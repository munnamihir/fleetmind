import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "services" / "common"))

from fleetmind_common.reliability import (
    ReliabilityObservation,
    fit_weibull_right_censored,
    kaplan_meier,
)


class ReliabilityMathTests(unittest.TestCase):
    def test_weibull_fit_returns_physical_parameters_with_censoring(self):
        observations = [
            ReliabilityObservation(22000, True),
            ReliabilityObservation(31000, True),
            ReliabilityObservation(39000, True),
            ReliabilityObservation(47000, True),
            ReliabilityObservation(54000, True),
            ReliabilityObservation(62000, False),
            ReliabilityObservation(71000, False),
            ReliabilityObservation(79000, False),
        ]
        fit = fit_weibull_right_censored(observations)
        self.assertIsNotNone(fit)
        assert fit is not None
        self.assertGreater(fit.beta, 0)
        self.assertGreater(fit.eta, 0)
        self.assertLess(fit.b10, fit.b50)
        self.assertLess(fit.b50, fit.eta * 2)
        self.assertGreaterEqual(fit.reliability(0), 0.999)
        self.assertLess(fit.reliability(100000), fit.reliability(25000))

    def test_weibull_requires_enough_failures(self):
        fit = fit_weibull_right_censored(
            [
                ReliabilityObservation(10000, False),
                ReliabilityObservation(20000, True),
                ReliabilityObservation(30000, False),
            ]
        )
        self.assertIsNone(fit)

    def test_kaplan_meier_is_monotonic(self):
        curve = kaplan_meier(
            [
                ReliabilityObservation(10, True),
                ReliabilityObservation(20, False),
                ReliabilityObservation(30, True),
                ReliabilityObservation(40, False),
            ]
        )
        survivals = [point["survival"] for point in curve]
        self.assertTrue(all(a >= b for a, b in zip(survivals, survivals[1:])))
        self.assertTrue(all(0 <= x <= 1 for x in survivals))


if __name__ == "__main__":
    unittest.main()
