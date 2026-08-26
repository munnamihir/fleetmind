from __future__ import annotations

import math

PROGNOSTIC_RULES_VERSION = "fm-diagnostic-prognostics-6.12-v1"

TARGET_HYPOTHESIS_CONFIDENCE = 0.95
FIT_WINDOW_POINTS = 16
MIN_TRAJECTORY_POINTS = 8
BACKTEST_HOLDOUT_MIN_POINTS = 4
MIN_POSITIVE_SLOPE_PER_1K_MILES = 0.002
MAX_EXPERIMENTAL_HORIZON_MILES = 25000.0

MAINTENANCE_STATES = (
    "REVIEW",
    "PLANNED",
    "SCHEDULED",
    "DEFERRED",
    "COMPLETED",
)

MAINTENANCE_ACTIVITY_CREATED = "PLAN_CREATED"
MAINTENANCE_ACTIVITY_STATE_CHANGED = "STATE_CHANGED"
MAINTENANCE_ACTIVITY_OWNER_CHANGED = "OWNER_CHANGED"
MAINTENANCE_ACTIVITY_TARGET_CHANGED = "TARGET_CHANGED"
MAINTENANCE_ACTIVITY_NOTE_ADDED = "NOTE_ADDED"

MAINTENANCE_TIERS = (
    "URGENT_REVIEW",
    "PLAN_SERVICE",
    "MONITOR",
    "ROUTINE_REVIEW",
)


def fit_trajectory(points: list[tuple[float, float]]) -> dict | None:
    """Fit confidence vs mileage using an ordinary least-squares line.

    Mileage is expressed in thousands of miles relative to the first point for
    numerical stability. The returned slope uncertainty is an uncalibrated fit
    band, not a validated probabilistic confidence interval.
    """

    cleaned = sorted(
        {
            (float(mileage), float(confidence))
            for mileage, confidence in points
            if math.isfinite(float(mileage))
            and math.isfinite(float(confidence))
        }
    )
    if len(cleaned) < 2:
        return None

    x0 = cleaned[0][0]
    xs = [(mileage - x0) / 1000.0 for mileage, _ in cleaned]
    ys = [confidence for _, confidence in cleaned]
    n = len(cleaned)

    x_bar = sum(xs) / n
    y_bar = sum(ys) / n
    sxx = sum((x - x_bar) ** 2 for x in xs)
    if sxx <= 0.0:
        return None

    sxy = sum(
        (x - x_bar) * (y - y_bar)
        for x, y in zip(xs, ys)
    )
    slope = sxy / sxx
    intercept = y_bar - slope * x_bar

    fitted = [intercept + slope * x for x in xs]
    sse = sum((y - y_hat) ** 2 for y, y_hat in zip(ys, fitted))
    sst = sum((y - y_bar) ** 2 for y in ys)
    r_squared = 1.0 - (sse / sst) if sst > 0 else 1.0

    if n > 2:
        residual_variance = sse / (n - 2)
        slope_se = math.sqrt(max(0.0, residual_variance / sxx))
    else:
        slope_se = 0.0

    return {
        "points": n,
        "startMileage": cleaned[0][0],
        "latestMileage": cleaned[-1][0],
        "latestConfidence": cleaned[-1][1],
        "slopePer1kMiles": slope,
        "slopeStdErrorPer1kMiles": slope_se,
        "rSquared": max(0.0, min(1.0, r_squared)),
        "observedSpanMiles": max(0.0, cleaned[-1][0] - cleaned[0][0]),
    }


def estimate_threshold_horizon(
    *,
    latest_confidence: float,
    slope_per_1k_miles: float,
    slope_std_error_per_1k_miles: float,
    threshold: float = TARGET_HYPOTHESIS_CONFIDENCE,
) -> dict:
    """Estimate distance to a model-confidence threshold.

    This is an extrapolation of a model-hypothesis trajectory. It is not
    physical remaining useful life, a failure-time estimate, or calibrated
    physical-failure risk.
    """

    latest = float(latest_confidence)
    slope = float(slope_per_1k_miles)
    slope_se = max(0.0, float(slope_std_error_per_1k_miles))

    if latest >= threshold:
        return {
            "estimatedMilesToThreshold": 0.0,
            "lowerBandMiles": 0.0,
            "upperBandMiles": 0.0,
            "withinExperimentalWindow": True,
            "thresholdAlreadyReached": True,
        }

    if slope < MIN_POSITIVE_SLOPE_PER_1K_MILES:
        return {
            "estimatedMilesToThreshold": None,
            "lowerBandMiles": None,
            "upperBandMiles": None,
            "withinExperimentalWindow": False,
            "thresholdAlreadyReached": False,
        }

    delta = threshold - latest
    estimate = (delta / slope) * 1000.0

    upper_slope = slope + 1.96 * slope_se
    lower_slope = slope - 1.96 * slope_se

    lower_miles = (
        (delta / upper_slope) * 1000.0
        if upper_slope > 0
        else None
    )
    upper_miles = (
        (delta / lower_slope) * 1000.0
        if lower_slope >= MIN_POSITIVE_SLOPE_PER_1K_MILES
        else None
    )

    return {
        "estimatedMilesToThreshold": max(0.0, estimate),
        "lowerBandMiles": (
            max(0.0, lower_miles)
            if lower_miles is not None
            else None
        ),
        "upperBandMiles": (
            max(0.0, upper_miles)
            if upper_miles is not None
            else None
        ),
        "withinExperimentalWindow": (
            0.0 <= estimate <= MAX_EXPERIMENTAL_HORIZON_MILES
        ),
        "thresholdAlreadyReached": False,
    }


def maintenance_priority(
    *,
    review_priority: str,
    episode_state: str,
    latest_confidence: float | None,
    slope_per_1k_miles: float | None,
    estimated_miles_to_threshold: float | None,
    watchlisted: bool,
) -> dict:
    """Deterministic operational review heuristic, not physical failure risk."""

    score = {
        "HIGH": 35.0,
        "MEDIUM": 20.0,
        "LOW": 5.0,
    }.get(review_priority, 0.0)

    confidence = max(0.0, min(1.0, float(latest_confidence or 0.0)))
    score += confidence * 25.0

    slope = max(0.0, float(slope_per_1k_miles or 0.0))
    score += min(20.0, (slope / 0.05) * 20.0)

    if estimated_miles_to_threshold is not None:
        horizon = max(0.0, float(estimated_miles_to_threshold))
        score += max(
            0.0,
            15.0 * (
                1.0
                - min(horizon, MAX_EXPERIMENTAL_HORIZON_MILES)
                / MAX_EXPERIMENTAL_HORIZON_MILES
            ),
        )

    score += {
        "DESTABILIZED": 10.0,
        "STABILIZED": 5.0,
        "EVOLVING": 3.0,
        "EMERGING": 2.0,
    }.get(episode_state, 0.0)

    if watchlisted:
        score += 5.0

    score = min(100.0, score)

    if score >= 70.0:
        tier = "URGENT_REVIEW"
    elif score >= 50.0:
        tier = "PLAN_SERVICE"
    elif score >= 30.0:
        tier = "MONITOR"
    else:
        tier = "ROUTINE_REVIEW"

    horizon = estimated_miles_to_threshold
    if horizon is None:
        window = "TRACK_TRAJECTORY"
    elif horizon <= 0:
        window = "REVIEW_NOW"
    elif horizon <= 2500:
        window = "WITHIN_2500_MI"
    elif horizon <= 7500:
        window = "WITHIN_7500_MI"
    elif horizon <= MAX_EXPERIMENTAL_HORIZON_MILES:
        window = "WITHIN_25000_MI"
    else:
        window = "TRACK_TRAJECTORY"

    return {
        "priorityScore": round(score, 3),
        "maintenanceTier": tier,
        "recommendedReviewWindow": window,
    }


def backtest_threshold_horizon(
    points: list[tuple[float, float]],
) -> dict | None:
    """Backtest threshold-horizon extrapolation against future replay points.

    The target is a future crossing of the model-hypothesis confidence
    threshold, not a physical failure event.
    """

    cleaned = sorted(
        {
            (float(mileage), float(confidence))
            for mileage, confidence in points
        }
    )
    if len(cleaned) < MIN_TRAJECTORY_POINTS + BACKTEST_HOLDOUT_MIN_POINTS:
        return None

    split = max(
        MIN_TRAJECTORY_POINTS,
        int(len(cleaned) * 0.65),
    )
    split = min(
        split,
        len(cleaned) - BACKTEST_HOLDOUT_MIN_POINTS,
    )

    prefix = cleaned[:split]
    future = cleaned[split:]
    fit_points = prefix[-FIT_WINDOW_POINTS:]
    fit = fit_trajectory(fit_points)
    if fit is None:
        return None

    horizon = estimate_threshold_horizon(
        latest_confidence=fit["latestConfidence"],
        slope_per_1k_miles=fit["slopePer1kMiles"],
        slope_std_error_per_1k_miles=fit[
            "slopeStdErrorPer1kMiles"
        ],
    )

    origin_mileage = prefix[-1][0]
    observed_crossing = next(
        (
            mileage
            for mileage, confidence in future
            if confidence >= TARGET_HYPOTHESIS_CONFIDENCE
        ),
        None,
    )
    observed_miles = (
        max(0.0, observed_crossing - origin_mileage)
        if observed_crossing is not None
        else None
    )
    predicted_miles = horizon["estimatedMilesToThreshold"]

    return {
        "originMileage": origin_mileage,
        "predictedMilesToThreshold": predicted_miles,
        "observedFutureCrossingMiles": observed_miles,
        "absoluteErrorMiles": (
            abs(float(predicted_miles) - float(observed_miles))
            if predicted_miles is not None
            and observed_miles is not None
            else None
        ),
        "predictedCrossing": predicted_miles is not None,
        "observedFutureCrossing": observed_miles is not None,
    }
