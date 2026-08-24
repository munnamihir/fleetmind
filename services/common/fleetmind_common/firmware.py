from __future__ import annotations

from dataclasses import dataclass
from math import erfc, exp, log, sqrt
from typing import Iterable


@dataclass(frozen=True)
class FirmwareObservation:
    firmware: str
    pump_revision: str
    factory: str
    model: str
    mileage: float
    ambient_temp_c: float
    failed: bool
    risk_score: float = 0.0
    non_healthy: bool = False
    pump_current_a: float = 0.0


def mileage_band(mileage: float, width: int = 40000) -> str:
    start = int(max(0.0, mileage) // width) * width
    return f"{start // 1000}k-{(start + width) // 1000}k"


def ambient_band(temp_c: float) -> str:
    return "<30C" if temp_c < 30 else ">=30C"


def stratum_key(observation: FirmwareObservation) -> tuple[str, str, str]:
    # Coarsened exact matching. Hardware, accumulated use and environment are
    # the primary causal confounders in the synthetic scenario. Factory/model
    # remain available in the API for follow-up slicing, but matching on all
    # five fields over-fragments a 500-vehicle demo fleet and discards failures.
    return (
        observation.pump_revision,
        mileage_band(observation.mileage),
        ambient_band(observation.ambient_temp_c),
    )


def _safe_rate(failures: int, population: int) -> float:
    return failures / population if population else 0.0


def _risk_ratio_with_ci(
    target_failures: int,
    target_population: int,
    control_failures: int,
    control_population: int,
) -> tuple[float | None, float | None, float | None]:
    if target_population <= 0 or control_population <= 0:
        return None, None, None

    # Haldane-Anscombe correction is only used for the effect estimate when a
    # 2x2 cell is zero. Raw event counts/rates are returned separately.
    a = float(target_failures)
    b = float(target_population - target_failures)
    c = float(control_failures)
    d = float(control_population - control_failures)
    if min(a, b, c, d) == 0:
        a += 0.5
        b += 0.5
        c += 0.5
        d += 0.5

    target_rate = a / (a + b)
    control_rate = c / (c + d)
    if control_rate <= 0:
        return None, None, None

    rr = target_rate / control_rate
    se = sqrt(max(0.0, 1 / a - 1 / (a + b) + 1 / c - 1 / (c + d)))
    lower = exp(log(rr) - 1.96 * se)
    upper = exp(log(rr) + 1.96 * se)
    return rr, lower, upper


def _cmh(strata: list[dict]) -> tuple[float | None, float | None, float | None]:
    """Mantel-Haenszel common odds ratio and CMH chi-square p-value."""

    numerator_or = 0.0
    denominator_or = 0.0
    observed_minus_expected = 0.0
    variance = 0.0

    for row in strata:
        a = float(row["a"])
        b = float(row["b"])
        c = float(row["c"])
        d = float(row["d"])
        n = a + b + c + d
        if n <= 1:
            continue

        # Continuity correction only for the common odds-ratio estimate when
        # a stratum contains a zero cell. The CMH statistic uses raw counts.
        oa, ob, oc, od = a, b, c, d
        if min(oa, ob, oc, od) == 0:
            oa += 0.5
            ob += 0.5
            oc += 0.5
            od += 0.5
            on = oa + ob + oc + od
        else:
            on = n
        numerator_or += oa * od / on
        denominator_or += ob * oc / on

        exposed = a + b
        unexposed = c + d
        cases = a + c
        noncases = b + d
        expected_a = exposed * cases / n
        observed_minus_expected += a - expected_a
        variance += exposed * unexposed * cases * noncases / (n * n * (n - 1))

    common_or = numerator_or / denominator_or if denominator_or > 0 else None
    if variance <= 0:
        return common_or, None, None

    chi_square = (observed_minus_expected**2) / variance
    # Chi-square(df=1) survival function = erfc(sqrt(x/2)).
    p_value = erfc(sqrt(max(0.0, chi_square) / 2.0))
    return common_or, chi_square, p_value


def classify_regression(
    matched_population: int,
    total_failures: int,
    risk_ratio: float | None,
    p_value: float | None,
    absolute_risk_increase: float,
) -> str:
    if matched_population < 30 or total_failures < 2:
        return "insufficient_data"
    if risk_ratio is not None and p_value is not None and p_value < 0.01 and risk_ratio >= 2.0:
        return "critical_regression"
    if risk_ratio is not None and p_value is not None and p_value < 0.05 and risk_ratio >= 1.3:
        return "regression"
    if (risk_ratio is not None and risk_ratio >= 1.2) or absolute_risk_increase >= 0.02:
        return "watch"
    return "stable"


def compare_firmware(
    observations: Iterable[FirmwareObservation],
    target_firmware: str,
    control_firmware: str,
) -> dict:
    obs = [item for item in observations if item.firmware in {target_firmware, control_firmware}]

    grouped: dict[tuple[str, str, str], dict[str, list[FirmwareObservation]]] = {}
    for item in obs:
        grouped.setdefault(stratum_key(item), {}).setdefault(item.firmware, []).append(item)

    matched: list[dict] = []
    target_rows: list[FirmwareObservation] = []
    control_rows: list[FirmwareObservation] = []

    for key, by_firmware in grouped.items():
        target = by_firmware.get(target_firmware, [])
        control = by_firmware.get(control_firmware, [])
        if not target or not control:
            continue

        target_rows.extend(target)
        control_rows.extend(control)
        a = sum(1 for item in target if item.failed)
        c = sum(1 for item in control if item.failed)
        matched.append(
            {
                "key": key,
                "a": a,
                "b": len(target) - a,
                "c": c,
                "d": len(control) - c,
                "targetPopulation": len(target),
                "controlPopulation": len(control),
            }
        )

    target_failures = sum(1 for item in target_rows if item.failed)
    control_failures = sum(1 for item in control_rows if item.failed)
    target_population = len(target_rows)
    control_population = len(control_rows)
    target_rate = _safe_rate(target_failures, target_population)
    control_rate = _safe_rate(control_failures, control_population)
    absolute_risk_increase = target_rate - control_rate
    rr, rr_lower, rr_upper = _risk_ratio_with_ci(
        target_failures,
        target_population,
        control_failures,
        control_population,
    )
    common_or, chi_square, p_value = _cmh(matched)

    target_avg_risk = sum(item.risk_score for item in target_rows) / target_population if target_population else 0.0
    control_avg_risk = sum(item.risk_score for item in control_rows) / control_population if control_population else 0.0
    target_nonhealthy = _safe_rate(sum(1 for item in target_rows if item.non_healthy), target_population)
    control_nonhealthy = _safe_rate(sum(1 for item in control_rows if item.non_healthy), control_population)
    target_current = sum(item.pump_current_a for item in target_rows) / target_population if target_population else 0.0
    control_current = sum(item.pump_current_a for item in control_rows) / control_population if control_population else 0.0

    matched_population = target_population + control_population
    classification = classify_regression(
        matched_population=matched_population,
        total_failures=target_failures + control_failures,
        risk_ratio=rr,
        p_value=p_value,
        absolute_risk_increase=absolute_risk_increase,
    )

    return {
        "targetFirmware": target_firmware,
        "controlFirmware": control_firmware,
        "matching": {
            "dimensions": ["pump_revision", "40k_mileage_band", "ambient_temperature_band"],
            "matchedStrata": len(matched),
            "matchedPopulation": matched_population,
            "targetPopulation": target_population,
            "controlPopulation": control_population,
        },
        "outcomes": {
            "targetFailures": target_failures,
            "controlFailures": control_failures,
            "targetFailureRate": target_rate,
            "controlFailureRate": control_rate,
            "absoluteRiskIncrease": absolute_risk_increase,
            "riskRatio": rr,
            "riskRatio95CI": [rr_lower, rr_upper] if rr_lower is not None and rr_upper is not None else None,
            "mantelHaenszelOddsRatio": common_or,
            "cmhChiSquare": chi_square,
            "pValue": p_value,
        },
        "telemetrySignals": {
            "targetAverageRisk": target_avg_risk,
            "controlAverageRisk": control_avg_risk,
            "averageRiskDelta": target_avg_risk - control_avg_risk,
            "targetNonHealthyRate": target_nonhealthy,
            "controlNonHealthyRate": control_nonhealthy,
            "nonHealthyRateDelta": target_nonhealthy - control_nonhealthy,
            "targetPumpCurrentA": target_current,
            "controlPumpCurrentA": control_current,
            "pumpCurrentDeltaA": target_current - control_current,
        },
        "classification": classification,
    }


def hardware_interactions(
    observations: Iterable[FirmwareObservation],
    target_firmware: str,
    control_firmware: str,
) -> list[dict]:
    obs = list(observations)
    revisions = sorted({item.pump_revision for item in obs})
    rows: list[dict] = []

    for revision in revisions:
        scoped = [item for item in obs if item.pump_revision == revision]
        target = [item for item in scoped if item.firmware == target_firmware]
        control = [item for item in scoped if item.firmware == control_firmware]
        if not target or not control:
            continue

        target_failures = sum(1 for item in target if item.failed)
        control_failures = sum(1 for item in control if item.failed)
        target_rate = _safe_rate(target_failures, len(target))
        control_rate = _safe_rate(control_failures, len(control))
        rr, lower, upper = _risk_ratio_with_ci(target_failures, len(target), control_failures, len(control))
        target_risk = sum(item.risk_score for item in target) / len(target)
        control_risk = sum(item.risk_score for item in control) / len(control)

        rows.append(
            {
                "pumpRevision": revision,
                "targetPopulation": len(target),
                "controlPopulation": len(control),
                "targetFailures": target_failures,
                "controlFailures": control_failures,
                "targetFailureRate": target_rate,
                "controlFailureRate": control_rate,
                "riskRatio": rr,
                "riskRatio95CI": [lower, upper] if lower is not None and upper is not None else None,
                "absoluteRiskIncrease": target_rate - control_rate,
                "targetAverageRisk": target_risk,
                "controlAverageRisk": control_risk,
                "averageRiskDelta": target_risk - control_risk,
            }
        )

    return sorted(rows, key=lambda row: (row["absoluteRiskIncrease"], row["averageRiskDelta"]), reverse=True)
