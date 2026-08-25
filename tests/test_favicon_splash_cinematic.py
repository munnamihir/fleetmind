from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class CinematicFaviconSplashTests(unittest.TestCase):
    def test_existing_favicon_remains_the_primary_logo_asset(self):
        source = (ROOT / "web/index.html").read_text()

        self.assertIn(
            '<link rel="icon" href="/favicon.ico" sizes="any" />',
            source,
        )
        self.assertIn('src="/favicon.ico"', source)

    def test_cinematic_layers_are_present(self):
        source = (ROOT / "web/index.html").read_text()

        self.assertIn("fleetmind-splash__halo", source)
        self.assertIn("fleetmind-splash__ring", source)
        self.assertIn("@keyframes fleetmind-scanline", source)
        self.assertIn("@keyframes fleetmind-horizon-reveal", source)
        self.assertIn("@keyframes fleetmind-icon-reveal", source)

    def test_graph_isolated_for_double_beat_animation(self):
        source = (ROOT / "web/index.html").read_text()

        graph = source.split(
            'class="fleetmind-splash__graph"',
            1,
        )[1].split("</svg>", 1)[0]

        self.assertEqual(graph.count("<rect "), 19)
        self.assertIn('fill="#4ade80"', graph)
        self.assertIn("@keyframes fleetmind-graph-pulse", source)
        self.assertIn("transform: scale(1.07)", source)
        self.assertIn("transform: scale(1.04)", source)

    def test_splash_has_cinematic_minimum_visibility(self):
        source = (ROOT / "web/src/main.tsx").read_text()

        self.assertIn(
            "const minimumVisibleMs = reducedMotion ? 100 : 1850",
            source,
        )
        self.assertIn(
            "const fadeDurationMs = reducedMotion ? 110 : 540",
            source,
        )
        self.assertIn(
            "splash.classList.add('fleetmind-splash--leaving')",
            source,
        )

    def test_reduced_motion_is_preserved(self):
        index_source = (ROOT / "web/index.html").read_text()
        main_source = (ROOT / "web/src/main.tsx").read_text()

        self.assertIn(
            "@media (prefers-reduced-motion: reduce)",
            index_source,
        )
        self.assertIn(
            "'(prefers-reduced-motion: reduce)'",
            main_source,
        )


if __name__ == "__main__":
    unittest.main()
