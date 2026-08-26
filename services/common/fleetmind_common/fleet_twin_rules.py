from __future__ import annotations

from collections import defaultdict
from typing import Any

from fleetmind_common.vehicle_twin_rules import current_automation_status


FLEET_TWIN_RULES_VERSION = "fm-fleet-twin-7.2-v1"

DIMENSION_MODEL = "model"
DIMENSION_FACTORY = "factory"
DIMENSION_FIRMWARE = "firmware"
DIMENSION_PUMP_REVISION = "pumpRevision"
DIMENSION_HYPOTHESIS_CLASS = "hypothesisClass"
DIMENSION_DECISION_STATE = "decisionState"
DIMENSION_MAINTENANCE_TIER = "maintenanceTier"
DIMENSION_REVIEW_PRIORITY = "reviewPriority"
DIMENSION_AUTOMATION_STATUS = "automationStatus"

FLEET_TWIN_DIMENSIONS = (
    DIMENSION_MODEL,
    DIMENSION_FACTORY,
    DIMENSION_FIRMWARE,
    DIMENSION_PUMP_REVISION,
    DIMENSION_HYPOTHESIS_CLASS,
    DIMENSION_DECISION_STATE,
    DIMENSION_MAINTENANCE_TIER,
    DIMENSION_REVIEW_PRIORITY,
    DIMENSION_AUTOMATION_STATUS,
)

EXPOSURE_MEASURE_ATTENTION = "attention"
EXPOSURE_MEASURE_NONHEALTHY = "nonHealthy"
EXPOSURE_MEASURE_CASE = "case"
EXPOSURE_MEASURE_COVERAGE_GAP = "coverageGap"

FLEET_TWIN_EXPOSURE_MEASURES = (
    EXPOSURE_MEASURE_ATTENTION,
    EXPOSURE_MEASURE_NONHEALTHY,
    EXPOSURE_MEASURE_CASE,
    EXPOSURE_MEASURE_COVERAGE_GAP,
)


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _pct(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 3)


def _rate_ratio(cohort_rate_pct: float, fleet_rate_pct: float) -> float | None:
    """
    Return descriptive cohort-rate / fleet-rate representation.

    This is not relative physical failure risk, reliability risk, causal effect,
    or calibrated probability.
    """
    if fleet_rate_pct <= 0.0:
        return None
    return round(cohort_rate_pct / fleet_rate_pct, 3)


def _dimension_value(record: dict[str, Any], dimension: str) -> str:
    if dimension not in FLEET_TWIN_DIMENSIONS:
        raise ValueError(f"Unsupported fleet twin dimension: {dimension}")

    if dimension == DIMENSION_HYPOTHESIS_CLASS:
        value = record.get("topClass")
    elif dimension == DIMENSION_AUTOMATION_STATUS:
        value = record.get("automationStatus")
        if value is None:
            value = current_automation_status(
                list(record.get("automationStatuses") or [])
            )
    else:
        value = record.get(dimension)

    if value is None or str(value).strip() == "":
        return "NONE"

    return str(value)


def _is_attention(record: dict[str, Any]) -> bool:
    return str(record.get("decisionState") or "NOMINAL") != "NOMINAL"


def _is_nonhealthy(record: dict[str, Any]) -> bool:
    return str(record.get("topClass") or "healthy") != "healthy"


def _has_case(record: dict[str, Any]) -> bool:
    return record.get("caseId") is not None


def _has_coverage_gap(record: dict[str, Any]) -> bool:
    return bool(record.get("coverageGaps") or [])


def _coverage_gap_instances(record: dict[str, Any]) -> int:
    return len(record.get("coverageGaps") or [])


def fleet_exposure_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)

    attention_count = sum(1 for record in records if _is_attention(record))
    nonhealthy_count = sum(1 for record in records if _is_nonhealthy(record))
    case_count = sum(1 for record in records if _has_case(record))
    gap_vehicle_count = sum(1 for record in records if _has_coverage_gap(record))
    gap_instances = sum(_coverage_gap_instances(record) for record in records)

    workload = round(
        sum(_safe_float(record.get("workloadUnits")) for record in records),
        2,
    )
    mean_attention = (
        round(
            sum(_safe_float(record.get("attentionScore")) for record in records)
            / total,
            3,
        )
        if total
        else 0.0
    )

    return {
        "populationCount": total,
        "attentionCount": attention_count,
        "attentionRatePct": _pct(attention_count, total),
        "nonHealthyCount": nonhealthy_count,
        "nonHealthyRatePct": _pct(nonhealthy_count, total),
        "caseCount": case_count,
        "caseRatePct": _pct(case_count, total),
        "coverageGapVehicleCount": gap_vehicle_count,
        "coverageGapRatePct": _pct(gap_vehicle_count, total),
        "coverageGapInstances": gap_instances,
        "totalWorkloadUnits": workload,
        "workloadUnitsPer100Vehicles": (
            round((workload / total) * 100.0, 3)
            if total
            else 0.0
        ),
        "meanAttentionScore": mean_attention,
    }


def cohort_exposure_rows(
    records: list[dict[str, Any]],
    dimension: str,
) -> list[dict[str, Any]]:
    """
    Build normalized operational exposure rows for one cohort dimension.

    Counts describe volume.
    Rates normalize by cohort population.
    rateToFleetRatio compares cohort rate to the selected-run fleet rate.

    These are descriptive operational representations only. They are not
    physical failure probabilities, relative risk, reliability estimates,
    causal effects, or model feature attribution.
    """
    if dimension not in FLEET_TWIN_DIMENSIONS:
        raise ValueError(f"Unsupported fleet twin dimension: {dimension}")

    fleet = fleet_exposure_summary(records)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[_dimension_value(record, dimension)].append(record)

    rows: list[dict[str, Any]] = []

    for value, cohort_records in grouped.items():
        summary = fleet_exposure_summary(cohort_records)

        rows.append(
            {
                "dimension": dimension,
                "value": value,
                **summary,
                "populationSharePct": _pct(
                    summary["populationCount"],
                    fleet["populationCount"],
                ),
                "rateToFleetRatio": {
                    "attention": _rate_ratio(
                        summary["attentionRatePct"],
                        fleet["attentionRatePct"],
                    ),
                    "nonHealthy": _rate_ratio(
                        summary["nonHealthyRatePct"],
                        fleet["nonHealthyRatePct"],
                    ),
                    "case": _rate_ratio(
                        summary["caseRatePct"],
                        fleet["caseRatePct"],
                    ),
                    "coverageGap": _rate_ratio(
                        summary["coverageGapRatePct"],
                        fleet["coverageGapRatePct"],
                    ),
                },
            }
        )

    return sorted(
        rows,
        key=lambda row: (
            -int(row["populationCount"]),
            str(row["value"]),
        ),
    )


def fleet_cohort_exposure(
    records: list[dict[str, Any]],
    dimension: str,
) -> dict[str, Any]:
    fleet = fleet_exposure_summary(records)

    return {
        "rulesVersion": FLEET_TWIN_RULES_VERSION,
        "dimension": dimension,
        "fleetBaseline": fleet,
        "cohorts": cohort_exposure_rows(records, dimension),
        "interpretation": (
            "Counts describe operational volume; rates normalize by cohort "
            "population. rateToFleetRatio is the cohort rate divided by the "
            "selected-run fleet rate. It is descriptive representation only, "
            "not physical failure risk, reliability probability, causal effect, "
            "RUL, or model feature attribution."
        ),
    }


def exposure_measure_rate(
    row: dict[str, Any],
    measure: str,
) -> float:
    if measure == EXPOSURE_MEASURE_ATTENTION:
        return _safe_float(row.get("attentionRatePct"))
    if measure == EXPOSURE_MEASURE_NONHEALTHY:
        return _safe_float(row.get("nonHealthyRatePct"))
    if measure == EXPOSURE_MEASURE_CASE:
        return _safe_float(row.get("caseRatePct"))
    if measure == EXPOSURE_MEASURE_COVERAGE_GAP:
        return _safe_float(row.get("coverageGapRatePct"))

    raise ValueError(f"Unsupported fleet twin exposure measure: {measure}")


def compare_cohort_exposure(
    reference: dict[str, Any],
    candidate: dict[str, Any],
    *,
    measure: str,
) -> dict[str, Any]:
    if measure not in FLEET_TWIN_EXPOSURE_MEASURES:
        raise ValueError(f"Unsupported fleet twin exposure measure: {measure}")

    reference_rate = exposure_measure_rate(reference, measure)
    candidate_rate = exposure_measure_rate(candidate, measure)

    rate_ratio = (
        round(candidate_rate / reference_rate, 3)
        if reference_rate > 0.0
        else None
    )

    return {
        "dimension": reference.get("dimension"),
        "measure": measure,
        "referenceValue": reference.get("value"),
        "candidateValue": candidate.get("value"),
        "referencePopulationCount": int(
            reference.get("populationCount") or 0
        ),
        "candidatePopulationCount": int(
            candidate.get("populationCount") or 0
        ),
        "referenceRatePct": round(reference_rate, 3),
        "candidateRatePct": round(candidate_rate, 3),
        "rateDeltaPctPoints": round(candidate_rate - reference_rate, 3),
        "candidateToReferenceRateRatio": rate_ratio,
        "interpretation": (
            "Comparison is normalized operational representation within the "
            "selected run. It is not relative physical failure risk, causal "
            "effect, reliability probability, or model attribution."
        ),
    }
