from __future__ import annotations
import unittest
from pathlib import Path
ROOT=Path(__file__).parents[1]

class VehicleOperationalTwinContractTests(unittest.TestCase):
    def api(self): return (ROOT/'services/api/app/diagnostics.py').read_text()
    def test_rules_versioned(self): self.assertIn('fm-vehicle-operational-twin-7.1-v1',(ROOT/'services/common/fleetmind_common/vehicle_twin_rules.py').read_text())
    def test_operational_not_physics(self):
        s=self.api().split('# Phase 7.1 — Vehicle Operational Digital Twin',1)[1].split('@router.get("/summary")',1)[0]
        self.assertIn('"physicsTwin": False',s); self.assertIn('"physicalRul": False',s); self.assertIn('"causalGraph": False',s)
    def test_truth_blind(self):
        s=self.api().split('# Phase 7.1 — Vehicle Operational Digital Twin',1)[1].split('@router.get("/summary")',1)[0]
        self.assertNotIn('FailureEvent',s); self.assertIn('"usesPrivateFailureTruth": False',s)
    def test_population_and_detail_routes(self):
        s=self.api(); self.assertIn('@router.get("/twins/summary")',s); self.assertIn('@router.get("/twins")',s); self.assertIn('@router.get("/twins/{vehicle_id}")',s)
    def test_timeline_graph_evidence_routes(self):
        s=self.api(); self.assertIn('@router.get("/twins/{vehicle_id}/timeline")',s); self.assertIn('@router.get("/twins/{vehicle_id}/graph")',s); self.assertIn('@router.get("/twins/{vehicle_id}/evidence")',s)
    def test_compare_route(self): self.assertIn('@router.get("/twins/compare")',self.api())
    def test_snapshot_model_and_route(self):
        store=(ROOT/'services/common/fleetmind_common/diagnostic_store.py').read_text(); s=self.api()
        self.assertIn('class DiagnosticVehicleTwinSnapshot(Base):',store); self.assertIn('uq_vehicle_twin_snapshot_run_vehicle_hash',store); self.assertIn('@router.post("/twins/{vehicle_id}/snapshots")',s)
    def test_snapshot_no_source_mutation_claim(self): self.assertIn('They do not rewrite predictions, replay, events, episodes, cases, maintenance, automation, fleet-decision evidence',' '.join(self.api().split()))
    def test_graph_labeled_lineage(self): self.assertIn('This graph is data/workflow lineage, not a causal component graph',self.api())
    def test_ui_workspaces(self):
        s=(ROOT/'web/src/VehicleOperationalTwin.tsx').read_text()
        for p in ('CANONICAL TWIN STATE','LONGITUDINAL TWIN TIMELINE','STATE LINEAGE GRAPH','EVIDENCE INVENTORY','TWIN CHECKPOINTS','COMPARE OPERATIONAL TWINS'): self.assertIn(p,s)
    def test_ui_not_physics_twin(self): self.assertIn('NOT PHYSICS TWIN',(ROOT/'web/src/VehicleOperationalTwin.tsx').read_text())
    def test_mount_order(self):
        s=(ROOT/'web/src/RootCauseDashboard.tsx').read_text(); self.assertLess(s.index('<FleetDecisionIntelligence'),s.index('<VehicleOperationalTwin')); self.assertLess(s.index('<VehicleOperationalTwin'),s.index('<DiagnosticTransitionIntelligence'))
    def test_no_training_or_benchmark_write(self):
        s=self.api().split('# Phase 7.1 — Vehicle Operational Digital Twin',1)[1].split('@router.get("/summary")',1)[0]
        self.assertNotIn('xgboost.train',s); self.assertNotIn('DiagnosticBenchmarkSnapshot',s); self.assertIn('"modelRetrained": False',s); self.assertIn('"benchmarkModified": False',s)

    def test_twin_context_bounded_to_prediction_anchor(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        start = source.index("def _current_vehicle_twin_record(")
        end = source.index("\ndef _vehicle_twin_timeline_items(", start)
        section = source[start:end]
        self.assertIn(
            "Telemetry.timestamp <= prediction.anchor_timestamp",
            section,
        )
        self.assertIn('"scoringContextMileage"', section)
        self.assertIn('"scoringContextTimestamp"', section)
        self.assertNotIn('"currentMileage"', section)
        self.assertNotIn('"latestTelemetryTimestamp"', section)

    def test_scope_policy_excludes_post_run_telemetry(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        self.assertIn(
            '"telemetryContextBoundedToPredictionAnchor": True',
            source,
        )
        self.assertIn('"postRunTelemetryUsed": False', source)


    # Phase 7.1.2 — Selected-Run Stability

    def test_twin_default_run_uses_persisted_trained_run(self):
        source = self.api()
        start = source.index("def _resolve_vehicle_twin_run(")
        end = source.index("\ndef _current_vehicle_twin_record(", start)
        section = source[start:end]

        self.assertIn(
            'DiagnosticModelRun.status == "trained"',
            section,
        )
        self.assertIn(
            "desc(DiagnosticModelRun.created_at)",
            section,
        )
        self.assertIn(
            "desc(DiagnosticModelRun.id)",
            section,
        )
        self.assertNotIn("_active_experiment_id(", section)
        self.assertNotIn("_require_current_run(", section)


    def test_twin_explicit_run_id_is_authoritative(self):
        source = self.api()
        start = source.index("def _resolve_vehicle_twin_run(")
        end = source.index("\ndef _current_vehicle_twin_record(", start)
        section = source[start:end]

        self.assertIn(
            "run_id: int | None = None",
            section,
        )
        self.assertIn(
            "db.get(DiagnosticModelRun, run_id)",
            section,
        )
        self.assertIn(
            'if run.status != "trained":',
            section,
        )
        self.assertIn(
            "DiagnosticPrediction.run_id == run.id",
            section,
        )
        self.assertIn(
            "DiagnosticPrediction.experiment_id == run.experiment_id",
            section,
        )


    def test_selected_run_propagates_through_twin_stack(self):
        source = self.api()

        prognostic_start = source.index(
            "def _current_prognostic_records("
        )
        prognostic_end = source.index(
            "\ndef _maintenance_plan_payload(",
            prognostic_start,
        )
        prognostic = source[prognostic_start:prognostic_end]

        fleet_start = source.index(
            "def _current_fleet_decision_records("
        )
        fleet_end = source.index(
            "\n@router.",
            fleet_start,
        )
        fleet = source[fleet_start:fleet_end]

        twin_start = source.index(
            "def _current_vehicle_twin_record("
        )
        twin_end = source.index(
            "\ndef _vehicle_twin_timeline_items(",
            twin_start,
        )
        twin = source[twin_start:twin_end]

        self.assertIn(
            "selected_run: DiagnosticModelRun | None = None",
            prognostic,
        )
        self.assertIn(
            "selected_run: DiagnosticModelRun | None = None",
            fleet,
        )
        self.assertIn(
            "selected_run=run",
            fleet,
        )
        self.assertIn(
            "selected_run: DiagnosticModelRun | None = None",
            twin,
        )
        self.assertIn(
            "selected_run=run",
            twin,
        )


    def test_twin_routes_expose_optional_run_id(self):
        source = self.api()
        start = source.index('@router.get("/twins/summary")')
        end = source.index('@router.get("/summary")', start)
        section = source[start:end]

        expected_routes = (
            '@router.get("/twins/summary")',
            '@router.get("/twins")',
            '@router.get("/twins/compare")',
            '@router.get("/twins/{vehicle_id}")',
            '@router.get("/twins/{vehicle_id}/timeline")',
            '@router.get("/twins/{vehicle_id}/graph")',
            '@router.get("/twins/{vehicle_id}/evidence")',
            '@router.post("/twins/{vehicle_id}/snapshots")',
            '@router.get("/twins/{vehicle_id}/snapshots")',
        )

        for route in expected_routes:
            self.assertIn(route, section)

        self.assertGreaterEqual(
            section.count("run_id"),
            len(expected_routes),
        )
        self.assertIn(
            "run_id: int | None = Query(default=None, ge=1)",
            section,
        )
        self.assertIn(
            "run_id:int|None=Query(default=None,ge=1)",
            section,
        )


    def test_legacy_active_run_selection_remains_unchanged(self):
        source = self.api()

        start = source.index("def _require_current_run(")
        next_def = source.find("\ndef ", start + 1)

        if next_def == -1:
            section = source[start:]
        else:
            section = source[start:next_def]

        self.assertIn(
            "_active_experiment_id(db)",
            section,
        )

        twin_scope_start = source.index(
            "def _vehicle_twin_scope_policy() -> dict:"
        )
        twin_scope_end = source.index(
            "\n\n",
            twin_scope_start,
        )
        twin_scope = source[twin_scope_start:twin_scope_end]

        self.assertIn(
            '"selectedRunOnly": True',
            twin_scope,
        )
        self.assertIn(
            '"defaultRunSelection": "latest_persisted_trained_run"',
            twin_scope,
        )
        self.assertIn(
            '"activeTelemetryExperimentRequired": False',
            twin_scope,
        )


if __name__=='__main__': unittest.main()
