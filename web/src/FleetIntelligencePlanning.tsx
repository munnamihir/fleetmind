import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Activity,
  ArrowRight,
  BarChart3,
  Boxes,
  CheckCircle2,
  Clock3,
  GitCompareArrows,
  Gauge,
  Layers3,
  Play,
  RefreshCw,
  Scale,
  ShieldCheck,
  SlidersHorizontal,
  Target,
  Workflow,
} from 'lucide-react';


const API =
  import.meta.env.VITE_API_URL ??
  'http://localhost:8000';


type Workspace =
  | 'EXPOSURE'
  | 'CHANGE'
  | 'CAPACITY'
  | 'EFFECTIVENESS';


type Props = {
  runId?: number;
};


type FleetTwinSummary = {
  runId: number;
  experimentId: string;
  lineage: string;
  rulesVersion: string;

  populationCount: number;

  attentionCount: number;
  attentionRatePct: number;

  nonHealthyCount: number;
  nonHealthyRatePct: number;

  caseCount: number;
  caseRatePct: number;

  coverageGapVehicleCount: number;
  coverageGapRatePct: number;

  coverageGapInstances: number;

  totalWorkloadUnits: number;
  workloadUnitsPer100Vehicles: number;
  meanAttentionScore: number;

  dimensions: string[];
  exposureMeasures: string[];
};


type CohortRow = {
  dimension: string;
  value: string;

  populationCount: number;
  populationSharePct: number;

  attentionCount: number;
  attentionRatePct: number;

  nonHealthyCount: number;
  nonHealthyRatePct: number;

  caseCount: number;
  caseRatePct: number;

  coverageGapVehicleCount: number;
  coverageGapRatePct: number;

  coverageGapInstances: number;

  totalWorkloadUnits: number;
  workloadUnitsPer100Vehicles: number;
  meanAttentionScore: number;

  rateToFleetRatio: {
    attention: number | null;
    nonHealthy: number | null;
    case: number | null;
    coverageGap: number | null;
  };
};


type CohortResponse = {
  runId: number;
  experimentId: string;
  dimension: string;
  fleetBaseline: FleetTwinSummary;
  cohorts: CohortRow[];
  interpretation: string;
};


type FleetSnapshot = {
  id: number;
  runId: number;
  experimentId: string;
  createdAt: string;
  actor: string;
  label: string | null;
  stateHash: string;
  vehicleCount: number;
};


type SnapshotResponse = {
  runId: number;
  experimentId: string;
  total: number;
  returned: number;
  snapshots: FleetSnapshot[];
};


type TransitionCounts =
  Record<string, number>;


type ChangeSummary = {
  runId: number;
  experimentId: string;
  fromSnapshot: FleetSnapshot;
  toSnapshot: FleetSnapshot | null;
  toCurrent: boolean;

  fromVehicleCount: number;
  toVehicleCount: number;
  vehiclesCompared: number;
  vehiclesChanged: number;
  vehiclesUnchanged: number;

  transitionCounts: TransitionCounts;

  fromWorkloadUnits: number;
  toWorkloadUnits: number;
  workloadUnitsDelta: number;

  fromAttentionScoreTotal: number;
  toAttentionScoreTotal: number;
  attentionScoreTotalDelta: number;

  fromCoverageGapInstances: number;
  toCoverageGapInstances: number;
  coverageGapInstanceDelta: number;

  changedVehicleCount: number;
};


type VehicleChange = {
  vehicleId: string;
  changed: boolean;
  changedFields: string[];
  transitions: string[];

  fromDecisionState: string | null;
  toDecisionState: string | null;

  fromAttentionScore: number;
  toAttentionScore: number;
  attentionScoreDelta: number;

  fromWorkloadUnits: number;
  toWorkloadUnits: number;
  workloadUnitsDelta: number;

  fromCoverageGaps: string[];
  toCoverageGaps: string[];
  coverageGapDelta: number;
};


type VehicleChangeResponse = {
  totalMatching: number;
  returned: number;
  vehicles: VehicleChange[];
};


type CapacityResult = {
  runId: number;
  experimentId: string;
  rulesVersion: string;

  strategy: string;

  requestedCapacityUnits: number;
  allocatedCapacityUnits: number;
  unusedCapacityUnits: number;
  capacityUtilizationPct: number;

  fleetVehicles: number;
  eligibleVehicles: number;
  selectedVehicles: number;
  deferredVehicles: number;
  ineligibleVehicles: number;

  fleetWorkloadUnits: number;
  eligibleWorkloadUnits: number;
  selectedWorkloadUnits: number;
  deferredWorkloadUnits: number;

  fleetCoverageGapInstances: number;
  simulatedAddressedCoverageGapInstances: number;
  simulatedRemainingCoverageGapInstances: number;

  selection: Array<{
    rank: number;
    vehicleId: string;
    decisionState: string;
    maintenanceTier: string | null;
    hypothesisClass: string;
    attentionScore: number;
    workloadUnits: number;
    coverageGapCount: number;
    coverageGaps: string[];
    strategyEfficiency: number;
  }>;
};


type EffectivenessSummary = {
  runId: number;
  experimentId: string;
  rulesVersion: string;

  totalPolicies: number;
  enabledPolicies: number;

  currentMatches: number;
  totalActions: number;

  pendingApproval: number;
  approvedReady: number;
  rejected: number;
  executed: number;
  everApproved: number;

  approvalRatePct: number;
  executionRatePct: number;
  rejectionRatePct: number;

  evaluableExecutedActions: number;
  executedTargetObserved: number;
  executedTargetObservationRatePct: number;
};


type PolicyRow = {
  policyId: number;
  policyKey: string;
  policyName: string;
  enabled: boolean;
  priority: number;
  severity: string;
  actionType: string;
  requiresApproval: boolean;

  currentMatches: number;
  materializedActions: number;
  pendingApproval: number;
  approvedReady: number;
  rejected: number;
  executed: number;
  everApproved: number;

  approvalRatePct: number;
  executionRatePct: number;
  rejectionRatePct: number;

  medianHoursToApproval: number | null;
  medianHoursToExecution: number | null;

  evaluableExecutedActions: number;
  executedTargetObserved: number;
  executedTargetObservationRatePct: number;
};


type PolicyResponse = {
  policies: PolicyRow[];
};


function humanize(
  value: string | null | undefined,
) {
  if (!value) return '—';

  return value
    .replaceAll('_', ' ')
    .replace(
      /\b\w/g,
      char => char.toUpperCase(),
    );
}


function percent(
  value: number | null | undefined,
  digits = 1,
) {
  if (value == null) return '—';

  return `${value.toFixed(digits)}%`;
}


function number(
  value: number | null | undefined,
  digits = 0,
) {
  if (value == null) return '—';

  return value.toLocaleString(
    undefined,
    {
      maximumFractionDigits: digits,
    },
  );
}


function signed(
  value: number | null | undefined,
  digits = 1,
) {
  if (value == null) return '—';

  const text = value.toFixed(digits);

  return value > 0
    ? `+${text}`
    : text;
}


function runQuery(
  runId?: number,
) {
  return runId
    ? `run_id=${runId}`
    : '';
}


function withRun(
  path: string,
  runId?: number,
) {
  const query = runQuery(runId);

  if (!query) return `${API}${path}`;

  return `${API}${path}${
    path.includes('?')
      ? '&'
      : '?'
  }${query}`;
}


async function json<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(
    url,
    init,
  );

  if (!response.ok) {
    throw new Error(
      `${response.status}: ${await response.text()}`,
    );
  }

  return response.json() as Promise<T>;
}


export function FleetIntelligencePlanning({
  runId,
}: Props) {
  const [
    workspace,
    setWorkspace,
  ] = useState<Workspace>('EXPOSURE');

  const [
    summary,
    setSummary,
  ] = useState<FleetTwinSummary | null>(
    null,
  );

  const [
    dimension,
    setDimension,
  ] = useState('factory');

  const [
    cohorts,
    setCohorts,
  ] = useState<CohortResponse | null>(
    null,
  );

  const [
    snapshots,
    setSnapshots,
  ] = useState<SnapshotResponse | null>(
    null,
  );

  const [
    snapshotFrom,
    setSnapshotFrom,
  ] = useState<number | null>(null);

  const [
    changeSummary,
    setChangeSummary,
  ] = useState<ChangeSummary | null>(
    null,
  );

  const [
    vehicleChanges,
    setVehicleChanges,
  ] = useState<VehicleChange[]>([]);

  const [
    capacityUnits,
    setCapacityUnits,
  ] = useState(100);

  const [
    capacityStrategy,
    setCapacityStrategy,
  ] = useState('BALANCED');

  const [
    capacity,
    setCapacity,
  ] = useState<CapacityResult | null>(
    null,
  );

  const [
    effectiveness,
    setEffectiveness,
  ] = useState<EffectivenessSummary | null>(
    null,
  );

  const [
    policies,
    setPolicies,
  ] = useState<PolicyRow[]>([]);

  const [
    loading,
    setLoading,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState<string | null>(null);


  async function refreshExposure() {
    const [nextSummary, nextCohorts] =
      await Promise.all([
        json<FleetTwinSummary>(
          withRun(
            '/api/v1/diagnostics/fleet-twin/summary',
            runId,
          ),
        ),
        json<CohortResponse>(
          withRun(
            `/api/v1/diagnostics/fleet-twin/cohorts?dimension=${encodeURIComponent(
              dimension,
            )}`,
            runId,
          ),
        ),
      ]);

    setSummary(nextSummary);
    setCohorts(nextCohorts);
  }


  async function refreshSnapshots() {
    const next =
      await json<SnapshotResponse>(
        withRun(
          '/api/v1/diagnostics/fleet-change/snapshots?limit=50',
          runId,
        ),
      );

    setSnapshots(next);

    setSnapshotFrom(current => {
      if (
        current &&
        next.snapshots.some(
          row => row.id === current,
        )
      ) {
        return current;
      }

      return next.snapshots[0]?.id ?? null;
    });
  }


  async function refreshEffectiveness() {
    const [nextSummary, nextPolicies] =
      await Promise.all([
        json<EffectivenessSummary>(
          withRun(
            '/api/v1/diagnostics/workflow-effectiveness/summary',
            runId,
          ),
        ),
        json<PolicyResponse>(
          withRun(
            '/api/v1/diagnostics/workflow-effectiveness/policies',
            runId,
          ),
        ),
      ]);

    setEffectiveness(nextSummary);
    setPolicies(nextPolicies.policies);
  }


  async function refreshAll() {
    setLoading(true);

    try {
      await Promise.all([
        refreshExposure(),
        refreshSnapshots(),
        refreshEffectiveness(),
      ]);

      setError(null);
    } catch (refreshError) {
      setError(
        refreshError instanceof Error
          ? refreshError.message
          : 'Fleet Intelligence API unavailable',
      );
    } finally {
      setLoading(false);
    }
  }


  useEffect(() => {
    void refreshAll();

    const timer = setInterval(
      () => {
        void refreshAll();
      },
      20000,
    );

    return () => clearInterval(timer);
  }, [runId]);


  useEffect(() => {
    void refreshExposure().catch(
      refreshError => {
        setError(
          refreshError instanceof Error
            ? refreshError.message
            : 'Fleet exposure unavailable',
        );
      },
    );
  }, [dimension]);


  async function compareState() {
    if (!snapshotFrom) return;

    setLoading(true);

    try {
      const suffix =
        `snapshot_from=${snapshotFrom}` +
        '&to_current=true';

      const [
        nextSummary,
        nextVehicles,
      ] = await Promise.all([
        json<ChangeSummary>(
          withRun(
            `/api/v1/diagnostics/fleet-change/compare?${suffix}`,
            runId,
          ),
        ),
        json<VehicleChangeResponse>(
          withRun(
            `/api/v1/diagnostics/fleet-change/vehicles?${suffix}&changed_only=true&limit=100`,
            runId,
          ),
        ),
      ]);

      setChangeSummary(nextSummary);
      setVehicleChanges(
        nextVehicles.vehicles,
      );

      setError(null);
    } catch (compareError) {
      setError(
        compareError instanceof Error
          ? compareError.message
          : 'Fleet change comparison unavailable',
      );
    } finally {
      setLoading(false);
    }
  }


  async function simulateCapacity() {
    setLoading(true);

    try {
      const result =
        await json<CapacityResult>(
          `${API}/api/v1/diagnostics/capacity-planning/simulate`,
          {
            method: 'POST',
            headers: {
              'Content-Type':
                'application/json',
            },
            body: JSON.stringify({
              runId: runId ?? null,
              capacityUnits,
              strategy:
                capacityStrategy,
              maxVehicles: null,
              allowedMaintenanceTiers: [],
              allowedDecisionStates: [],
            }),
          },
        );

      setCapacity(result);
      setError(null);
    } catch (simulationError) {
      setError(
        simulationError instanceof Error
          ? simulationError.message
          : 'Capacity simulation unavailable',
      );
    } finally {
      setLoading(false);
    }
  }


  const topCohorts = useMemo(
    () =>
      [...(cohorts?.cohorts ?? [])]
        .sort(
          (a, b) =>
            b.nonHealthyRatePct -
            a.nonHealthyRatePct,
        )
        .slice(0, 12),
    [cohorts],
  );


  return (
    <section className="panel fleetPlanningPanel">
      <div className="panelTitleRow">
        <div className="panelTitle">
          <span>
            PHASES 7.2–7.5 · FLEET INTELLIGENCE & PLANNING
          </span>
          <h2>
            Normalize exposure, understand change,
            simulate capacity and measure workflow throughput
          </h2>
        </div>

        <span className="methodBadge">
          SELECTED-RUN · OPERATIONAL ONLY
        </span>
      </div>

      <p className="muted fleetPlanningPolicy">
        Counts and rates describe selected-run operational representation.
        State changes describe workflow/evidence change. Capacity units are
        synthetic prioritization units. Policy effectiveness measures workflow
        lifecycle throughput and current target-state observation. None of
        these are physical failure risk, technician hours, causal effects,
        physical RUL or proof of maintenance success.
      </p>

      {error && (
        <div className="diagnosticError">
          {error}
        </div>
      )}

      <div className="fleetPlanningHeader">
        <div>
          <span>Selected diagnostic run</span>
          <strong>
            {summary?.runId ?? runId ?? '—'}
          </strong>
          <small>
            {summary?.experimentId ?? 'persisted selected run'}
          </small>
        </div>

        <div>
          <span>Fleet population</span>
          <strong>
            {number(summary?.populationCount)}
          </strong>
          <small>
            frozen operational population
          </small>
        </div>

        <div>
          <span>Nonhealthy representation</span>
          <strong>
            {percent(summary?.nonHealthyRatePct)}
          </strong>
          <small>
            {number(summary?.nonHealthyCount)} model hypotheses
          </small>
        </div>

        <div>
          <span>Workflow workload</span>
          <strong>
            {number(
              summary?.totalWorkloadUnits,
              2,
            )}
          </strong>
          <small>
            synthetic units · not hours
          </small>
        </div>

        <button
          className="fleetPlanningRefresh"
          onClick={() => void refreshAll()}
          disabled={loading}
        >
          <RefreshCw
            size={14}
            className={
              loading
                ? 'fleetPlanningSpin'
                : ''
            }
          />
          Refresh
        </button>
      </div>

      <div className="fleetPlanningTabs">
        <WorkspaceButton
          active={workspace === 'EXPOSURE'}
          icon={<BarChart3 size={15} />}
          label="FLEET EXPOSURE"
          onClick={() =>
            setWorkspace('EXPOSURE')
          }
        />

        <WorkspaceButton
          active={workspace === 'CHANGE'}
          icon={<GitCompareArrows size={15} />}
          label="STATE CHANGE"
          onClick={() =>
            setWorkspace('CHANGE')
          }
        />

        <WorkspaceButton
          active={workspace === 'CAPACITY'}
          icon={<Gauge size={15} />}
          label="CAPACITY PLANNING"
          onClick={() =>
            setWorkspace('CAPACITY')
          }
        />

        <WorkspaceButton
          active={
            workspace === 'EFFECTIVENESS'
          }
          icon={<Workflow size={15} />}
          label="POLICY EFFECTIVENESS"
          onClick={() =>
            setWorkspace('EFFECTIVENESS')
          }
        />
      </div>


      {workspace === 'EXPOSURE' && (
        <ExposureWorkspace
          summary={summary}
          cohorts={topCohorts}
          dimension={dimension}
          setDimension={setDimension}
        />
      )}


      {workspace === 'CHANGE' && (
        <ChangeWorkspace
          snapshots={
            snapshots?.snapshots ?? []
          }
          snapshotFrom={snapshotFrom}
          setSnapshotFrom={setSnapshotFrom}
          comparison={changeSummary}
          vehicles={vehicleChanges}
          compare={() =>
            void compareState()
          }
          loading={loading}
        />
      )}


      {workspace === 'CAPACITY' && (
        <CapacityWorkspace
          capacityUnits={capacityUnits}
          setCapacityUnits={setCapacityUnits}
          strategy={capacityStrategy}
          setStrategy={setCapacityStrategy}
          result={capacity}
          simulate={() =>
            void simulateCapacity()
          }
          loading={loading}
        />
      )}


      {workspace === 'EFFECTIVENESS' && (
        <EffectivenessWorkspace
          summary={effectiveness}
          policies={policies}
        />
      )}


      <div className="fleetPlanningBoundary">
        <ShieldCheck size={15} />

        <span>
          Selected-run operational intelligence only ·
          private failure truth excluded · post-run telemetry excluded ·
          no automatic execution · no benchmark or model mutation.
        </span>
      </div>
    </section>
  );
}


function ExposureWorkspace({
  summary,
  cohorts,
  dimension,
  setDimension,
}: {
  summary: FleetTwinSummary | null;
  cohorts: CohortRow[];
  dimension: string;
  setDimension: (
    value: string,
  ) => void;
}) {
  return (
    <div className="fleetPlanningWorkspace">
      <div className="fleetPlanningWorkspaceTitle">
        <div>
          <Scale size={17} />
          <div>
            <span>
              PHASE 7.2 · NORMALIZED COHORT EXPOSURE
            </span>
            <b>
              Count is not rate. Rate is not physical risk.
            </b>
          </div>
        </div>

        <select
          value={dimension}
          onChange={event =>
            setDimension(
              event.target.value,
            )
          }
        >
          {(
            summary?.dimensions ?? [
              'factory',
              'model',
              'firmware',
              'pumpRevision',
              'hypothesisClass',
              'decisionState',
              'maintenanceTier',
              'reviewPriority',
              'automationStatus',
            ]
          ).map(value => (
            <option
              key={value}
              value={value}
            >
              {humanize(value)}
            </option>
          ))}
        </select>
      </div>

      <div className="fleetPlanningMetricGrid">
        <PlanningMetric
          label="Attention rate"
          value={percent(
            summary?.attentionRatePct,
          )}
          detail={`${number(
            summary?.attentionCount,
          )} vehicles`}
        />

        <PlanningMetric
          label="Case rate"
          value={percent(
            summary?.caseRatePct,
          )}
          detail={`${number(
            summary?.caseCount,
          )} vehicles`}
        />

        <PlanningMetric
          label="Coverage gap rate"
          value={percent(
            summary?.coverageGapRatePct,
          )}
          detail={`${number(
            summary?.coverageGapInstances,
          )} gap instances`}
        />

        <PlanningMetric
          label="Workload / 100"
          value={number(
            summary?.workloadUnitsPer100Vehicles,
            1,
          )}
          detail="synthetic normalized load"
        />
      </div>

      <div className="fleetExposureTable">
        <div className="fleetExposureHeader">
          <span>Cohort</span>
          <span>Population</span>
          <span>Nonhealthy</span>
          <span>Rate</span>
          <span>vs fleet</span>
          <span>Workload /100</span>
        </div>

        {cohorts.map(row => (
          <div
            className="fleetExposureRow"
            key={`${row.dimension}-${row.value}`}
          >
            <div>
              <b>{humanize(row.value)}</b>
              <small>
                {percent(
                  row.populationSharePct,
                )} of fleet
              </small>
            </div>

            <strong>
              {number(
                row.populationCount,
              )}
            </strong>

            <strong>
              {number(
                row.nonHealthyCount,
              )}
            </strong>

            <strong>
              {percent(
                row.nonHealthyRatePct,
              )}
            </strong>

            <strong>
              {row.rateToFleetRatio
                .nonHealthy == null
                ? '—'
                : `${row.rateToFleetRatio.nonHealthy.toFixed(
                    2,
                  )}×`}
            </strong>

            <strong>
              {number(
                row.workloadUnitsPer100Vehicles,
                1,
              )}
            </strong>
          </div>
        ))}
      </div>

      <p className="fleetPlanningInterpretation">
        <Scale size={13} />
        Rate-to-fleet ratios compare selected-run representation only.
        They are not relative failure risk or reliability estimates.
      </p>
    </div>
  );
}


function ChangeWorkspace({
  snapshots,
  snapshotFrom,
  setSnapshotFrom,
  comparison,
  vehicles,
  compare,
  loading,
}: {
  snapshots: FleetSnapshot[];
  snapshotFrom: number | null;
  setSnapshotFrom: (
    value: number,
  ) => void;
  comparison: ChangeSummary | null;
  vehicles: VehicleChange[];
  compare: () => void;
  loading: boolean;
}) {
  return (
    <div className="fleetPlanningWorkspace">
      <div className="fleetPlanningWorkspaceTitle">
        <div>
          <GitCompareArrows size={17} />
          <div>
            <span>
              PHASE 7.3 · FLEET STATE CHANGE
            </span>
            <b>
              Persisted checkpoint → selected-run current state
            </b>
          </div>
        </div>
      </div>

      <div className="fleetChangeControls">
        <label>
          <span>From checkpoint</span>

          <select
            value={
              snapshotFrom ?? ''
            }
            onChange={event =>
              setSnapshotFrom(
                Number(
                  event.target.value,
                ),
              )
            }
          >
            {snapshots.map(snapshot => (
              <option
                key={snapshot.id}
                value={snapshot.id}
              >
                #{snapshot.id} ·{' '}
                {snapshot.label ??
                  new Date(
                    snapshot.createdAt,
                  ).toLocaleString()}
              </option>
            ))}
          </select>
        </label>

        <div className="fleetChangeArrow">
          <ArrowRight size={20} />
          <span>
            CURRENT SELECTED-RUN STATE
          </span>
        </div>

        <button
          onClick={compare}
          disabled={
            !snapshotFrom ||
            loading
          }
        >
          <GitCompareArrows
            size={14}
          />
          Compare state
        </button>
      </div>

      {snapshots.length === 0 && (
        <div className="fleetPlanningEmpty">
          No persisted Fleet Decision checkpoint is available for this selected run.
        </div>
      )}

      {comparison && (
        <>
          <div className="fleetPlanningMetricGrid">
            <PlanningMetric
              label="Vehicles changed"
              value={number(
                comparison.vehiclesChanged,
              )}
              detail={`${number(
                comparison.vehiclesUnchanged,
              )} unchanged`}
            />

            <PlanningMetric
              label="Workload Δ"
              value={signed(
                comparison.workloadUnitsDelta,
                2,
              )}
              detail={`${number(
                comparison.fromWorkloadUnits,
                2,
              )} → ${number(
                comparison.toWorkloadUnits,
                2,
              )}`}
            />

            <PlanningMetric
              label="Coverage gap Δ"
              value={signed(
                comparison.coverageGapInstanceDelta,
                0,
              )}
              detail={`${number(
                comparison.fromCoverageGapInstances,
              )} → ${number(
                comparison.toCoverageGapInstances,
              )}`}
            />

            <PlanningMetric
              label="Attention total Δ"
              value={signed(
                comparison.attentionScoreTotalDelta,
                1,
              )}
              detail="operational score total"
            />
          </div>

          <div className="fleetTransitionGrid">
            {Object.entries(
              comparison.transitionCounts,
            )
              .filter(
                ([, value]) =>
                  value > 0,
              )
              .map(
                ([transition, count]) => (
                  <div
                    key={transition}
                  >
                    <span>
                      {humanize(
                        transition,
                      )}
                    </span>
                    <b>{count}</b>
                  </div>
                ),
              )}
          </div>

          <div className="fleetChangeRows">
            {vehicles
              .slice(0, 40)
              .map(row => (
                <div
                  key={row.vehicleId}
                >
                  <div>
                    <b>
                      {row.vehicleId}
                    </b>

                    <span>
                      {humanize(
                        row.fromDecisionState,
                      )}
                      {' → '}
                      {humanize(
                        row.toDecisionState,
                      )}
                    </span>
                  </div>

                  <div className="fleetChangeTags">
                    {row.transitions.map(
                      transition => (
                        <span
                          key={transition}
                        >
                          {humanize(
                            transition,
                          )}
                        </span>
                      ),
                    )}
                  </div>

                  <strong>
                    Attention{' '}
                    {signed(
                      row.attentionScoreDelta,
                      1,
                    )}
                  </strong>

                  <strong>
                    Load{' '}
                    {signed(
                      row.workloadUnitsDelta,
                      2,
                    )}
                  </strong>
                </div>
              ))}
          </div>
        </>
      )}

      <p className="fleetPlanningInterpretation">
        <Activity size={13} />
        Operational state change does not prove physical improvement,
        deterioration, reliability change or maintenance causality.
      </p>
    </div>
  );
}


function CapacityWorkspace({
  capacityUnits,
  setCapacityUnits,
  strategy,
  setStrategy,
  result,
  simulate,
  loading,
}: {
  capacityUnits: number;
  setCapacityUnits: (
    value: number,
  ) => void;
  strategy: string;
  setStrategy: (
    value: string,
  ) => void;
  result: CapacityResult | null;
  simulate: () => void;
  loading: boolean;
}) {
  const strategies = [
    'BALANCED',
    'ATTENTION_FIRST',
    'URGENT_FIRST',
    'COVERAGE_GAP_FIRST',
    'WORKLOAD_EFFICIENCY',
  ];

  return (
    <div className="fleetPlanningWorkspace">
      <div className="fleetPlanningWorkspaceTitle">
        <div>
          <SlidersHorizontal
            size={17}
          />
          <div>
            <span>
              PHASE 7.4 · CAPACITY &amp; MAINTENANCE PLANNING
            </span>
            <b>
              Allocate synthetic workflow capacity without writing workflow state
            </b>
          </div>
        </div>
      </div>

      <div className="capacityPlannerControls">
        <label>
          <span>
            Available workflow units
          </span>

          <input
            type="number"
            min={0}
            step={5}
            value={capacityUnits}
            onChange={event =>
              setCapacityUnits(
                Math.max(
                  0,
                  Number(
                    event.target.value,
                  ),
                ),
              )
            }
          />
        </label>

        <label>
          <span>
            Prioritization strategy
          </span>

          <select
            value={strategy}
            onChange={event =>
              setStrategy(
                event.target.value,
              )
            }
          >
            {strategies.map(
              value => (
                <option
                  key={value}
                  value={value}
                >
                  {humanize(value)}
                </option>
              ),
            )}
          </select>
        </label>

        <button
          onClick={simulate}
          disabled={loading}
        >
          <Play size={14} />
          Run no-write simulation
        </button>
      </div>

      {result && (
        <>
          <div className="fleetPlanningMetricGrid">
            <PlanningMetric
              label="Capacity utilization"
              value={percent(
                result.capacityUtilizationPct,
              )}
              detail={`${number(
                result.allocatedCapacityUnits,
                2,
              )} / ${number(
                result.requestedCapacityUnits,
                2,
              )} units`}
            />

            <PlanningMetric
              label="Selected vehicles"
              value={number(
                result.selectedVehicles,
              )}
              detail={`${number(
                result.deferredVehicles,
              )} deferred`}
            />

            <PlanningMetric
              label="Selected workload"
              value={number(
                result.selectedWorkloadUnits,
                2,
              )}
              detail={`${number(
                result.fleetWorkloadUnits,
                2,
              )} fleet total`}
            />

            <PlanningMetric
              label="Simulated gap coverage"
              value={number(
                result.simulatedAddressedCoverageGapInstances,
              )}
              detail={`${number(
                result.simulatedRemainingCoverageGapInstances,
              )} remain`}
            />
          </div>

          <div className="capacitySelectionRows">
            {result.selection
              .slice(0, 40)
              .map(row => (
                <div
                  key={row.vehicleId}
                >
                  <span className="capacityRank">
                    {row.rank}
                  </span>

                  <div>
                    <b>
                      {row.vehicleId}
                    </b>

                    <span>
                      {humanize(
                        row.hypothesisClass,
                      )}
                      {' · '}
                      {humanize(
                        row.decisionState,
                      )}
                    </span>
                  </div>

                  <small>
                    {humanize(
                      row.maintenanceTier,
                    )}
                  </small>

                  <strong>
                    {row.attentionScore.toFixed(
                      1,
                    )} attn
                  </strong>

                  <strong>
                    {row.workloadUnits.toFixed(
                      2,
                    )} units
                  </strong>

                  <strong>
                    {row.coverageGapCount} gaps
                  </strong>
                </div>
              ))}
          </div>
        </>
      )}

      <p className="fleetPlanningInterpretation">
        <Gauge size={13} />
        Capacity units are synthetic workflow-prioritization units,
        not technician hours, labor estimates or physical service duration.
        Simulation performs no write or automatic execution.
      </p>
    </div>
  );
}


function EffectivenessWorkspace({
  summary,
  policies,
}: {
  summary: EffectivenessSummary | null;
  policies: PolicyRow[];
}) {
  return (
    <div className="fleetPlanningWorkspace">
      <div className="fleetPlanningWorkspaceTitle">
        <div>
          <Workflow size={17} />
          <div>
            <span>
              PHASE 7.5 · POLICY &amp; WORKFLOW EFFECTIVENESS
            </span>
            <b>
              Lifecycle throughput and current workflow-target observation
            </b>
          </div>
        </div>
      </div>

      <div className="fleetPlanningMetricGrid">
        <PlanningMetric
          label="Materialized actions"
          value={number(
            summary?.totalActions,
          )}
          detail={`${number(
            summary?.currentMatches,
          )} current policy matches`}
        />

        <PlanningMetric
          label="Execution rate"
          value={percent(
            summary?.executionRatePct,
          )}
          detail={`${number(
            summary?.executed,
          )} executed`}
        />

        <PlanningMetric
          label="Approval rate"
          value={percent(
            summary?.approvalRatePct,
          )}
          detail={`${number(
            summary?.everApproved,
          )} ever approved`}
        />

        <PlanningMetric
          label="Executed target observed"
          value={percent(
            summary?.executedTargetObservationRatePct,
          )}
          detail={`${number(
            summary?.executedTargetObserved,
          )}/${number(
            summary?.evaluableExecutedActions,
          )} evaluable`}
        />
      </div>

      <div className="policyEffectivenessRows">
        {policies.map(policy => (
          <div
            key={policy.policyKey}
          >
            <div className="policyIdentity">
              <span
                className={
                  policy.enabled
                    ? 'policyEnabled'
                    : 'policyDisabled'
                }
              >
                {policy.enabled
                  ? 'ENABLED'
                  : 'DISABLED'}
              </span>

              <b>
                {policy.policyName}
              </b>

              <small>
                {policy.policyKey}
              </small>
            </div>

            <EffectivenessFact
              label="Current matches"
              value={number(
                policy.currentMatches,
              )}
            />

            <EffectivenessFact
              label="Actions"
              value={number(
                policy.materializedActions,
              )}
            />

            <EffectivenessFact
              label="Executed"
              value={number(
                policy.executed,
              )}
            />

            <EffectivenessFact
              label="Execution rate"
              value={percent(
                policy.executionRatePct,
              )}
            />

            <EffectivenessFact
              label="Median to approval"
              value={
                policy.medianHoursToApproval ==
                null
                  ? '—'
                  : `${policy.medianHoursToApproval.toFixed(
                      2,
                    )} h`
              }
            />

            <EffectivenessFact
              label="Median to execution"
              value={
                policy.medianHoursToExecution ==
                null
                  ? '—'
                  : `${policy.medianHoursToExecution.toFixed(
                      2,
                    )} h`
              }
            />

            <EffectivenessFact
              label="Target observed"
              value={percent(
                policy.executedTargetObservationRatePct,
              )}
            />
          </div>
        ))}
      </div>

      <p className="fleetPlanningInterpretation">
        <ShieldCheck size={13} />
        A currently observed workflow target does not prove that the
        policy caused it, prevented a physical failure, repaired a component,
        improved reliability or reduced physical risk.
      </p>
    </div>
  );
}


function WorkspaceButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      className={
        active
          ? 'active'
          : ''
      }
      onClick={onClick}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}


function PlanningMetric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="fleetPlanningMetric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}


function EffectivenessFact({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="policyEffectivenessFact">
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}
