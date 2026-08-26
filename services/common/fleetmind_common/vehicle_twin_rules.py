from __future__ import annotations

from copy import deepcopy
from typing import Any

VEHICLE_TWIN_RULES_VERSION = "fm-vehicle-operational-twin-7.1-v1"

TWIN_LAYER_MODEL = "MODEL"
TWIN_LAYER_DIAGNOSTIC = "DIAGNOSTIC"
TWIN_LAYER_CASE = "CASE"
TWIN_LAYER_PROGNOSTIC = "PROGNOSTIC"
TWIN_LAYER_MAINTENANCE = "MAINTENANCE"
TWIN_LAYER_AUTOMATION = "AUTOMATION"
TWIN_LAYER_FLEET_DECISION = "FLEET_DECISION"
TWIN_LAYER_COVERAGE = "COVERAGE"

TWIN_LAYERS = (
    TWIN_LAYER_MODEL,
    TWIN_LAYER_DIAGNOSTIC,
    TWIN_LAYER_CASE,
    TWIN_LAYER_PROGNOSTIC,
    TWIN_LAYER_MAINTENANCE,
    TWIN_LAYER_AUTOMATION,
    TWIN_LAYER_FLEET_DECISION,
    TWIN_LAYER_COVERAGE,
)

AUTOMATION_STATUS_ORDER = {
    "PENDING_APPROVAL": 1,
    "APPROVED": 2,
    "REJECTED": 3,
    "EXECUTED": 4,
}


def active_twin_layers(record: dict[str, Any]) -> list[str]:
    """Return operational layers that currently contain state.

    Layer presence is descriptive. A healthy vehicle is expected to have fewer
    active workflow layers; this is not a data-quality or physical-health grade.
    """
    layers: list[str] = []
    model = record.get("modelState") or {}
    diagnostic = record.get("diagnosticState") or {}
    case = record.get("caseState") or {}
    prognostic = record.get("prognosticState") or {}
    maintenance = record.get("maintenanceState") or {}
    automation = record.get("automationState") or {}
    fleet = record.get("fleetDecisionState") or {}
    coverage = record.get("coverageState") or {}

    if model.get("topClass") is not None:
        layers.append(TWIN_LAYER_MODEL)
    if diagnostic.get("episodeId") is not None:
        layers.append(TWIN_LAYER_DIAGNOSTIC)
    if case.get("caseId") is not None:
        layers.append(TWIN_LAYER_CASE)
    if prognostic.get("maintenanceTier") is not None:
        layers.append(TWIN_LAYER_PROGNOSTIC)
    if maintenance.get("planId") is not None:
        layers.append(TWIN_LAYER_MAINTENANCE)
    if automation.get("actionIds"):
        layers.append(TWIN_LAYER_AUTOMATION)
    if fleet.get("decisionState") is not None:
        layers.append(TWIN_LAYER_FLEET_DECISION)
    if coverage.get("coverageGaps") is not None:
        layers.append(TWIN_LAYER_COVERAGE)
    return layers


def layer_presence_payload(record: dict[str, Any]) -> dict[str, Any]:
    active = active_twin_layers(record)
    return {
        "activeLayers": active,
        "activeLayerCount": len(active),
        "availableLayerCount": len(TWIN_LAYERS),
        "layerPresencePct": round((len(active) / len(TWIN_LAYERS)) * 100.0, 1),
        "interpretation": (
            "Layer presence describes which operational records currently exist. "
            "It is not a physical-health, completeness, safety, or data-quality score."
        ),
    }


def current_automation_status(statuses: list[str]) -> str | None:
    if not statuses:
        return None
    return max(statuses, key=lambda status: AUTOMATION_STATUS_ORDER.get(str(status), 0))


def canonical_twin_state(record: dict[str, Any]) -> dict[str, Any]:
    """Stable operational state used for snapshot hashing.

    Volatile latest telemetry mileage/time are excluded so an otherwise unchanged
    operational twin checkpoint remains idempotent.
    """
    context = deepcopy(record.get("vehicleContext") or {})
    return {
        "vehicleId": record.get("vehicleId"),
        "runId": record.get("runId"),
        "experimentId": record.get("experimentId"),
        "lineage": record.get("lineage"),
        "vehicleContext": context,
        "modelState": deepcopy(record.get("modelState") or {}),
        "diagnosticState": deepcopy(record.get("diagnosticState") or {}),
        "caseState": deepcopy(record.get("caseState") or {}),
        "prognosticState": deepcopy(record.get("prognosticState") or {}),
        "maintenanceState": deepcopy(record.get("maintenanceState") or {}),
        "automationState": deepcopy(record.get("automationState") or {}),
        "fleetDecisionState": deepcopy(record.get("fleetDecisionState") or {}),
        "coverageState": deepcopy(record.get("coverageState") or {}),
        "sourceVersions": deepcopy(record.get("sourceVersions") or {}),
    }


def twin_list_record(decision_record: dict[str, Any]) -> dict[str, Any]:
    action_ids = list(decision_record.get("automationActionIds") or [])
    active_layers = [TWIN_LAYER_MODEL, TWIN_LAYER_FLEET_DECISION, TWIN_LAYER_COVERAGE]
    if decision_record.get("episodeId") is not None:
        active_layers.append(TWIN_LAYER_DIAGNOSTIC)
    if decision_record.get("caseId") is not None:
        active_layers.append(TWIN_LAYER_CASE)
    if decision_record.get("maintenanceTier") is not None:
        active_layers.append(TWIN_LAYER_PROGNOSTIC)
    if decision_record.get("maintenancePlanId") is not None:
        active_layers.append(TWIN_LAYER_MAINTENANCE)
    if action_ids:
        active_layers.append(TWIN_LAYER_AUTOMATION)
    return {
        "vehicleId": decision_record.get("vehicleId"),
        "topClass": decision_record.get("topClass"),
        "topConfidence": decision_record.get("topConfidence"),
        "decisionState": decision_record.get("decisionState"),
        "attentionScore": decision_record.get("attentionScore"),
        "workloadUnits": decision_record.get("workloadUnits"),
        "caseId": decision_record.get("caseId"),
        "caseStatus": decision_record.get("caseStatus"),
        "episodeId": decision_record.get("episodeId"),
        "episodeState": decision_record.get("episodeState"),
        "maintenanceTier": decision_record.get("maintenanceTier"),
        "maintenancePlanState": decision_record.get("maintenancePlanState"),
        "automationStatus": current_automation_status(list(decision_record.get("automationStatuses") or [])),
        "coverageGaps": list(decision_record.get("coverageGaps") or []),
        "activeLayers": active_layers,
        "activeLayerCount": len(active_layers),
    }


def compare_twin_states(reference: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Exact operational-state comparison, not learned/physical similarity."""
    ref_context = reference.get("vehicleContext") or {}
    cand_context = candidate.get("vehicleContext") or {}
    ref_model = reference.get("modelState") or {}
    cand_model = candidate.get("modelState") or {}
    ref_fleet = reference.get("fleetDecisionState") or {}
    cand_fleet = candidate.get("fleetDecisionState") or {}
    ref_cov = set((reference.get("coverageState") or {}).get("coverageGaps") or [])
    cand_cov = set((candidate.get("coverageState") or {}).get("coverageGaps") or [])
    metadata_matches = {
        key: ref_context.get(key) == cand_context.get(key)
        for key in ("model", "factory", "firmware", "pumpRevision")
    }
    return {
        "referenceVehicleId": reference.get("vehicleId"),
        "candidateVehicleId": candidate.get("vehicleId"),
        "sameHypothesisClass": ref_model.get("topClass") == cand_model.get("topClass"),
        "sameDecisionState": ref_fleet.get("decisionState") == cand_fleet.get("decisionState"),
        "metadataMatches": metadata_matches,
        "sharedCoverageGaps": sorted(ref_cov & cand_cov),
        "referenceOnlyCoverageGaps": sorted(ref_cov - cand_cov),
        "candidateOnlyCoverageGaps": sorted(cand_cov - ref_cov),
        "attentionScoreDelta": round(float(cand_fleet.get("attentionScore") or 0) - float(ref_fleet.get("attentionScore") or 0), 3),
        "workloadUnitsDelta": round(float(cand_fleet.get("workloadUnits") or 0) - float(ref_fleet.get("workloadUnits") or 0), 2),
        "interpretation": (
            "Comparison is deterministic operational-state differencing. It is not a "
            "probability of shared failure, causal relationship, physical similarity, "
            "or model feature attribution."
        ),
    }
