"""Suite 10: repeated performance and effectiveness measurements.

Append samples and run settings to evaluation/results/performance_metrics.jsonl.
Acceptance bounds apply to this prototype; report figures should use the
recorded measurements from the tested version."""

from __future__ import annotations

import json
import hashlib
import os
import statistics
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

INCIDENT_REPEATS = int(os.getenv("EVAL_PERF_REPEATS", "3"))
if not 1 <= INCIDENT_REPEATS <= 10:
    raise ValueError("EVAL_PERF_REPEATS must be between 1 and 10")

PERFORMANCE_RUN_ID = (
    f"perf-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
)
AUTHORIZED_REQUEST = {"person_id": "personnel-004", "command": {"power_on": True}}
FLOOD = {
    "device_id": "env-001",
    "attack_type": "telemetry_flood",
    "rate_per_second": 20,
}


def code_version():
    """Record both the Git revision and the source bytes, including local edits."""
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for folder in ("gateway", "simulator", "shared", "dashboard/src", "evaluation"):
        for path in sorted((root / folder).rglob("*")):
            if path.is_file() and path.suffix in {".py", ".js", ".jsx", ".css"}:
                digest.update(path.relative_to(root).as_posix().encode("utf-8"))
                digest.update(path.read_bytes())
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        revision = None
    return {"git_commit": revision, "source_sha256": digest.hexdigest()}


def run_context(**settings):
    return {
        "performance_run_id": PERFORMANCE_RUN_ID,
        "code_version": code_version(),
        **settings,
    }


def authorized_pdu_request(client, gateway_url):
    return client.post(
        f"{gateway_url}/devices/pdu-002/commands/pdu", json=AUTHORIZED_REQUEST
    )


def sample_authorized_requests(client, gateway_url, attempts=20):
    latencies = []
    successes = 0
    for _ in range(attempts):
        response, elapsed = timed_request(
            lambda: authorized_pdu_request(client, gateway_url)
        )
        latencies.append(elapsed)
        successes += response.status_code == 200
        time.sleep(0.05)
    return latencies, successes


def reset(client, gateway_url):
    r = client.post(f"{gateway_url}/system/reset-demo-data")
    assert r.status_code == 200, r.text
    time.sleep(0.6)


def security(client, gateway_url, device_id):
    r = client.get(f"{gateway_url}/security/devices/{device_id}")
    assert r.status_code == 200, r.text
    return r.json()


def operational_state(client, gateway_url, device_id):
    r = client.get(f"{gateway_url}/devices/{device_id}/operational-state")
    assert r.status_code == 200, r.text
    return r.json()


def wait_until(predicate, timeout=8.0, interval=0.1, description="condition"):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"Timed out waiting for {description}; last={last}")


def force_device_quarantine_by_violations(client, gateway_url, source_device_id):
    """Generate four denied device-originated commands.

    The current ABAC baseline has no allow policy for device-originated
    actuator control. Four violations inside the 10 s detector window are the
    configured quarantine threshold.
    """
    for _ in range(4):
        r = client.post(
            f"{gateway_url}/devices/pdu-002/commands/device/pdu",
            json={"source_device_id": source_device_id, "command": {"power_on": False}},
        )
        assert r.status_code == 403, r.text

    def quarantined_status():
        status = security(client, gateway_url, source_device_id)
        if status["security_state"] == "quarantined":
            return status
        return None

    return wait_until(quarantined_status, description=f"{source_device_id} quarantine")


def wait_for_response(
    client,
    gateway_url,
    device_id,
    strategy=None,
    timeout=8.0,
    *,
    quarantined_stage=False,
):
    def lookup():
        r = client.get(
            f"{gateway_url}/responses", params={"device_id": device_id, "limit": 20}
        )
        assert r.status_code == 200, r.text
        for item in r.json():
            if strategy is None or item["strategy"] == strategy:
                if quarantined_stage and not (
                    item["trigger_reason"].startswith("Severe sliding-window anomaly:")
                    and item["action"].startswith("Stop trusting sensor telemetry")
                ):
                    continue
                return item
        return None

    return wait_until(
        lookup, timeout=timeout, description=f"mitigation response for {device_id}"
    )


RESULTS = Path(__file__).resolve().parent / "results" / "performance_metrics.jsonl"


def record_metric(name, values, unit, context=None):
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    values = [float(v) for v in values]
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "metric": name,
        "unit": unit,
        "n": len(values),
        "min": min(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "max": max(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "values": values,
        "context": context or {},
    }
    with RESULTS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return record


def timed_request(call):
    start = time.perf_counter()
    response = call()
    return response, (time.perf_counter() - start) * 1000.0


def launch_attack(client, gateway_url, device_id, attack_type, rate=20, duration=2):
    r = client.post(
        f"{gateway_url}/attack/launch",
        json={
            "device_id": device_id,
            "attack_type": attack_type,
            "rate_per_second": rate,
            "duration_seconds": duration,
        },
    )
    assert r.status_code == 202, r.text
    return r.json()["attack_id"]


def wait_attack(client, gateway_url, attack_id, timeout=10):
    return wait_until(
        lambda: next(
            (
                item
                for item in client.get(f"{gateway_url}/attack/status").json()
                if item["attack_id"] == attack_id
                and item["status"] in {"completed", "failed", "cancelled"}
            ),
            None,
        ),
        timeout=timeout,
        description=attack_id,
    )


@pytest.mark.scenario(
    id="PERF-01",
    description="Measure legitimate gateway request latency under benign operation",
    expected="Repeated health/security reads complete successfully and provide a current baseline latency distribution.",
)
def test_baseline_request_latency(client, gateway_url):
    reset(client, gateway_url)
    samples, successes = sample_authorized_requests(client, gateway_url, attempts=30)

    result = record_metric(
        "baseline_authorized_pdu_request_latency",
        samples,
        "ms",
        run_context(
            request="POST /devices/pdu-002/commands/pdu",
            actor="personnel-004",
            requests=30,
            successful=successes,
        ),
    )
    assert successes == 30
    # A generous failure bound catches a seriously unhealthy local PoC while
    # leaving the measured distribution, not this threshold, as report evidence.
    assert result["max"] < 2000


@pytest.mark.scenario(
    id="PERF-02",
    description="Measure detection-to-mitigation timing for a flood incident",
    expected="The flood reaches quarantine and a successful automatic response is persisted; detector observation and response-engine durations are recorded.",
)
def test_detection_and_mitigation_latency(client, gateway_url):
    observations = []
    settings = run_context(
        attack={**FLOOD, "duration_seconds": 2}, repeats=INCIDENT_REPEATS
    )
    for repetition in range(1, INCIDENT_REPEATS + 1):
        reset(client, gateway_url)
        started = time.perf_counter()
        attack_id = launch_attack(
            client,
            gateway_url,
            FLOOD["device_id"],
            FLOOD["attack_type"],
            rate=FLOOD["rate_per_second"],
            duration=2,
        )
        quarantine_seen = wait_until(
            lambda: (
                time.perf_counter()
                if security(client, gateway_url, "env-001")["security_state"]
                == "quarantined"
                else None
            ),
            timeout=8,
            interval=0.02,
            description="flood quarantine",
        )
        response = wait_for_response(
            client,
            gateway_url,
            "env-001",
            strategy="logical_containment",
            quarantined_stage=True,
        )
        response_seen = time.perf_counter()
        attack = wait_attack(client, gateway_url, attack_id)
        assert attack["status"] == "completed"
        assert response["success"] is True
        detection_ms = (quarantine_seen - started) * 1000.0
        end_to_end_ms = (response_seen - started) * 1000.0
        assert detection_ms < 8000
        assert end_to_end_ms < 8000
        observations.append(
            {
                "repetition": repetition,
                "attack_id": attack_id,
                "attack_attempts": attack["attempts"],
                "response_id": response["response_id"],
                "strategy": response["strategy"],
                "trigger_reason": response["trigger_reason"],
                "quarantine_observation_ms": detection_ms,
                "response_engine_ms": response["duration_ms"],
                "end_to_end_observation_ms": end_to_end_ms,
            }
        )

    context = {
        **settings,
        "observations": observations,
        "timing_note": "Measured from launch request to observed state/response; includes polling and request latency.",
    }
    for metric, field in (
        ("quarantine_observation_latency", "quarantine_observation_ms"),
        ("response_engine_execution_duration", "response_engine_ms"),
        ("end_to_end_response_observation_latency", "end_to_end_observation_ms"),
    ):
        record_metric(metric, [item[field] for item in observations], "ms", context)


@pytest.mark.scenario(
    id="PERF-03",
    description="Measure legitimate availability and latency while another device is under attack",
    expected="Authorized room-002 PDU requests remain successful while env-001 is flooded, demonstrating local availability rather than whole-system shutdown.",
)
def test_legitimate_availability_during_attack(client, gateway_url):
    normal_samples, attack_samples = [], []
    observations = []
    attempts = 20
    settings = run_context(
        attack={**FLOOD, "duration_seconds": 3},
        repeats=INCIDENT_REPEATS,
        request="POST /devices/pdu-002/commands/pdu",
        actor="personnel-004",
        attempts_per_condition=attempts,
    )
    for repetition in range(1, INCIDENT_REPEATS + 1):
        reset(client, gateway_url)
        normal, normal_successes = sample_authorized_requests(
            client, gateway_url, attempts
        )
        assert normal_successes == attempts
        attack_id = launch_attack(
            client,
            gateway_url,
            FLOOD["device_id"],
            FLOOD["attack_type"],
            rate=FLOOD["rate_per_second"],
            duration=3,
        )
        during_attack, attack_successes = sample_authorized_requests(
            client, gateway_url, attempts
        )
        attack = wait_attack(client, gateway_url, attack_id)
        assert attack["status"] == "completed"
        availability = attack_successes / attempts
        assert availability >= 0.95
        normal_samples.extend(normal)
        attack_samples.extend(during_attack)
        observations.append(
            {
                "repetition": repetition,
                "attack_id": attack_id,
                "attack_attempts": attack["attempts"],
                "normal_successes": normal_successes,
                "attack_successes": attack_successes,
                "normal_mean_ms": statistics.fmean(normal),
                "attack_mean_ms": statistics.fmean(during_attack),
                "availability_percent": availability * 100.0,
            }
        )

    context = {
        **settings,
        "observations": observations,
        "timing_note": "Identical authorized PDU commands before and during each flood; sequential within each reset.",
    }
    record_metric("legitimate_request_latency_normal", normal_samples, "ms", context)
    record_metric(
        "legitimate_request_latency_during_attack", attack_samples, "ms", context
    )
    record_metric(
        "legitimate_request_availability_during_attack",
        [item["availability_percent"] for item in observations],
        "percent",
        context,
    )


@pytest.mark.scenario(
    id="PERF-04",
    description="Measure benign false-positive behaviour",
    expected="Representative healthy devices remain NORMAL during the observation period, yielding zero false security escalations in this controlled sample.",
)
def test_benign_false_positive_sample(client, gateway_url):
    reset(client, gateway_url)

    device_ids = [
        "env-001",
        "env-002",
        "env-003",
        "env-004",
        "env-005",
        "env-006",
        "pdu-001",
        "pdu-002",
    ]
    observations = 5
    false_escalations = 0
    total = 0

    for _ in range(observations):
        time.sleep(1)
        for device_id in device_ids:
            total += 1
            if security(client, gateway_url, device_id)["security_state"] != "normal":
                false_escalations += 1

    rate = false_escalations / total
    record_metric(
        "benign_false_positive_rate",
        [rate * 100.0],
        "percent",
        {"observations": total, "false_escalations": false_escalations},
    )
    assert false_escalations == 0


@pytest.mark.scenario(
    id="PERF-05",
    description="Measure gateway container CPU and memory snapshot when Docker Compose statistics are available",
    expected="Capture resource-use evidence from the running gateway container; skip only when the local Docker CLI cannot provide Compose stats.",
)
def test_gateway_resource_snapshot():
    try:
        completed = subprocess.run(
            [
                "docker",
                "compose",
                "stats",
                "--no-stream",
                "--format",
                "json",
                "gateway",
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        pytest.skip(f"Docker Compose stats unavailable: {exc}")

    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        pytest.skip("Docker Compose returned no gateway resource statistics")

    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError:
        pytest.skip(f"Could not parse Docker Compose stats: {completed.stdout!r}")

    # Docker's JSON format reports human-readable percentages/quantities.
    cpu_text = str(payload.get("CPUPerc", payload.get("CPU", ""))).strip()
    mem_text = str(payload.get("MemUsage", "")).strip()
    if not cpu_text:
        pytest.skip(f"CPU field unavailable in Docker stats: {payload}")

    cpu_percent = float(cpu_text.rstrip("%"))
    record_metric(
        "gateway_cpu_snapshot",
        [cpu_percent],
        "percent",
        {"memory_usage": mem_text, "raw": payload},
    )
    assert cpu_percent >= 0
