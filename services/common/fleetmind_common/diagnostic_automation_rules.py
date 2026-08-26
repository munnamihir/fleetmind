from __future__ import annotations

from typing import Any

AUTOMATION_RULES_VERSION = "fm-diagnostic-automation-6.13-v1"

AUTOMATION_ACTION_ENSURE_REVIEW_PLAN = "ENSURE_REVIEW_PLAN"
AUTOMATION_ACTION_ENSURE_WATCHLIST = "ENSURE_WATCHLIST"
AUTOMATION_ACTION_TYPES = (
    AUTOMATION_ACTION_ENSURE_REVIEW_PLAN,
    AUTOMATION_ACTION_ENSURE_WATCHLIST,
)

AUTOMATION_STATUS_PENDING_APPROVAL = "PENDING_APPROVAL"
AUTOMATION_STATUS_APPROVED = "APPROVED"
AUTOMATION_STATUS_REJECTED = "REJECTED"
AUTOMATION_STATUS_EXECUTED = "EXECUTED"
AUTOMATION_ACTION_STATUSES = (
    AUTOMATION_STATUS_PENDING_APPROVAL,
    AUTOMATION_STATUS_APPROVED,
    AUTOMATION_STATUS_REJECTED,
    AUTOMATION_STATUS_EXECUTED,
)

AUTOMATION_ACTIVITY_POLICY_CREATED = "POLICY_CREATED"
AUTOMATION_ACTIVITY_POLICY_ENABLED = "POLICY_ENABLED"
AUTOMATION_ACTIVITY_POLICY_DISABLED = "POLICY_DISABLED"
AUTOMATION_ACTIVITY_ACTION_CREATED = "ACTION_CREATED"
AUTOMATION_ACTIVITY_ACTION_APPROVED = "ACTION_APPROVED"
AUTOMATION_ACTIVITY_ACTION_REJECTED = "ACTION_REJECTED"
AUTOMATION_ACTIVITY_ACTION_EXECUTED = "ACTION_EXECUTED"

# Phase 6.13 policies are intentionally deterministic and declared in source.
# They create approval-gated workflow actions only. They are not learned rules,
# physical-failure probabilities, causal conclusions, or private failure truth.
DEFAULT_AUTOMATION_POLICIES = (
    {
        "key": "urgent-review-without-plan",
        "name": "Urgent review without maintenance plan",
        "description": (
            "Queue creation of a REVIEW maintenance plan when the deterministic "
            "Phase 6.12 maintenance tier is URGENT_REVIEW and no plan exists."
        ),
        "priority": 100,
        "severity": "HIGH",
        "conditions": [
            {
                "field": "maintenanceTier",
                "operator": "eq",
                "value": "URGENT_REVIEW",
            },
            {
                "field": "maintenancePlan",
                "operator": "is_null",
                "value": True,
            },
        ],
        "actionType": AUTOMATION_ACTION_ENSURE_REVIEW_PLAN,
        "actionPayload": {"state": "REVIEW"},
        "requiresApproval": True,
    },
    {
        "key": "plan-service-without-plan",
        "name": "Plan-service tier without maintenance plan",
        "description": (
            "Queue creation of a REVIEW maintenance plan when the deterministic "
            "Phase 6.12 maintenance tier is PLAN_SERVICE and no plan exists."
        ),
        "priority": 80,
        "severity": "MEDIUM",
        "conditions": [
            {
                "field": "maintenanceTier",
                "operator": "eq",
                "value": "PLAN_SERVICE",
            },
            {
                "field": "maintenancePlan",
                "operator": "is_null",
                "value": True,
            },
        ],
        "actionType": AUTOMATION_ACTION_ENSURE_REVIEW_PLAN,
        "actionPayload": {"state": "REVIEW"},
        "requiresApproval": True,
    },
    {
        "key": "destabilized-not-watchlisted",
        "name": "Destabilized episode not on watchlist",
        "description": (
            "Queue watchlist enrollment when a current diagnostic case was "
            "created from a DESTABILIZED episode and is not already watchlisted."
        ),
        "priority": 90,
        "severity": "HIGH",
        "conditions": [
            {
                "field": "episodeState",
                "operator": "eq",
                "value": "DESTABILIZED",
            },
            {
                "field": "watchlisted",
                "operator": "eq",
                "value": False,
            },
        ],
        "actionType": AUTOMATION_ACTION_ENSURE_WATCHLIST,
        "actionPayload": {},
        "requiresApproval": True,
    },
)


def nested_value(record: dict[str, Any], field: str) -> Any:
    value: Any = record
    for part in field.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def condition_matches(record: dict[str, Any], condition: dict[str, Any]) -> bool:
    field = str(condition.get("field") or "")
    operator = str(condition.get("operator") or "eq")
    expected = condition.get("value")
    actual = nested_value(record, field)

    if operator == "eq":
        return actual == expected
    if operator == "neq":
        return actual != expected
    if operator == "in":
        return actual in (expected or [])
    if operator == "not_in":
        return actual not in (expected or [])
    if operator == "is_null":
        return (actual is None) is bool(expected)
    if operator == "truthy":
        return bool(actual) is bool(expected)
    if operator == "gte":
        return actual is not None and float(actual) >= float(expected)
    if operator == "lte":
        return actual is not None and float(actual) <= float(expected)

    raise ValueError(f"Unsupported automation condition operator: {operator}")


def policy_matches(record: dict[str, Any], policy: dict[str, Any]) -> bool:
    conditions = policy.get("conditions") or []
    return bool(conditions) and all(
        condition_matches(record, condition)
        for condition in conditions
    )


def policy_match_reason(record: dict[str, Any], policy: dict[str, Any]) -> str:
    matched = []
    for condition in policy.get("conditions") or []:
        field = str(condition.get("field") or "")
        operator = str(condition.get("operator") or "eq")
        expected = condition.get("value")
        actual = nested_value(record, field)
        matched.append(
            f"{field} {operator} {expected!r} (observed {actual!r})"
        )
    return "; ".join(matched)
