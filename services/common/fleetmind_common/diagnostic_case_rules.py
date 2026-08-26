from __future__ import annotations

from .diagnostic_episode_rules import (
    EPISODE_DESTABILIZED,
    EPISODE_EVOLVING,
    EPISODE_RULES_VERSION,
    EPISODE_STABILIZED,
)

CASE_RULES_VERSION = "fm-diagnostic-cases-6.10-v1"
CASE_SOURCE_EPISODE_RULES_VERSION = EPISODE_RULES_VERSION

CASE_OPEN = "OPEN"
CASE_ACKNOWLEDGED = "ACKNOWLEDGED"
CASE_INVESTIGATING = "INVESTIGATING"
CASE_MONITORING = "MONITORING"
CASE_CLOSED = "CLOSED"

DIAGNOSTIC_CASE_STATUSES = (
    CASE_OPEN,
    CASE_ACKNOWLEDGED,
    CASE_INVESTIGATING,
    CASE_MONITORING,
    CASE_CLOSED,
)

CASE_PRIORITY_HIGH = "HIGH"
CASE_PRIORITY_MEDIUM = "MEDIUM"
CASE_PRIORITY_LOW = "LOW"

DIAGNOSTIC_CASE_PRIORITIES = (
    CASE_PRIORITY_HIGH,
    CASE_PRIORITY_MEDIUM,
    CASE_PRIORITY_LOW,
)

CASE_ACTIVITY_CREATED = "CASE_CREATED"
CASE_ACTIVITY_STATUS_CHANGED = "STATUS_CHANGED"
CASE_ACTIVITY_PRIORITY_CHANGED = "PRIORITY_CHANGED"
CASE_ACTIVITY_ASSIGNED = "ASSIGNED"
CASE_ACTIVITY_NOTE_ADDED = "NOTE_ADDED"

DIAGNOSTIC_CASE_ACTIVITY_TYPES = (
    CASE_ACTIVITY_CREATED,
    CASE_ACTIVITY_STATUS_CHANGED,
    CASE_ACTIVITY_PRIORITY_CHANGED,
    CASE_ACTIVITY_ASSIGNED,
    CASE_ACTIVITY_NOTE_ADDED,
)

# Case creation is an operational workflow layer over persisted episodes.
# Only currently open model-hypothesis episodes enter the active case queue.
CASE_ELIGIBLE_EPISODE_OPEN_ONLY = True

# Review priority is a deterministic triage heuristic, NOT calibrated
# physical-failure risk and NOT private failure truth.
CASE_HIGH_CONFIDENCE = 0.95
CASE_MEDIUM_CONFIDENCE = 0.80
CASE_HIGH_ESCALATION_COUNT = 1


def derive_case_review_priority(
    *,
    episode_state: str,
    latest_confidence: float | None,
    escalation_count: int,
    destabilized_count: int,
) -> str:
    confidence = float(latest_confidence or 0.0)

    if (
        episode_state == EPISODE_DESTABILIZED
        or destabilized_count > 0
        or (
            confidence >= CASE_HIGH_CONFIDENCE
            and escalation_count >= CASE_HIGH_ESCALATION_COUNT
        )
    ):
        return CASE_PRIORITY_HIGH

    if (
        episode_state in (EPISODE_EVOLVING, EPISODE_STABILIZED)
        or confidence >= CASE_MEDIUM_CONFIDENCE
        or escalation_count > 0
    ):
        return CASE_PRIORITY_MEDIUM

    return CASE_PRIORITY_LOW
