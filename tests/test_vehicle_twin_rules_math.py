from __future__ import annotations
import unittest
from services.common.fleetmind_common.vehicle_twin_rules import *

def sample(**kw):
    d={"vehicleId":"EV-A","runId":5,"experimentId":"exp","lineage":"lineage",
       "vehicleContext":{"model":"S3","factory":"Austin","firmware":"2026.32.1","pumpRevision":"CP-17","scoringContextMileage":50000.0,"scoringContextTimestamp":"2026-08-25T18:00:00+00:00"},
       "modelState":{"topClass":"inverter","topConfidence":.91},"diagnosticState":{"episodeId":7,"episodeState":"EVOLVING"},
       "caseState":{"caseId":8,"status":"OPEN"},"prognosticState":{"maintenanceTier":"PLAN_SERVICE"},"maintenanceState":{"planId":None,"state":None},
       "automationState":{"actionIds":[3],"statuses":["PENDING_APPROVAL"]},"fleetDecisionState":{"decisionState":"PLAN","attentionScore":90.0,"workloadUnits":3.25},
       "coverageState":{"coverageGaps":["PRIORITY_CASE_WITHOUT_PLAN"]},"sourceVersions":{"twinRules":VEHICLE_TWIN_RULES_VERSION}}
    d.update(kw); return d

class VehicleTwinRulesTests(unittest.TestCase):
    def test_version(self): self.assertEqual(VEHICLE_TWIN_RULES_VERSION,'fm-vehicle-operational-twin-7.1-v1')
    def test_layers(self):
        x=active_twin_layers(sample()); self.assertEqual(len(x),7); self.assertNotIn(TWIN_LAYER_MAINTENANCE,x)
    def test_presence_not_health_score(self): self.assertIn('not a physical-health',layer_presence_payload(sample())['interpretation'])
    def test_status_order(self): self.assertEqual(current_automation_status(['PENDING_APPROVAL','APPROVED','EXECUTED']),'EXECUTED')
    def test_compare_exact_differences(self):
        a=sample(); b=sample(vehicleId='EV-B',modelState={'topClass':'battery_pack','topConfidence':.85},fleetDecisionState={'decisionState':'OBSERVE','attentionScore':50.0,'workloadUnits':.5},coverageState={'coverageGaps':['UNASSIGNED_CASE']}); r=compare_twin_states(a,b); self.assertFalse(r['sameHypothesisClass']); self.assertFalse(r['sameDecisionState']); self.assertEqual(r['attentionScoreDelta'],-40.0)
    def test_compare_metadata(self):
        b=sample(vehicleId='EV-B'); b['vehicleContext']['factory']='Berlin'; r=compare_twin_states(sample(),b); self.assertFalse(r['metadataMatches']['factory']); self.assertTrue(r['metadataMatches']['firmware'])
    def test_list_projection_active_layers(self):
        r=twin_list_record({'vehicleId':'EV-1','topClass':'inverter','topConfidence':.9,'decisionState':'PLAN','attentionScore':90,'workloadUnits':3.25,'caseId':1,'caseStatus':'OPEN','episodeId':2,'episodeState':'EVOLVING','maintenanceTier':'PLAN_SERVICE','maintenancePlanId':None,'maintenancePlanState':None,'automationActionIds':[3],'automationStatuses':['PENDING_APPROVAL'],'coverageGaps':['UNASSIGNED_CASE']}); self.assertEqual(r['activeLayerCount'],7)
    def test_healthy_projection_base_layers(self):
        r=twin_list_record({'vehicleId':'EV-H','topClass':'healthy','topConfidence':.99,'decisionState':'NOMINAL','attentionScore':0,'workloadUnits':0,'caseId':None,'caseStatus':None,'episodeId':None,'episodeState':None,'maintenanceTier':None,'maintenancePlanId':None,'maintenancePlanState':None,'automationActionIds':[],'automationStatuses':[],'coverageGaps':[]}); self.assertEqual(r['activeLayerCount'],3)

    def test_hash_retains_frozen_scoring_context(self):
        state = canonical_twin_state(sample())
        self.assertEqual(
            state["vehicleContext"]["scoringContextMileage"],
            50000.0,
        )
        self.assertEqual(
            state["vehicleContext"]["scoringContextTimestamp"],
            "2026-08-25T18:00:00+00:00",
        )

    def test_hash_changes_if_frozen_scoring_context_changes(self):
        first = canonical_twin_state(sample())
        changed = sample()
        changed["vehicleContext"]["scoringContextMileage"] = 50001.0
        second = canonical_twin_state(changed)
        self.assertNotEqual(first, second)


if __name__=='__main__': unittest.main()
