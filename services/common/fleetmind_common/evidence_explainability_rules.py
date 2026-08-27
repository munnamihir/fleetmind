"""Deterministic evidence and explainability helpers for FleetMind Phase 7.6.

This module explains operational scoring logic that FleetMind itself defines.
It does not provide SHAP values, feature attribution, causal attribution,
physical failure truth, reliability probability, physical RUL, or calibrated
failure risk.
"""

from __future__ import annotations

from typing import Any

from fleetmind_common.fleet_decision_rules import (
    GAP_DESTABILIZED_NOT_WATCHLISTED,
    GAP_NONHEALTHY_WITHOUT_CASE,
    GAP_PENDING_AUTOMATION_APPROVAL,
    GAP_PRIORITY_CASE_WITHOUT_PLAN,
    GAP_TRAJECTORY_INELIGIBLE,
    GAP_UNASSIGNED_CASE,
    attention_score,
    coverage_gaps,
)


EVIDENCE_EXPLAINABILITY_RULES_VERSION = "fm-evidence-explainability-7.6-v1"

ATTENTION_FACTOR_MODEL_CONFIDENCE = "MODEL_CONFIDENCE"
ATTENTION_FACTOR_REVIEW_PRIORITY = "REVIEW_PRIORITY"
ATTENTION_FACTOR_MAINTENANCE_TIER = "MAINTENANCE_TIER"
ATTENTION_FACTOR_EPISODE_STATE = "EPISODE_STATE"
ATTENTION_FACTOR_WATCHLIST = "WATCHLIST"
ATTENTION_FACTOR_SCORE_CAP = "SCORE_CAP"

ATTENTION_FACTOR_GAP_PREFIX = "COVERAGE_GAP_"

REVIEW_PRIORITY_WEIGHTS = {
    "HIGH": 20.0,
    "MEDIUM": 12.0,
    "LOW": 4.0,
}

MAINTENANCE_TIER_WEIGHTS = {
    "URGENT_REVIEW": 25.0,
    "PLAN_SERVICE": 18.0,
    "MONITOR": 8.0,
    "ROUTINE_REVIEW": 2.0,
}

EPISODE_STATE_WEIGHTS = {
    "DESTABILIZED": 10.0,
    "STABILIZED": 5.0,
    "EVOLVING": 3.0,
    "EMERGING": 2.0,
}

COVERAGE_GAP_WEIGHTS = {
    GAP_NONHEALTHY_WITHOUT_CASE: 12.0,
    GAP_UNASSIGNED_CASE: 5.0,
    GAP_PRIORITY_CASE_WITHOUT_PLAN: 10.0,
    GAP_DESTABILIZED_NOT_WATCHLISTED: 8.0,
    GAP_TRAJECTORY_INELIGIBLE: 5.0,
    GAP_PENDING_AUTOMATION_APPROVAL: 4.0,
}


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _component(
    factor: str,
    contribution: float,
    *,
    source: str,
    observed_value: Any,
    explanation: str,
) -> dict[str, Any]:
    return {
        "factor": factor,
        "source": source,
        "observedValue": observed_value,
        "contribution": round(float(contribution), 6),
        "explanation": explanation,
    }


def attention_score_decomposition(record: dict[str, Any]) -> dict[str, Any]:
    """Explain the canonical Phase 7.0 operator-attention score.

    Contributions reproduce the exact deterministic weights used by
    fleet_decision_rules.attention_score().

    The score is an operational prioritization index only.

    It is not:
    - SHAP or model feature attribution
    - causal evidence
    - physical failure probability
    - reliability probability
    - safety probability
    - physical condition proof
    - physical RUL
    """

    gaps = coverage_gaps(record)
    components: list[dict[str, Any]] = []

    top_class = str(record.get("topClass") or "healthy")
    top_confidence = max(
        0.0,
        min(
            1.0,
            _number(record.get("topConfidence")),
        ),
    )

    if top_class != "healthy":
        components.append(
            _component(
                ATTENTION_FACTOR_MODEL_CONFIDENCE,
                top_confidence * 30.0,
                source="diagnostic_prediction",
                observed_value={
                    "topClass": top_class,
                    "topConfidence": top_confidence,
                },
                explanation=(
                    "Non-healthy model hypothesis confidence contributes "
                    "up to 30 operational attention points."
                ),
            )
        )

    review_priority = record.get("reviewPriority")
    review_weight = REVIEW_PRIORITY_WEIGHTS.get(
        review_priority,
        0.0,
    )

    if review_weight:
        components.append(
            _component(
                ATTENTION_FACTOR_REVIEW_PRIORITY,
                review_weight,
                source="diagnostic_case",
                observed_value=review_priority,
                explanation=(
                    "Case review priority contributes deterministic "
                    "operator-attention points."
                ),
            )
        )

    maintenance_tier = record.get("maintenanceTier")
    maintenance_weight = MAINTENANCE_TIER_WEIGHTS.get(
        maintenance_tier,
        0.0,
    )

    if maintenance_weight:
        components.append(
            _component(
                ATTENTION_FACTOR_MAINTENANCE_TIER,
                maintenance_weight,
                source="prognostic_workflow",
                observed_value=maintenance_tier,
                explanation=(
                    "Maintenance workflow tier contributes deterministic "
                    "operator-attention points."
                ),
            )
        )

    episode_state = record.get("episodeState")
    episode_weight = EPISODE_STATE_WEIGHTS.get(
        episode_state,
        0.0,
    )

    if episode_weight:
        components.append(
            _component(
                ATTENTION_FACTOR_EPISODE_STATE,
                episode_weight,
                source="diagnostic_episode",
                observed_value=episode_state,
                explanation=(
                    "Diagnostic episode state contributes deterministic "
                    "operator-attention points."
                ),
            )
        )

    for gap in gaps:
        gap_weight = COVERAGE_GAP_WEIGHTS.get(gap, 0.0)

        if not gap_weight:
            continue

        components.append(
            _component(
                f"{ATTENTION_FACTOR_GAP_PREFIX}{gap}",
                gap_weight,
                source="fleet_decision_coverage",
                observed_value=gap,
                explanation=(
                    "Operational coverage gap contributes deterministic "
                    "attention points."
                ),
            )
        )

    if bool(record.get("watchlisted")):
        components.append(
            _component(
                ATTENTION_FACTOR_WATCHLIST,
                2.0,
                source="prognostic_watchlist",
                observed_value=True,
                explanation=(
                    "Watchlist membership contributes two operational "
                    "attention points."
                ),
            )
        )

    raw_score = sum(
        float(component["contribution"])
        for component in components
    )

    canonical_score = attention_score(record, gaps)

    # A SCORE_CAP component represents only an actual Phase 7.0
    # 100-point cap. Normal three-decimal canonical rounding must not
    # be mislabeled as score capping.
    cap_applied = raw_score > 100.0

    cap_adjustment = (
        100.0 - raw_score
        if cap_applied
        else 0.0
    )

    if cap_applied:
        components.append(
            _component(
                ATTENTION_FACTOR_SCORE_CAP,
                cap_adjustment,
                source="fleet_decision_rule",
                observed_value=100.0,
                explanation=(
                    "Phase 7.0 caps the operational attention score at "
                    "100 points. This adjustment is present only when "
                    "the uncapped weighted score exceeds 100."
                ),
            )
        )

    explained_score = round(
        sum(
            float(component["contribution"])
            for component in components
        ),
        3,
    )

    reconciles = abs(
        explained_score - canonical_score
    ) < 0.001

    return {
        "rulesVersion": EVIDENCE_EXPLAINABILITY_RULES_VERSION,
        "attentionScore": canonical_score,
        "rawAttentionScore": round(raw_score, 3),
        "capApplied": cap_applied,
        "capAdjustment": round(cap_adjustment, 3),
        "explainedScore": explained_score,
        "reconciles": reconciles,
        "coverageGaps": gaps,
        "components": components,
        "interpretation": {
            "operationalAttentionOnly": True,
            "shapValues": False,
            "modelFeatureAttribution": False,
            "causalAttribution": False,
            "physicalFailureProbability": False,
            "physicalReliabilityProbability": False,
            "physicalConditionProof": False,
            "physicalRul": False,
        },
    }


def summarize_attention_explanations(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate deterministic score-factor representation across a fleet."""

    explanations = [
        attention_score_decomposition(record)
        for record in records
    ]

    factor_totals: dict[str, dict[str, float | int]] = {}

    for explanation in explanations:
        for component in explanation["components"]:
            factor = str(component["factor"])

            bucket = factor_totals.setdefault(
                factor,
                {
                    "vehicleCount": 0,
                    "totalContribution": 0.0,
                },
            )

            bucket["vehicleCount"] = int(
                bucket["vehicleCount"]
            ) + 1

            bucket["totalContribution"] = (
                float(bucket["totalContribution"])
                + float(component["contribution"])
            )

    factors = []

    for factor, values in sorted(
        factor_totals.items(),
        key=lambda item: (
            -float(item[1]["totalContribution"]),
            item[0],
        ),
    ):
        vehicle_count = int(values["vehicleCount"])
        total_contribution = float(
            values["totalContribution"]
        )

        factors.append(
            {
                "factor": factor,
                "vehicleCount": vehicle_count,
                "totalContribution": round(
                    total_contribution,
                    3,
                ),
                "meanContributionWhenPresent": round(
                    (
                        total_contribution
                        / vehicle_count
                    )
                    if vehicle_count
                    else 0.0,
                    3,
                ),
            }
        )

    return {
        "rulesVersion": EVIDENCE_EXPLAINABILITY_RULES_VERSION,
        "vehicleCount": len(records),
        "reconciledVehicleCount": sum(
            1
            for explanation in explanations
            if explanation["reconciles"]
        ),
        "cappedVehicleCount": sum(
            1
            for explanation in explanations
            if explanation["capApplied"]
        ),
        "factors": factors,
        "interpretation": {
            "operationalAttentionOnly": True,
            "fleetRepresentationOnly": True,
            "shapValues": False,
            "modelFeatureAttribution": False,
            "causalAttribution": False,
            "physicalRiskRanking": False,
        },
    }


def evidence_inventory(twin: dict[str, Any]) -> dict[str, Any]:
    """Describe which selected-run operational evidence layers are present.

    Presence means FleetMind has persisted/derived operational information for
    that layer. It does not prove physical component condition or causality.
    """

    model = twin.get("modelState") or {}
    diagnostic = twin.get("diagnosticState") or {}
    case = twin.get("caseState") or {}
    prognostic = twin.get("prognosticState") or {}
    maintenance = twin.get("maintenanceState") or {}
    automation = twin.get("automationState") or {}
    fleet_decision = twin.get("fleetDecisionState") or {}
    coverage = twin.get("coverageState") or {}

    observable_evidence = list(
        model.get("observableEvidence") or []
    )
    automation_actions = list(
        automation.get("actions") or []
    )
    coverage_gaps = list(
        coverage.get("coverageGaps") or []
    )

    prognostic_present = any(
        prognostic.get(key) is not None
        for key in (
            "maintenanceTier",
            "priorityScore",
            "recommendedReviewWindow",
            "trajectoryEligible",
        )
    )

    layers = [
        {
            "layer": "MODEL",
            "present": model.get("predictionId") is not None,
            "evidenceItemCount": len(observable_evidence),
            "sourceId": model.get("predictionId"),
        },
        {
            "layer": "DIAGNOSTIC",
            "present": diagnostic.get("episodeId") is not None,
            "evidenceItemCount": (
                1
                if diagnostic.get("episodeId") is not None
                else 0
            ),
            "sourceId": diagnostic.get("episodeId"),
        },
        {
            "layer": "CASE",
            "present": case.get("caseId") is not None,
            "evidenceItemCount": (
                1
                if case.get("caseId") is not None
                else 0
            ),
            "sourceId": case.get("caseId"),
        },
        {
            "layer": "PROGNOSTIC",
            "present": prognostic_present,
            "evidenceItemCount": (
                1 if prognostic_present else 0
            ),
            "sourceId": None,
        },
        {
            "layer": "MAINTENANCE",
            "present": maintenance.get("planId") is not None,
            "evidenceItemCount": (
                1
                if maintenance.get("planId") is not None
                else 0
            ),
            "sourceId": maintenance.get("planId"),
        },
        {
            "layer": "AUTOMATION",
            "present": bool(
                automation.get("actionIds")
            ),
            "evidenceItemCount": len(automation_actions),
            "sourceId": None,
        },
        {
            "layer": "FLEET_DECISION",
            "present": (
                fleet_decision.get("decisionState")
                is not None
            ),
            "evidenceItemCount": (
                1
                if fleet_decision.get("decisionState")
                is not None
                else 0
            ),
            "sourceId": None,
        },
        {
            "layer": "COVERAGE",
            "present": bool(coverage),
            "evidenceItemCount": len(coverage_gaps),
            "sourceId": None,
        },
    ]

    return {
        "rulesVersion": EVIDENCE_EXPLAINABILITY_RULES_VERSION,
        "vehicleId": twin.get("vehicleId"),
        "presentLayerCount": sum(
            1
            for layer in layers
            if layer["present"]
        ),
        "totalLayerCount": len(layers),
        "observableModelEvidenceCount": len(
            observable_evidence
        ),
        "coverageGapCount": len(coverage_gaps),
        "automationActionCount": len(
            automation_actions
        ),
        "layers": layers,
        "interpretation": {
            "evidencePresenceOnly": True,
            "usesPrivateFailureTruth": False,
            "failureMarkersExposed": False,
            "causalAttribution": False,
            "physicalConditionProof": False,
            "physicalFailureConfirmation": False,
        },
    }


def evidence_lineage(twin: dict[str, Any]) -> dict[str, Any]:
    """Build selected-run operational evidence/workflow lineage.

    Edges mean that FleetMind operational layers are connected in its data and
    workflow pipeline. They do not imply a causal physical relationship.
    """

    model = twin.get("modelState") or {}
    diagnostic = twin.get("diagnosticState") or {}
    case = twin.get("caseState") or {}
    prognostic = twin.get("prognosticState") or {}
    maintenance = twin.get("maintenanceState") or {}
    automation = twin.get("automationState") or {}
    fleet_decision = twin.get("fleetDecisionState") or {}
    coverage = twin.get("coverageState") or {}

    prognostic_present = any(
        prognostic.get(key) is not None
        for key in (
            "maintenanceTier",
            "priorityScore",
            "recommendedReviewWindow",
            "trajectoryEligible",
        )
    )

    nodes = [
        {
            "id": "model",
            "layer": "MODEL",
            "present": model.get("predictionId") is not None,
            "sourceId": model.get("predictionId"),
            "label": model.get("topClass"),
            "detail": {
                "topConfidence": model.get(
                    "topConfidence"
                ),
                "anchorTimestamp": model.get(
                    "anchorTimestamp"
                ),
                "anchorMileage": model.get(
                    "anchorMileage"
                ),
            },
        },
        {
            "id": "episode",
            "layer": "DIAGNOSTIC",
            "present": (
                diagnostic.get("episodeId") is not None
            ),
            "sourceId": diagnostic.get("episodeId"),
            "label": diagnostic.get("episodeState"),
            "detail": {
                "hypothesisClass": diagnostic.get(
                    "hypothesisClass"
                ),
                "isOpen": diagnostic.get("isOpen"),
            },
        },
        {
            "id": "case",
            "layer": "CASE",
            "present": case.get("caseId") is not None,
            "sourceId": case.get("caseId"),
            "label": case.get("status"),
            "detail": {
                "reviewPriority": case.get(
                    "reviewPriority"
                ),
                "assignedTo": case.get(
                    "assignedTo"
                ),
                "watchlisted": case.get(
                    "watchlisted"
                ),
            },
        },
        {
            "id": "prognostic",
            "layer": "PROGNOSTIC",
            "present": prognostic_present,
            "sourceId": None,
            "label": prognostic.get(
                "maintenanceTier"
            ),
            "detail": {
                "priorityScore": prognostic.get(
                    "priorityScore"
                ),
                "trajectoryEligible": prognostic.get(
                    "trajectoryEligible"
                ),
                "recommendedReviewWindow": (
                    prognostic.get(
                        "recommendedReviewWindow"
                    )
                ),
            },
        },
        {
            "id": "maintenance",
            "layer": "MAINTENANCE",
            "present": (
                maintenance.get("planId") is not None
            ),
            "sourceId": maintenance.get("planId"),
            "label": maintenance.get("state"),
            "detail": {
                "owner": maintenance.get("owner"),
                "targetMileage": maintenance.get(
                    "targetMileage"
                ),
            },
        },
        {
            "id": "automation",
            "layer": "AUTOMATION",
            "present": bool(
                automation.get("actionIds")
            ),
            "sourceId": None,
            "label": automation.get(
                "currentStatus"
            ),
            "detail": {
                "actionIds": list(
                    automation.get("actionIds") or []
                ),
                "pendingActionTypes": list(
                    automation.get(
                        "pendingActionTypes"
                    )
                    or []
                ),
            },
        },
        {
            "id": "fleet-decision",
            "layer": "FLEET_DECISION",
            "present": (
                fleet_decision.get("decisionState")
                is not None
            ),
            "sourceId": None,
            "label": fleet_decision.get(
                "decisionState"
            ),
            "detail": {
                "attentionScore": fleet_decision.get(
                    "attentionScore"
                ),
                "workloadUnits": fleet_decision.get(
                    "workloadUnits"
                ),
            },
        },
        {
            "id": "coverage",
            "layer": "COVERAGE",
            "present": bool(coverage),
            "sourceId": None,
            "label": (
                f"{len(coverage.get('coverageGaps') or [])} gaps"
            ),
            "detail": {
                "coverageGaps": list(
                    coverage.get("coverageGaps") or []
                ),
            },
        },
    ]

    present = {
        node["id"]: bool(node["present"])
        for node in nodes
    }

    candidate_edges = [
        (
            "model",
            "episode",
            "TEMPORALIZED_AS",
        ),
        (
            "episode",
            "case",
            "OPERATIONALIZED_AS",
        ),
        (
            "case",
            "prognostic",
            "REVIEWED_BY",
        ),
        (
            "prognostic",
            "maintenance",
            "INFORMS_WORKFLOW",
        ),
        (
            "prognostic",
            "automation",
            "EVALUATED_BY_POLICY",
        ),
        (
            "maintenance",
            "fleet-decision",
            "SYNTHESIZED_IN",
        ),
        (
            "automation",
            "fleet-decision",
            "SYNTHESIZED_IN",
        ),
        (
            "fleet-decision",
            "coverage",
            "ASSESSED_FOR",
        ),
    ]

    edges = [
        {
            "from": source,
            "to": target,
            "relation": relation,
            "causal": False,
        }
        for source, target, relation
        in candidate_edges
        if present.get(source)
        and present.get(target)
    ]

    active_nodes = [
        node
        for node in nodes
        if node["present"]
    ]

    return {
        "rulesVersion": EVIDENCE_EXPLAINABILITY_RULES_VERSION,
        "vehicleId": twin.get("vehicleId"),
        "nodes": active_nodes,
        "edges": edges,
        "lineagePath": [
            node["id"]
            for node in active_nodes
        ],
        "sourceVersions": dict(
            twin.get("sourceVersions") or {}
        ),
        "interpretation": {
            "workflowLineageOnly": True,
            "causalGraph": False,
            "causalAttribution": False,
            "physicalDependencyGraph": False,
            "physicalFailurePropagation": False,
            "usesPrivateFailureTruth": False,
            "failureMarkersExposed": False,
        },
    }
