"""Versioned recommendation policy replay for FleetMind Phases 8.4 and 8.5."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from typing import Any


POLICY_EVALUATION_RULES_VERSION = "fm-recommendation-policy-8.4-v1"
SHADOW_EXPERIMENT_RULES_VERSION = "fm-shadow-policy-8.5-v1"

PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

DEFAULT_CONTROL_POLICY = {
    "policyKey": "closed-loop-control",
    "version": "1.0.0",
    "name": "Closed Loop Control",
    "description": "Current deterministic recommendation set with no additional filtering.",
    "rules": {
        "allowedRecommendationTypes": [],
        "blockedRecommendationTypes": [],
        "maximumPriorityRank": 3,
        "maximumCandidatesPerVehicle": 8,
        "blockedSourcePrefixes": [],
        "conflictPairs": [],
    },
}

DEFAULT_CANDIDATE_POLICY = {
    "policyKey": "closed-loop-selective",
    "version": "1.0.0",
    "name": "Selective Review Candidate",
    "description": "Shadow-only candidate emphasizing P0-P2 workflow recommendations.",
    "rules": {
        "allowedRecommendationTypes": [],
        "blockedRecommendationTypes": [],
        "maximumPriorityRank": 2,
        "maximumCandidatesPerVehicle": 4,
        "blockedSourcePrefixes": [],
        "conflictPairs": [],
    },
}


def canonical_hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def policy_evaluation_key(
    *,
    policy_id: int,
    run_id: int,
    input_hash: str,
    rules_version: str = POLICY_EVALUATION_RULES_VERSION,
) -> str:
    return canonical_hash(
        {
            "policyId": int(policy_id),
            "runId": int(run_id),
            "inputHash": input_hash,
            "rulesVersion": rules_version,
        }
    )


def _candidate_identity(candidate: dict[str, Any]) -> str:
    return canonical_hash(
        {
            "vehicleId": candidate.get("vehicleId"),
            "caseId": candidate.get("caseId"),
            "recommendationType": candidate.get("recommendationType"),
            "sourceKey": candidate.get("sourceKey"),
        }
    )


def evaluate_policy(
    candidates: list[dict[str, Any]],
    policy_rules: dict[str, Any],
    *,
    input_is_frozen: bool,
) -> dict[str, Any]:
    allowed = set(policy_rules.get("allowedRecommendationTypes") or [])
    blocked = set(policy_rules.get("blockedRecommendationTypes") or [])
    blocked_prefixes = tuple(policy_rules.get("blockedSourcePrefixes") or [])
    max_rank = int(policy_rules.get("maximumPriorityRank", 3))
    max_per_vehicle = max(1, int(policy_rules.get("maximumCandidatesPerVehicle", 8)))

    deduped: dict[str, dict[str, Any]] = {}
    duplicate_count = 0
    for candidate in candidates:
        key = _candidate_identity(candidate)
        if key in deduped:
            duplicate_count += 1
            continue
        deduped[key] = dict(candidate)

    filtered = []
    suppressed = Counter()
    per_vehicle = defaultdict(int)

    ordered = sorted(
        deduped.values(),
        key=lambda row: (
            PRIORITY_RANK.get(str(row.get("priority")), 99),
            str(row.get("vehicleId") or ""),
            str(row.get("recommendationType") or ""),
            str(row.get("sourceKey") or ""),
        ),
    )

    for candidate in ordered:
        rec_type = str(candidate.get("recommendationType") or "")
        priority = str(candidate.get("priority") or "P3")
        source_key = str(candidate.get("sourceKey") or "")
        vehicle_id = str(candidate.get("vehicleId") or "")

        if allowed and rec_type not in allowed:
            suppressed["not_allowed_type"] += 1
            continue
        if rec_type in blocked:
            suppressed["blocked_type"] += 1
            continue
        if PRIORITY_RANK.get(priority, 99) > max_rank:
            suppressed["priority_filter"] += 1
            continue
        if blocked_prefixes and source_key.startswith(blocked_prefixes):
            suppressed["blocked_source"] += 1
            continue
        if per_vehicle[vehicle_id] >= max_per_vehicle:
            suppressed["per_vehicle_limit"] += 1
            continue

        per_vehicle[vehicle_id] += 1
        candidate = dict(candidate)
        candidate["policyCandidateKey"] = _candidate_identity(candidate)
        filtered.append(candidate)

    conflict_pairs = {
        frozenset(pair)
        for pair in (policy_rules.get("conflictPairs") or [])
        if isinstance(pair, list) and len(pair) == 2
    }
    types_by_vehicle: dict[str, set[str]] = defaultdict(set)
    for candidate in filtered:
        types_by_vehicle[str(candidate.get("vehicleId") or "")].add(
            str(candidate.get("recommendationType") or "")
        )

    conflicts = []
    for vehicle_id, types in sorted(types_by_vehicle.items()):
        for pair in conflict_pairs:
            if pair.issubset(types):
                conflicts.append(
                    {
                        "vehicleId": vehicle_id,
                        "recommendationTypes": sorted(pair),
                    }
                )

    by_type = Counter(str(row.get("recommendationType") or "UNKNOWN") for row in filtered)
    by_priority = Counter(str(row.get("priority") or "UNKNOWN") for row in filtered)

    cohort_coverage: dict[str, dict[str, int]] = {}
    for dimension in ("factory", "model", "firmware", "pumpRevision", "hypothesisClass"):
        counts = Counter()
        for row in filtered:
            context = row.get("context") or {}
            value = context.get(dimension)
            if value is not None:
                counts[str(value)] += 1
        cohort_coverage[dimension] = dict(sorted(counts.items()))

    candidate_count = len(filtered)
    input_count = len(candidates)
    selectivity = candidate_count / input_count if input_count else 0.0

    promotion_reasons = []
    if not input_is_frozen:
        promotion_reasons.append("evaluation input is not a full frozen fleet snapshot")
    if conflicts:
        promotion_reasons.append("policy produced configured conflicts")
    if input_count and candidate_count == 0:
        promotion_reasons.append("policy selected zero candidates")

    return {
        "rulesVersion": POLICY_EVALUATION_RULES_VERSION,
        "inputCandidates": input_count,
        "deduplicatedCandidates": len(deduped),
        "duplicateSuppressed": duplicate_count,
        "selectedCandidates": candidate_count,
        "selectivityPct": round(selectivity * 100.0, 4),
        "suppressedByReason": dict(sorted(suppressed.items())),
        "byType": dict(sorted(by_type.items())),
        "byPriority": dict(sorted(by_priority.items())),
        "cohortCoverage": cohort_coverage,
        "conflicts": conflicts,
        "candidates": filtered,
        "promotionCriteria": {
            "met": not promotion_reasons,
            "reasons": promotion_reasons,
            "requiresHumanReview": True,
            "automaticPromotion": False,
        },
        "claimBoundary": {
            "noWriteRecommendationReplay": True,
            "productionBehaviorChanged": False,
            "automaticApproval": False,
            "automaticExecution": False,
        },
    }


def compare_shadow_results(
    control: dict[str, Any],
    candidate: dict[str, Any],
    *,
    outcome_summary_by_type: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    control_keys = {
        str(row.get("policyCandidateKey"))
        for row in control.get("candidates") or []
    }
    candidate_keys = {
        str(row.get("policyCandidateKey"))
        for row in candidate.get("candidates") or []
    }

    overlap = control_keys & candidate_keys
    only_control = control_keys - candidate_keys
    only_candidate = candidate_keys - control_keys

    return {
        "rulesVersion": SHADOW_EXPERIMENT_RULES_VERSION,
        "controlCandidateCount": len(control_keys),
        "candidateCandidateCount": len(candidate_keys),
        "overlapCount": len(overlap),
        "controlOnlyCount": len(only_control),
        "candidateOnlyCount": len(only_candidate),
        "candidateVolumeDelta": len(candidate_keys) - len(control_keys),
        "candidateVolumeDeltaPct": (
            round(
                (len(candidate_keys) - len(control_keys))
                / max(1, len(control_keys))
                * 100.0,
                4,
            )
        ),
        "controlConflicts": len(control.get("conflicts") or []),
        "candidateConflicts": len(candidate.get("conflicts") or []),
        "observedOutcomeContext": outcome_summary_by_type or {},
        "promotionGate": {
            "candidatePolicyReplayReady": bool(
                candidate.get("promotionCriteria", {}).get("met")
            ),
            "operatorReviewRequired": True,
            "automaticPromotion": False,
        },
        "claimBoundary": {
            "shadowOnly": True,
            "recommendationWrites": False,
            "workflowWrites": False,
            "physicalActions": False,
            "causalOutcomeComparison": False,
        },
    }
