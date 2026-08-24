from __future__ import annotations

from dataclasses import dataclass
from math import exp, log
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class ReliabilityObservation:
    """A component lifetime observation.

    time is typically odometer mileage. event=True means a failure was observed;
    event=False means the unit is right-censored at the latest known mileage.
    """

    time: float
    event: bool


@dataclass(frozen=True)
class WeibullFit:
    beta: float
    eta: float
    b10: float
    b50: float
    failure_behavior: str

    def reliability(self, time: float) -> float:
        if time <= 0:
            return 1.0
        return exp(-((time / self.eta) ** self.beta))


def _failure_behavior(beta: float) -> str:
    if beta < 0.9:
        return "infant_mortality"
    if beta <= 1.1:
        return "random_failure"
    return "wear_out"


def _logsumexp(values: list[float]) -> float:
    maximum = max(values)
    return maximum + log(sum(exp(v - maximum) for v in values))


def fit_weibull_right_censored(
    observations: Iterable[ReliabilityObservation],
) -> WeibullFit | None:
    """Fit a 2-parameter Weibull distribution with right-censored data.

    This profiles eta out of the likelihood and solves the score equation for
    beta using bisection. It intentionally avoids a heavyweight numerical
    dependency so the reliability math is transparent and testable.
    """

    obs = [o for o in observations if o.time > 0]
    failures = [o for o in obs if o.event]
    r = len(failures)
    if len(obs) < 3 or r < 2:
        return None

    log_times = [log(o.time) for o in obs]
    failure_log_sum = sum(log(o.time) for o in failures)

    def score(beta: float) -> float:
        weighted_logs = [beta * lt for lt in log_times]
        normalizer = _logsumexp(weighted_logs)
        weights = [exp(v - normalizer) for v in weighted_logs]
        weighted_mean_log_t = sum(w * lt for w, lt in zip(weights, log_times))
        return r / beta + failure_log_sum - r * weighted_mean_log_t

    low = 0.08
    high = 8.0
    f_low = score(low)
    f_high = score(high)

    # Expand the upper bracket for unusually tight/steep datasets.
    while f_low * f_high > 0 and high < 64:
        high *= 2
        f_high = score(high)

    if f_low * f_high > 0:
        return None

    for _ in range(120):
        mid = (low + high) / 2
        f_mid = score(mid)
        if abs(f_mid) < 1e-10:
            low = high = mid
            break
        if f_low * f_mid <= 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid

    beta = (low + high) / 2
    powered_logs = [beta * lt for lt in log_times]
    log_sum_t_beta = _logsumexp(powered_logs)
    eta = exp((log_sum_t_beta - log(r)) / beta)

    b10 = eta * (-log(0.90)) ** (1.0 / beta)
    b50 = eta * (log(2.0)) ** (1.0 / beta)

    return WeibullFit(
        beta=beta,
        eta=eta,
        b10=b10,
        b50=b50,
        failure_behavior=_failure_behavior(beta),
    )


def kaplan_meier(
    observations: Iterable[ReliabilityObservation],
) -> list[dict]:
    """Return a compact Kaplan-Meier survival curve."""

    obs = sorted((o for o in observations if o.time > 0), key=lambda o: o.time)
    if not obs:
        return []

    grouped: dict[float, list[ReliabilityObservation]] = {}
    for item in obs:
        grouped.setdefault(item.time, []).append(item)

    at_risk = len(obs)
    survival = 1.0
    curve: list[dict] = [
        {
            "mileage": 0.0,
            "survival": 1.0,
            "atRisk": at_risk,
            "failures": 0,
            "censored": 0,
        }
    ]

    for time in sorted(grouped):
        items = grouped[time]
        failures = sum(1 for item in items if item.event)
        censored = len(items) - failures
        if failures and at_risk:
            survival *= 1.0 - failures / at_risk
        curve.append(
            {
                "mileage": round(time, 1),
                "survival": round(max(0.0, survival), 6),
                "atRisk": at_risk,
                "failures": failures,
                "censored": censored,
            }
        )
        at_risk -= failures + censored

    return curve


def median_or_none(values: Iterable[float]) -> float | None:
    vals = list(values)
    return float(median(vals)) if vals else None
