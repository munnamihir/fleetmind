import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  Boxes,
  CheckCircle2,
  CircleGauge,
  Layers3,
  Play,
  Save,
  ScanSearch,
  ShieldCheck,
} from 'lucide-react';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

type DecisionState =
  | 'NOMINAL'
  | 'OBSERVE'
  | 'INVESTIGATE'
  | 'PLAN'
  | 'WORKFLOW_ACTIVE';

type Summary = {
  runId: number;
  experimentId: string;
  rulesVersion: string;
  totalVehicles: number;
  nonHealthyHypotheses: number;
  vehiclesWithCases: number;
  attentionRequired: number;
  totalWorkloadUnits: number;
  vehiclesWithCoverageGaps: number;
  coverageGapInstances: number;
  snapshots: number;
  byDecisionState: Array<{ state: DecisionState; vehicles: number }>;
  byCoverageGap: Array<{ gap: string; vehicles: number }>;
  interpretationPolicy: string;
};

type Vehicle = {
  vehicleId: string;
  topClass: string;
  topConfidence: number;
  anchorMileage: number;
  caseId: number | null;
  caseStatus: string | null;
  reviewPriority: string | null;
  assignedTo: string | null;
  episodeState: string | null;
  maintenanceTier: string | null;
  maintenancePlanState: string | null;
  watchlisted: boolean;
  trajectoryEligible: boolean | null;
  automationStatuses: string[];
  pendingActionTypes: string[];
  automationActionIds: number[];
  decisionState: DecisionState;
  attentionScore: number;
  workloadUnits: number;
  coverageGaps: string[];
};

type VehicleList = {
  totalMatched: number;
  returned: number;
  vehicles: Vehicle[];
};

type Coverage = {
  vehiclesWithCoverageGaps: number;
  coverageGapInstances: number;
  gaps: Array<{
    gap: string;
    vehicles: number;
    workloadUnits: number;
    averageAttentionScore: number | null;
  }>;
};

type Cohort = {
  key: string;
  vehicles: number;
  workloadUnits: number;
  coverageGapInstances: number;
  averageAttentionScore: number;
};

type Cohorts = {
  dimension: string;
  cohorts: Cohort[];
};

type ScenarioResult = {
  scenario: string;
  simulationOnly: boolean;
  changedVehicles: number;
  before: {
    totalWorkloadUnits: number;
    vehiclesWithCoverageGaps: number;
    coverageGapInstances: number;
  };
  after: {
    totalWorkloadUnits: number;
    vehiclesWithCoverageGaps: number;
    coverageGapInstances: number;
  };
  deltas: {
    workloadUnits: number;
    vehiclesWithCoverageGaps: number;
    coverageGapInstances: number;
  };
  stateTransitions: Array<{
    fromState: string;
    toState: string;
    vehicles: number;
  }>;
  interpretationPolicy: string;
};

type Snapshot = {
  id: number;
  createdAt: string;
  actor: string;
  label: string | null;
  stateHash: string;
  vehicleCount: number;
};

type Snapshots = {
  total: number;
  snapshots: Snapshot[];
};

type Props = {
  selectedVehicleId: string | null;
  onSelectVehicle: (vehicleId: string) => void;
  runId?: number;
};

const scenarios = [
  'EXECUTE_PENDING_WORKFLOW_ACTIONS',
  'ASSIGN_UNASSIGNED_CASES',
  'CLOSE_ALL_WORKFLOW_GAPS',
];

function humanize(value: string | null | undefined) {
  if (!value) return '—';
  return value.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function pct(value: number | null | undefined) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status}: ${text || url}`);
  }
  return response.json() as Promise<T>;
}

export function FleetDecisionIntelligence({
  selectedVehicleId,
  onSelectVehicle,
  runId,
}: Props) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [vehicles, setVehicles] = useState<VehicleList | null>(null);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [cohorts, setCohorts] = useState<Cohorts | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshots | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [scenario, setScenario] = useState(scenarios[0]);
  const [scenarioResult, setScenarioResult] = useState<ScenarioResult | null>(null);
  const [snapshotLabel, setSnapshotLabel] = useState('');
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [nextSummary, nextVehicles, nextCoverage, nextCohorts, nextSnapshots] =
      await Promise.all([
        requestJson<Summary>(`${API}/api/v1/diagnostics/fleet-intelligence/summary`),
        requestJson<VehicleList>(
          `${API}/api/v1/diagnostics/fleet-intelligence/vehicles?limit=80`,
        ),
        requestJson<Coverage>(
          `${API}/api/v1/diagnostics/fleet-intelligence/coverage`,
        ),
        requestJson<Cohorts>(
          `${API}/api/v1/diagnostics/fleet-intelligence/cohorts?dimension=hypothesisClass`,
        ),
        requestJson<Snapshots>(
          `${API}/api/v1/diagnostics/fleet-intelligence/snapshots?limit=8`,
        ),
      ]);
    setSummary(nextSummary);
    setVehicles(nextVehicles);
    setCoverage(nextCoverage);
    setCohorts(nextCohorts);
    setSnapshots(nextSnapshots);

    setSelectedId(current => {
      if (current && nextVehicles.vehicles.some(item => item.vehicleId === current)) {
        return current;
      }
      if (
        selectedVehicleId &&
        nextVehicles.vehicles.some(item => item.vehicleId === selectedVehicleId)
      ) {
        return selectedVehicleId;
      }
      return nextVehicles.vehicles[0]?.vehicleId ?? null;
    });
  }

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const cycle = async () => {
      try {
        await refresh();
        if (alive) setError(null);
      } catch (refreshError) {
        if (alive) {
          setError(
            refreshError instanceof Error
              ? refreshError.message
              : 'Fleet decision API unavailable',
          );
        }
      } finally {
        if (alive) timer = setTimeout(cycle, 15000);
      }
    };
    void cycle();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [runId]);

  useEffect(() => {
    if (!selectedVehicleId || !vehicles?.vehicles.length) return;
    if (vehicles.vehicles.some(item => item.vehicleId === selectedVehicleId)) {
      setSelectedId(selectedVehicleId);
    }
  }, [selectedVehicleId, vehicles]);

  const selected = useMemo(
    () => vehicles?.vehicles.find(item => item.vehicleId === selectedId) ?? null,
    [vehicles, selectedId],
  );

  const stateMap = useMemo(
    () =>
      new Map(
        (summary?.byDecisionState ?? []).map(item => [item.state, item.vehicles]),
      ),
    [summary],
  );

  async function runScenario() {
    const next = await requestJson<ScenarioResult>(
      `${API}/api/v1/diagnostics/fleet-intelligence/scenario`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario }),
      },
    );
    setScenarioResult(next);
  }

  async function saveSnapshot() {
    await requestJson(
      `${API}/api/v1/diagnostics/fleet-intelligence/snapshots`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          actor: 'dashboard_operator',
          label: snapshotLabel.trim() || null,
        }),
      },
    );
    setSnapshotLabel('');
    await refresh();
  }

  return (
    <section className="panel fleetDecisionPanel">
      <div className="panelTitleRow">
        <div className="panelTitle">
          <span>FLEET STATE & DECISION INTELLIGENCE</span>
          <h2>Operational attention, coverage debt & workflow scenarios</h2>
        </div>
        <span className="methodBadge">
          RUN-FROZEN · WORKFLOW ATTENTION · NOT PHYSICAL RISK
        </span>
      </div>

      <p className="muted fleetDecisionPolicy">
        Fleet states combine current model outputs with persisted diagnostic,
        prognostic and workflow metadata. Attention scores and workload units are
        deterministic operational indices—not failure probabilities, physical
        health scores, labor-hour estimates, RUL, attribution, or causal proof.
      </p>

      {error && <div className="diagnosticError">{error}</div>}

      <div className="fleetDecisionMetrics">
        <Metric
          label="Fleet vehicles"
          value={summary?.totalVehicles ?? 0}
          detail={`${summary?.nonHealthyHypotheses ?? 0} non-healthy model hypotheses`}
        />
        <Metric
          label="Attention required"
          value={summary?.attentionRequired ?? 0}
          detail={`${summary?.vehiclesWithCases ?? 0} vehicles with diagnostic cases`}
        />
        <Metric
          label="Workflow load"
          value={summary?.totalWorkloadUnits ?? 0}
          detail="synthetic workload units · not hours"
        />
        <Metric
          label="Coverage debt"
          value={summary?.coverageGapInstances ?? 0}
          detail={`${summary?.vehiclesWithCoverageGaps ?? 0} vehicles with ≥1 gap`}
        />
      </div>

      <div className="fleetDecisionStateStrip">
        {(['NOMINAL', 'OBSERVE', 'INVESTIGATE', 'PLAN', 'WORKFLOW_ACTIVE'] as DecisionState[]).map(
          state => (
            <div key={state}>
              <span>{humanize(state)}</span>
              <strong>{stateMap.get(state) ?? 0}</strong>
            </div>
          ),
        )}
      </div>

      <div className="fleetDecisionGrid">
        <div className="fleetDecisionCard">
          <div className="fleetDecisionCardTitle">
            <CircleGauge size={15} />
            <div>
              <span>DECISION QUEUE</span>
              <b>Highest deterministic operator-attention scores</b>
            </div>
          </div>
          <div className="fleetDecisionQueue">
            {(vehicles?.vehicles ?? []).slice(0, 28).map(item => (
              <button
                key={item.vehicleId}
                className={selectedId === item.vehicleId ? 'selected' : ''}
                onClick={() => {
                  setSelectedId(item.vehicleId);
                  onSelectVehicle(item.vehicleId);
                }}
              >
                <div>
                  <b>{item.vehicleId}</b>
                  <span>
                    {humanize(item.topClass)} · {humanize(item.decisionState)}
                  </span>
                  <small>
                    {item.coverageGaps.length} gaps · {item.workloadUnits.toFixed(2)} load units
                  </small>
                </div>
                <div>
                  <strong>{item.attentionScore.toFixed(1)}</strong>
                  <span>{pct(item.topConfidence)}</span>
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="fleetDecisionCard">
          <div className="fleetDecisionCardTitle">
            <ScanSearch size={15} />
            <div>
              <span>VEHICLE DECISION STATE</span>
              <b>{selected?.vehicleId ?? 'Select a vehicle'}</b>
            </div>
          </div>

          {selected ? (
            <>
              <div className="fleetDecisionHero">
                <div>
                  <span>Operational state</span>
                  <strong>{humanize(selected.decisionState)}</strong>
                </div>
                <div>
                  <span>Attention score</span>
                  <strong>{selected.attentionScore.toFixed(1)}</strong>
                </div>
                <div>
                  <span>Workflow load</span>
                  <strong>{selected.workloadUnits.toFixed(2)}</strong>
                </div>
              </div>

              <div className="fleetDecisionFacts">
                <Fact label="Hypothesis" value={humanize(selected.topClass)} />
                <Fact label="Confidence" value={pct(selected.topConfidence)} />
                <Fact label="Case" value={selected.caseId ? `#${selected.caseId}` : '—'} />
                <Fact label="Case state" value={humanize(selected.caseStatus)} />
                <Fact label="Review priority" value={humanize(selected.reviewPriority)} />
                <Fact label="Assigned" value={selected.assignedTo ?? 'Unassigned'} />
                <Fact label="Maintenance tier" value={humanize(selected.maintenanceTier)} />
                <Fact label="Plan state" value={humanize(selected.maintenancePlanState)} />
              </div>

              <span className="fleetDecisionSubhead">COVERAGE GAPS</span>
              <div className="fleetDecisionGaps">
                {selected.coverageGaps.length ? (
                  selected.coverageGaps.map(gap => (
                    <span key={gap}>{humanize(gap)}</span>
                  ))
                ) : (
                  <span className="covered"><CheckCircle2 size={12} /> No current coverage gap</span>
                )}
              </div>

              <span className="fleetDecisionSubhead">AUTOMATION WORKFLOW</span>
              <div className="fleetDecisionAutomation">
                <span>
                  Statuses <b>{selected.automationStatuses.map(humanize).join(', ') || '—'}</b>
                </span>
                <span>
                  Pending effects <b>{selected.pendingActionTypes.map(humanize).join(', ') || '—'}</b>
                </span>
              </div>
            </>
          ) : (
            <div className="fleetDecisionEmpty">Select a fleet decision record.</div>
          )}
        </div>
      </div>

      <div className="fleetDecisionGrid lower">
        <div className="fleetDecisionCard">
          <div className="fleetDecisionCardTitle">
            <Layers3 size={15} />
            <div>
              <span>COVERAGE DEBT</span>
              <b>Workflow and evidence gaps across current fleet state</b>
            </div>
          </div>
          <div className="fleetCoverageRows">
            {(coverage?.gaps ?? []).map(gap => (
              <div key={gap.gap}>
                <b>{humanize(gap.gap)}</b>
                <span>{gap.vehicles} vehicles</span>
                <span>{gap.workloadUnits.toFixed(2)} load units</span>
                <strong>
                  {gap.averageAttentionScore == null
                    ? '—'
                    : gap.averageAttentionScore.toFixed(1)}
                </strong>
              </div>
            ))}
          </div>
        </div>

        <div className="fleetDecisionCard">
          <div className="fleetDecisionCardTitle">
            <Boxes size={15} />
            <div>
              <span>COHORT CONCENTRATION</span>
              <b>Current workload by model hypothesis</b>
            </div>
          </div>
          <div className="fleetCohortRows">
            {(cohorts?.cohorts ?? []).slice(0, 10).map(cohort => (
              <div key={cohort.key}>
                <b>{humanize(cohort.key)}</b>
                <span>{cohort.vehicles} vehicles</span>
                <span>{cohort.workloadUnits.toFixed(2)} load</span>
                <strong>{cohort.averageAttentionScore.toFixed(1)}</strong>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="fleetDecisionGrid lower">
        <div className="fleetDecisionCard">
          <div className="fleetDecisionCardTitle">
            <Play size={15} />
            <div>
              <span>WORKFLOW SCENARIO LAB</span>
              <b>No-write counterfactual workflow simulation</b>
            </div>
          </div>
          <div className="fleetScenarioControls">
            <select value={scenario} onChange={event => setScenario(event.target.value)}>
              {scenarios.map(item => (
                <option value={item} key={item}>
                  {humanize(item)}
                </option>
              ))}
            </select>
            <button onClick={() => void runScenario()}>
              <Play size={13} /> Run no-write scenario
            </button>
          </div>

          {scenarioResult && (
            <>
              <div className="fleetScenarioHero">
                <Fact
                  label="Changed vehicles"
                  value={String(scenarioResult.changedVehicles)}
                />
                <Fact
                  label="Load delta"
                  value={scenarioResult.deltas.workloadUnits.toFixed(2)}
                />
                <Fact
                  label="Gap delta"
                  value={String(scenarioResult.deltas.coverageGapInstances)}
                />
                <Fact
                  label="Vehicles w/ gaps delta"
                  value={String(scenarioResult.deltas.vehiclesWithCoverageGaps)}
                />
              </div>
              <div className="fleetScenarioTransitions">
                {scenarioResult.stateTransitions.map(item => (
                  <span key={`${item.fromState}-${item.toState}`}>
                    {humanize(item.fromState)} → {humanize(item.toState)}
                    <b>{item.vehicles}</b>
                  </span>
                ))}
              </div>
              <p className="muted fleetScenarioPolicy">
                Simulation changes workflow metadata assumptions only. It does
                not forecast failures, component health, service outcomes, or
                causal effects.
              </p>
            </>
          )}
        </div>

        <div className="fleetDecisionCard">
          <div className="fleetDecisionCardTitle">
            <Save size={15} />
            <div>
              <span>DECISION CHECKPOINTS</span>
              <b>Versioned snapshots of derived fleet workflow state</b>
            </div>
          </div>

          <div className="fleetSnapshotComposer">
            <input
              value={snapshotLabel}
              onChange={event => setSnapshotLabel(event.target.value)}
              placeholder="Optional checkpoint label"
            />
            <button onClick={() => void saveSnapshot()}>
              <Save size={13} /> Save current checkpoint
            </button>
          </div>

          <div className="fleetSnapshotRows">
            {(snapshots?.snapshots ?? []).map(snapshot => (
              <div key={snapshot.id}>
                <ShieldCheck size={13} />
                <div>
                  <b>{snapshot.label || `Snapshot ${snapshot.id}`}</b>
                  <span>
                    {snapshot.vehicleCount} vehicles · {snapshot.actor}
                  </span>
                  <small>
                    {snapshot.stateHash.slice(0, 12)}… ·{' '}
                    {new Date(snapshot.createdAt).toLocaleString()}
                  </small>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="fleetDecisionFootnote">
        <Activity size={14} />
        <span>
          Fleet Decision Intelligence is derived from current-run model outputs,
          run-frozen prognostic records, and explicit workflow metadata. No
          private failure truth, post-run telemetry, automatic execution, model
          retraining, or benchmark mutation is used.
        </span>
      </div>
    </section>
  );
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: number;
  detail: string;
}) {
  return (
    <div className="fleetDecisionMetric">
      <span>{label}</span>
      <strong>{value.toLocaleString()}</strong>
      <small>{detail}</small>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}
