"""Match ABAC requests against enabled policies.

Any matching deny takes precedence; no matching allow means denial. A role
list matches any listed role, while separate attribute conditions must all match."""

from gateway.policy.repository import list_policies
from shared.policy import Policy, PolicyDecision, PolicyEffect, PolicyRequest


def evaluate_policy(request: PolicyRequest) -> PolicyDecision:
    """Evaluate a request against all enabled policies."""

    matching_policies = [
        policy
        for policy in list_policies()
        if policy.enabled and _matches(policy, request)
    ]

    matching_policies.sort(key=lambda policy: policy.priority, reverse=True)

    for policy in matching_policies:
        if policy.effect == PolicyEffect.DENY:
            return PolicyDecision(
                allowed=False,
                effect=PolicyEffect.DENY,
                policy_id=policy.policy_id,
                policy_name=policy.name,
                reason="Request matched an explicit deny policy.",
            )

    for policy in matching_policies:
        if policy.effect == PolicyEffect.ALLOW:
            return PolicyDecision(
                allowed=True,
                effect=PolicyEffect.ALLOW,
                policy_id=policy.policy_id,
                policy_name=policy.name,
                reason="Request matched an allow policy.",
            )

    return PolicyDecision(
        allowed=False,
        effect=PolicyEffect.DENY,
        reason="No applicable allow policy matched; default deny applied.",
    )


def _matches(policy: Policy, request: PolicyRequest) -> bool:
    """
    Return True only when every configured attribute condition matches.

    Roles within ``subject_roles`` use OR semantics. Independent attributes
    such as role, clearance, room, action and security state use AND semantics.
    """

    if policy.action != request.action:
        return False

    if policy.subject_type != request.subject.subject_type:
        return False

    if policy.resource_type != request.resource.resource_type:
        return False

    if (
        policy.subject_roles is not None
        and request.subject.role not in policy.subject_roles
    ):
        return False

    if policy.minimum_clearance is not None:
        if request.subject.clearance is None:
            return False
        if request.subject.clearance < policy.minimum_clearance:
            return False

    if (
        policy.subject_device_type is not None
        and policy.subject_device_type != request.subject.device_type
    ):
        return False

    if (
        policy.resource_device_type is not None
        and policy.resource_device_type != request.resource.device_type
    ):
        return False

    if policy.require_same_room:
        if (
            request.subject.room_id is None
            or request.resource.room_id is None
            or request.subject.room_id != request.resource.room_id
        ):
            return False

    if policy.allowed_subject_security_states is not None:
        if request.subject.security_state not in policy.allowed_subject_security_states:
            return False

    if policy.allowed_resource_security_states is not None:
        if (
            request.resource.security_state
            not in policy.allowed_resource_security_states
        ):
            return False

    if not _time_matches(policy, request):
        return False

    return True


def _time_matches(policy: Policy, request: PolicyRequest) -> bool:
    """Apply optional hour-based context restrictions."""

    if policy.start_hour is None and policy.end_hour is None:
        return True

    hour = request.context.hour

    if hour is None:
        return False

    if policy.start_hour is None or policy.end_hour is None:
        return False

    if policy.start_hour <= policy.end_hour:
        return policy.start_hour <= hour < policy.end_hour

    return hour >= policy.start_hour or hour < policy.end_hour
