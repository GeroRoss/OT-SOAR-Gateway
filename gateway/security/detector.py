"""Track message rates, policy violations, and peer disagreement per device.

Sliding-window counts and integrity streaks drive security-state changes.
Suspicious recovery depends on the recorded cause; quarantine requires
manual release."""

import time

from collections import defaultdict, deque
from threading import Lock, Thread


from gateway.registry import get_device, update_device_security_state

from gateway.security.repository import add_security_event

from gateway.response.engine import (
    execute_automatic_response,
    execute_suspicious_response,
)

from shared.devices import SecurityState

WINDOW_SECONDS = 10

SUSPICIOUS_MESSAGE_THRESHOLD = 8
QUARANTINE_MESSAGE_THRESHOLD = 14

SUSPICIOUS_VIOLATION_THRESHOLD = 2
QUARANTINE_VIOLATION_THRESHOLD = 4

RECOVERY_SECONDS = 20

# Peer-corroboration state machine. These counts are deliberately sample-based
# rather than time-based so the simulator can time-compress the experiment.
INTEGRITY_QUARANTINE_STREAK = 4
INTEGRITY_RECOVERY_STREAK = 3


class SlidingWindowDetector:
    """
    Maintains recent message and policy-violation timestamps for each
    registered device.
    """

    def __init__(self):
        self.message_events = defaultdict(deque)

        self.violation_events = defaultdict(deque)

        self.last_anomaly_at: dict[str, float] = {}

        self.integrity_disagreement_streak = defaultdict(int)
        self.integrity_recovery_streak = defaultdict(int)
        self.suspicious_causes = defaultdict(set)

        self.lock = Lock()

    def record_message(self, device_id: str):
        """
        Record one accepted device message and evaluate its behaviour.
        """

        now = time.monotonic()

        with self.lock:
            self.message_events[device_id].append(now)

            self._prune(device_id, now)

            return self._evaluate(device_id, now)

    def record_policy_violation(self, device_id: str, reason: str):
        """
        Record one ABAC violation attributed to a known device.
        """

        now = time.monotonic()

        with self.lock:
            self.violation_events[device_id].append(now)

            self._prune(device_id, now)

            message_count = len(self.message_events[device_id])

            violation_count = len(self.violation_events[device_id])

            add_security_event(
                device_id=device_id,
                event_type="policy_violation",
                reason=reason,
                message_count=message_count,
                violation_count=violation_count,
            )

            return self._evaluate(device_id, now)

    def record_integrity_disagreement(self, device_id: str, reason: str):
        """
        Record one corroborated content-integrity disagreement.

        Unlike generic ABAC violations, the first corroborated outlier moves a
        NORMAL sensor directly to SUSPICIOUS so it can be observed without
        immediately declaring compromise. Four consecutive disagreements
        quarantine it.
        """

        now = time.monotonic()

        with self.lock:
            device = get_device(device_id)
            if device is None:
                return None

            if device.security_state == SecurityState.QUARANTINED:
                return self._build_status(device_id, SecurityState.QUARANTINED)

            self.integrity_disagreement_streak[device_id] += 1
            self.integrity_recovery_streak[device_id] = 0
            self.last_anomaly_at[device_id] = now

            streak = self.integrity_disagreement_streak[device_id]

            add_security_event(
                device_id=device_id,
                event_type="integrity_disagreement",
                reason=f"{reason}. Observation disagreement streak: {streak}.",
                message_count=len(self.message_events[device_id]),
                violation_count=len(self.violation_events[device_id]),
            )

            if streak >= INTEGRITY_QUARANTINE_STREAK:
                self._transition(
                    device_id=device_id,
                    previous_state=device.security_state,
                    new_state=SecurityState.QUARANTINED,
                    reason=(
                        "Persistent peer-corroboration anomaly: "
                        f"{streak} consecutive observations disagreed with "
                        "two mutually agreeing same-room sensors. "
                        "Possible slow telemetry poisoning or sensor fault."
                    ),
                    message_count=len(self.message_events[device_id]),
                    violation_count=len(self.violation_events[device_id]),
                )
                return self._build_status(device_id, SecurityState.QUARANTINED)

            if device.security_state == SecurityState.NORMAL:
                self.suspicious_causes[device_id] = {"integrity"}
                self._transition(
                    device_id=device_id,
                    previous_state=SecurityState.NORMAL,
                    new_state=SecurityState.SUSPICIOUS,
                    reason=(
                        "Peer-corroboration anomaly: this sensor disagrees "
                        "with two mutually agreeing same-room sensors. "
                        "Entering observation state."
                    ),
                    message_count=len(self.message_events[device_id]),
                    violation_count=len(self.violation_events[device_id]),
                )

            return self._build_status(device_id, SecurityState.SUSPICIOUS)

    def record_integrity_agreement(self, device_id: str, reason: str):
        """
        Record corroborated recovery evidence for a sensor made SUSPICIOUS by
        content disagreement. Three consecutive agreeing observations restore
        NORMAL; QUARANTINED remains manual-reset only.
        """

        with self.lock:
            device = get_device(device_id)
            if device is None:
                return None

            if device.security_state == SecurityState.QUARANTINED:
                return self._build_status(device_id, SecurityState.QUARANTINED)

            self.integrity_disagreement_streak[device_id] = 0

            if device.security_state != SecurityState.SUSPICIOUS:
                self.integrity_recovery_streak[device_id] = 0
                return self._build_status(device_id, device.security_state)

            # Corroboration can only reverse the state transition it caused.
            # A flood/rate or ABAC anomaly may happen to publish values that
            # agree with peers, but that is not evidence that its cause ended.
            if self.suspicious_causes[device_id] != {"integrity"}:
                self.integrity_recovery_streak[device_id] = 0
                return self._build_status(device_id, SecurityState.SUSPICIOUS)

            self.integrity_recovery_streak[device_id] += 1
            streak = self.integrity_recovery_streak[device_id]

            if streak >= INTEGRITY_RECOVERY_STREAK:
                self._transition(
                    device_id=device_id,
                    previous_state=SecurityState.SUSPICIOUS,
                    new_state=SecurityState.NORMAL,
                    reason=(
                        "Peer-corroboration recovered: "
                        f"{streak} consecutive observations returned within "
                        "the agreed same-room sensor range."
                    ),
                    message_count=len(self.message_events[device_id]),
                    violation_count=len(self.violation_events[device_id]),
                )
                self.integrity_recovery_streak[device_id] = 0
                self.last_anomaly_at.pop(device_id, None)
                return self._build_status(device_id, SecurityState.NORMAL)

            add_security_event(
                device_id=device_id,
                event_type="integrity_recovery_observation",
                reason=f"{reason}. Recovery observation {streak}/{INTEGRITY_RECOVERY_STREAK}.",
                message_count=len(self.message_events[device_id]),
                violation_count=len(self.violation_events[device_id]),
            )
            return self._build_status(device_id, SecurityState.SUSPICIOUS)

    def record_monitoring_uncertainty(self, device_id: str, reason: str):
        """
        Log an ambiguous three-sensor observation without accusing a device.
        Security state is intentionally unchanged because no two sources
        corroborate strongly enough to establish a trustworthy reference.
        """

        with self.lock:
            device = get_device(device_id)
            if device is None:
                return None

            add_security_event(
                device_id=device_id,
                event_type="monitoring_uncertainty",
                reason=reason,
                message_count=len(self.message_events[device_id]),
                violation_count=len(self.violation_events[device_id]),
            )
            return self._build_status(device_id, device.security_state)

    def get_status(self, device_id: str):
        """
        Return the current rolling detector state for a device.

        Status retrieval also evaluates recovery eligibility so a quiet
        SUSPICIOUS device can return to NORMAL after RECOVERY_SECONDS
        without requiring another telemetry message or policy violation.
        """

        now = time.monotonic()

        with self.lock:
            self._prune(device_id, now)

            return self._evaluate(device_id, now)

    def reset_device(self, device_id: str):
        """
        Manually clear detector history and return the device to NORMAL.

        This is required for recovery from QUARANTINED.
        """

        with self.lock:
            device = get_device(device_id)

            if device is None:
                return None

            previous_state = device.security_state

            self.message_events[device_id].clear()

            self.violation_events[device_id].clear()

            self.last_anomaly_at.pop(device_id, None)
            self.integrity_disagreement_streak.pop(device_id, None)
            self.integrity_recovery_streak.pop(device_id, None)
            self.suspicious_causes.pop(device_id, None)

            update_device_security_state(device_id, SecurityState.NORMAL)

            if previous_state != SecurityState.NORMAL:
                add_security_event(
                    device_id=device_id,
                    event_type=("state_transition"),
                    reason=("Manual security reset"),
                    previous_state=(previous_state.value),
                    new_state=(SecurityState.NORMAL.value),
                    message_count=0,
                    violation_count=0,
                )

            return self._build_status(device_id, SecurityState.NORMAL)

    def clear_all_runtime_state(self):
        """Clear in-memory detector windows after a development data reset."""

        with self.lock:
            self.message_events.clear()
            self.violation_events.clear()
            self.last_anomaly_at.clear()
            self.integrity_disagreement_streak.clear()
            self.integrity_recovery_streak.clear()
            self.suspicious_causes.clear()

    def get_configuration(self):
        """
        Expose detector parameters for transparency and evaluation.
        """

        return {
            "window_seconds": (WINDOW_SECONDS),
            "suspicious_message_threshold": (SUSPICIOUS_MESSAGE_THRESHOLD),
            "quarantine_message_threshold": (QUARANTINE_MESSAGE_THRESHOLD),
            "suspicious_violation_threshold": (SUSPICIOUS_VIOLATION_THRESHOLD),
            "quarantine_violation_threshold": (QUARANTINE_VIOLATION_THRESHOLD),
            "recovery_seconds": (RECOVERY_SECONDS),
            "integrity_quarantine_streak": (INTEGRITY_QUARANTINE_STREAK),
            "integrity_recovery_streak": (INTEGRITY_RECOVERY_STREAK),
        }

    def _prune(self, device_id: str, now: float):
        """
        Remove timestamps that have moved outside the sliding window.
        """

        cutoff = now - WINDOW_SECONDS

        messages = self.message_events[device_id]

        while messages and messages[0] < cutoff:
            messages.popleft()

        violations = self.violation_events[device_id]

        while violations and violations[0] < cutoff:
            violations.popleft()

    def _evaluate(self, device_id: str, now: float):
        """
        Evaluate current rolling counts and apply any state transition.
        """

        device = get_device(device_id)

        if device is None:
            return None

        current_state = device.security_state

        message_count = len(self.message_events[device_id])

        violation_count = len(self.violation_events[device_id])

        # Quarantine is terminal until an explicit reset.
        if current_state == SecurityState.QUARANTINED:
            return self._build_status(device_id, current_state)

        severe_anomaly = (
            message_count >= QUARANTINE_MESSAGE_THRESHOLD
            or violation_count >= QUARANTINE_VIOLATION_THRESHOLD
        )

        suspicious_anomaly = (
            message_count >= SUSPICIOUS_MESSAGE_THRESHOLD
            or violation_count >= SUSPICIOUS_VIOLATION_THRESHOLD
        )

        if severe_anomaly:
            reason = (
                "Severe sliding-window anomaly: "
                f"{message_count} messages and "
                f"{violation_count} policy violations "
                f"within {WINDOW_SECONDS} seconds"
            )

            self._transition(
                device_id=device_id,
                previous_state=current_state,
                new_state=(SecurityState.QUARANTINED),
                reason=reason,
                message_count=message_count,
                violation_count=(violation_count),
            )

            return self._build_status(device_id, SecurityState.QUARANTINED)

        if suspicious_anomaly:
            self.last_anomaly_at[device_id] = now

            if message_count >= SUSPICIOUS_MESSAGE_THRESHOLD:
                self.suspicious_causes[device_id].add("message_rate")
            if violation_count >= SUSPICIOUS_VIOLATION_THRESHOLD:
                self.suspicious_causes[device_id].add("policy_violation")

            if current_state == SecurityState.NORMAL:
                reason = (
                    "Sliding-window anomaly: "
                    f"{message_count} messages and "
                    f"{violation_count} policy violations "
                    f"within {WINDOW_SECONDS} seconds"
                )

                self._transition(
                    device_id=device_id,
                    previous_state=(current_state),
                    new_state=(SecurityState.SUSPICIOUS),
                    reason=reason,
                    message_count=(message_count),
                    violation_count=(violation_count),
                )

            return self._build_status(device_id, SecurityState.SUSPICIOUS)

        # Suspicious devices may return to normal after enough time
        # without another threshold-level anomaly.
        if current_state == SecurityState.SUSPICIOUS:
            last_anomaly = self.last_anomaly_at.get(device_id)

            if last_anomaly is not None and (now - last_anomaly >= RECOVERY_SECONDS):
                self._transition(
                    device_id=device_id,
                    previous_state=(SecurityState.SUSPICIOUS),
                    new_state=(SecurityState.NORMAL),
                    reason=("Suspicious device returned " "to normal behaviour"),
                    message_count=(message_count),
                    violation_count=(violation_count),
                )

                self.last_anomaly_at.pop(device_id, None)
                self.suspicious_causes.pop(device_id, None)

                return self._build_status(device_id, SecurityState.NORMAL)

        return self._build_status(device_id, current_state)

    def _transition(
        self,
        device_id: str,
        previous_state: SecurityState,
        new_state: SecurityState,
        reason: str,
        message_count: int,
        violation_count: int,
    ):
        """
        Persist a state change and create a corresponding security event.
        """

        if previous_state == new_state:
            return

        update_device_security_state(device_id, new_state)

        add_security_event(
            device_id=device_id,
            event_type="state_transition",
            reason=reason,
            previous_state=(previous_state.value),
            new_state=new_state.value,
            message_count=message_count,
            violation_count=(violation_count),
        )

        if new_state == SecurityState.SUSPICIOUS:
            Thread(
                target=execute_suspicious_response,
                args=(device_id, reason),
                daemon=True,
                name=f"suspicious-response-{device_id}",
            ).start()

        if new_state == SecurityState.QUARANTINED:
            Thread(
                target=execute_automatic_response,
                args=(device_id, reason),
                daemon=True,
                name=f"mitigation-{device_id}",
            ).start()

    def _build_status(self, device_id: str, state: SecurityState):
        return {
            "device_id": device_id,
            "security_state": state.value,
            "message_count": len(self.message_events[device_id]),
            "policy_violation_count": len(self.violation_events[device_id]),
            "window_seconds": (WINDOW_SECONDS),
            "integrity_disagreement_streak": (
                self.integrity_disagreement_streak[device_id]
            ),
            "integrity_recovery_streak": (self.integrity_recovery_streak[device_id]),
        }


detector = SlidingWindowDetector()
