import {
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  Eye,
  GitBranch,
  Layers3,
  ListChecks,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  UserCheck,
  Workflow,
} from 'lucide-react';

import { ClosedLoopOutcomesPanel } from './ClosedLoopOutcomesPanel';

import './FleetCommandOperations.css';


const API =
  import.meta.env.VITE_API_URL ??
  'http://localhost:8000';


type Workspace =
  | 'COMMAND'
  | 'EXPLAINABILITY'
  | 'QUEUE'
  | 'CLOSED_LOOP';

type CommandView =
  | 'OVERVIEW'
  | 'QUEUES'
  | 'COHORTS'
  | 'FACTORS';

type ExplainabilityView =
  | 'OVERVIEW'
  | 'ATTENTION'
  | 'EVIDENCE'
  | 'LINEAGE';

type QueueView =
  | 'OVERVIEW'
  | 'ACTIVE'
  | 'OWNERSHIP'
  | 'WORKFLOW';

type ClosedLoopView =
  | 'EVALUATE'
  | 'RESULTS'
  | 'RECOMMENDATIONS'
  | 'OUTCOMES'
  | 'LIFECYCLE';


type Props = {
  runId?: number;
  selectedVehicleId?: string | null;
  onSelectVehicle?: (
    vehicleId: string,
  ) => void;
};


type CommandSummary = {
  runId: number;
  experimentId: string;
  lineage: string;
  rulesVersion: string;

  totalVehicles: number;
  nonHealthyHypotheses: number;
  vehiclesWithCases: number;
  attentionRequired: number;
  vehiclesWithCoverageGaps: number;
  coverageGapInstances: number;
  totalWorkloadUnits: number;
  meanAttentionScore: number;

  byDecisionState: Array<{
    state: string;
    vehicles: number;
  }>;

  queues: Array<{
    queue: string;
    vehicles: number;
  }>;

  workflow: {
    rulesVersion: string;
    totalPolicies: number;
    totalActions: number;
    pendingApproval: number;
    approvedReady: number;
    rejected: number;
    executed: number;
    everApproved: number;
    currentMatches: number;
  };

  attentionExplanation: {
    rulesVersion: string;
    reconciledVehicleCount: number;
    cappedVehicleCount: number;
    topFactors: Array<{
      factor: string;
      vehicleCount: number;
      totalContribution: number;
      meanContributionWhenPresent: number;
    }>;
  };
};


type CommandVehicle = {
  vehicleId: string;
  topClass: string;
  topConfidence: number;
  decisionState: string;
  attentionScore: number;
  workloadUnits: number;
  maintenanceTier: string | null;
  reviewPriority: string | null;
  caseId: number | null;
  assignedTo: string | null;
  trajectoryEligible: boolean | null;
  coverageGaps: string[];
  automationStatus: string | null;
  queues: string[];
};


type CommandQueueGroup = {
  queue: string;
  vehicles: number;
  topVehicles: CommandVehicle[];
};


type CommandQueuesResponse = {
  runId: number;
  experimentId: string;
  rulesVersion: string;
  queueCount: number;
  queues: CommandQueueGroup[];
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
};


type CommandCohorts = {
  runId: number;
  experimentId: string;
  dimension: string;
  measure: string;
  totalCohorts: number;
  returnedCohorts: number;
  cohorts: CohortRow[];
};


type ExplainabilitySummary = {
  runId: number;
  experimentId: string;
  lineage: string;
  rulesVersion: string;
  vehicleCount: number;
  reconciledVehicleCount: number;
  cappedVehicleCount: number;
  factors: Array<{
    factor: string;
    vehicleCount: number;
    totalContribution: number;
    meanContributionWhenPresent: number;
  }>;
};


type AttentionComponent = {
  factor: string;
  source: string;
  observedValue: unknown;
  contribution: number;
  explanation: string;
};


type ExplainabilityVehicleRow = {
  vehicleId: string;
  topClass: string;
  topConfidence: number;
  decisionState: string;
  attentionScore: number;
  rawAttentionScore: number;
  capApplied: boolean;
  reconciles: boolean;
  coverageGaps: string[];
  componentCount: number;
  topFactors: AttentionComponent[];
};


type ExplainabilityVehicles = {
  runId: number;
  experimentId: string;
  totalMatched: number;
  returned: number;
  vehicles: ExplainabilityVehicleRow[];
};


type ExplainabilityDetail = {
  runId: number;
  experimentId: string;
  vehicleId: string;

  attention: {
    attentionScore: number;
    rawAttentionScore: number;
    capApplied: boolean;
    capAdjustment: number;
    explainedScore: number;
    reconciles: boolean;
    coverageGaps: string[];
    components: AttentionComponent[];
  };

  evidenceInventory: {
    presentLayerCount: number;
    totalLayerCount: number;
    observableModelEvidenceCount: number;
    coverageGapCount: number;
    automationActionCount: number;
    layers: Array<{
      layer: string;
      present: boolean;
      evidenceItemCount: number;
      sourceId: number | null;
    }>;
  };

  lineage: {
    nodes: Array<{
      id: string;
      layer: string;
      label: string | null;
      present: boolean;
    }>;
    edges: Array<{
      from: string;
      to: string;
      relation: string;
      causal: boolean;
    }>;
    lineagePath: string[];
  };

  observableModelEvidence: Array<{
    feature?: string;
    label?: string;
    value?: number;
    unit?: string | null;
  }>;
};


type QueueSummary = {
  runId: number;
  experimentId: string;
  rulesVersion: string;
  totalRecommendations: number;
  activeRecommendations: number;
  terminalRecommendations: number;
  unassignedActive: number;
  overdueActive: number;

  byPriority: Array<{
    priority: string;
    active: number;
  }>;

  byStatus: Array<{
    status: string;
    count: number;
  }>;

  byAgeBucket: Array<{
    ageBucket: string;
    active: number;
  }>;

  assignment: {
    total: number;
    assigned: number;
    unassigned: number;
  };
};


type QueueRecord = {
  id: number;
  runId: number;
  experimentId: string;
  vehicleId: string;
  caseId: number | null;
  recommendationType: string;
  priority: string;
  priorityRank: number;
  status: string;
  active: boolean;
  approvalRequired: boolean;
  assignedTo: string | null;
  assignedAt: string | null;
  unassigned: boolean;
  ageHours: number;
  ageBucket: string;
  reviewTargetHours: number;
  reviewTargetOverdue: boolean;
  createdAt: string;
  updatedAt: string;
  queueRank: number;
};


type QueueResponse = {
  runId: number;
  experimentId: string;
  rulesVersion: string;
  totalMatched: number;
  returned: number;
  queue: QueueRecord[];
};


type Recommendation = {
  id: number;
  runId: number;
  experimentId: string;
  vehicleId: string;
  caseId: number | null;
  recommendationKey: string;
  rulesVersion: string;
  recommendationType: string;
  priority: string;
  status: string;
  approvalRequired: boolean;
  sourceKey: string;
  reason: string;
  createdAt: string;
  updatedAt: string;
  materializedBy: string;
  lastActor: string;
  assignedTo: string | null;
  assignedAt: string | null;
};


type RecommendationResponse = {
  runId: number;
  experimentId: string;
  totalMatched: number;
  returned: number;
  recommendations: Recommendation[];
};


type EvaluationResponse = {
  runId: number;
  experimentId: string;
  rulesVersion: string;
  evaluatedVehicles: number;
  candidateCount: number;
  materializeRequested: boolean;
  createdCount: number;
  existingCount: number;
  totalPersistedTargets?: number;

  byType: Array<{
    recommendationType: string;
    count: number;
  }>;

  byPriority: Array<{
    priority: string;
    count: number;
  }>;

  candidates?: Array<{
    vehicleId: string;
    caseId: number | null;
    recommendationType: string;
    priority: string;
    reason: string;
    sourceKey: string;
    recommendationKey: string;
  }>;
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


function percent(
  value: number | null | undefined,
  digits = 1,
) {
  if (value == null) return '—';

  return `${value.toFixed(digits)}%`;
}


function withRun(
  path: string,
  runId?: number,
) {
  const separator =
    path.includes('?')
      ? '&'
      : '?';

  return runId
    ? `${API}${path}${separator}run_id=${runId}`
    : `${API}${path}`;
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


function postJson<T>(
  url: string,
  body: unknown,
) {
  return json<T>(
    url,
    {
      method: 'POST',
      headers: {
        'Content-Type':
          'application/json',
      },
      body: JSON.stringify(body),
    },
  );
}


function nextAction(
  status: string,
) {
  if (status === 'PROPOSED') {
    return {
      label: 'Acknowledge',
      path: 'acknowledge',
    };
  }

  if (status === 'ACKNOWLEDGED') {
    return {
      label: 'Request approval',
      path: 'request-approval',
    };
  }

  if (
    status ===
    'APPROVAL_REQUIRED'
  ) {
    return {
      label: 'Approve',
      path: 'approve',
    };
  }

  if (status === 'APPROVED') {
    return {
      label: 'Mark execution ready',
      path: 'mark-execution-ready',
    };
  }

  if (
    status ===
    'EXECUTION_READY'
  ) {
    return {
      label: 'Execute workflow',
      path: 'execute',
    };
  }

  return null;
}


export function FleetCommandOperations({
  runId,
  selectedVehicleId,
  onSelectVehicle,
}: Props) {
  const [
    workspace,
    setWorkspace,
  ] = useState<Workspace>(
    'COMMAND',
  );

  const [
    commandView,
    setCommandView,
  ] = useState<CommandView>(
    'OVERVIEW',
  );

  const [
    explainabilityView,
    setExplainabilityView,
  ] = useState<ExplainabilityView>(
    'OVERVIEW',
  );

  const [
    queueView,
    setQueueView,
  ] = useState<QueueView>(
    'OVERVIEW',
  );

  const [
    closedLoopView,
    setClosedLoopView,
  ] = useState<ClosedLoopView>(
    'EVALUATE',
  );

  const [
    command,
    setCommand,
  ] = useState<CommandSummary | null>(
    null,
  );

  const [
    commandQueues,
    setCommandQueues,
  ] = useState<CommandQueuesResponse | null>(
    null,
  );

  const [
    cohortDimension,
    setCohortDimension,
  ] = useState('factory');

  const [
    cohorts,
    setCohorts,
  ] = useState<CommandCohorts | null>(
    null,
  );

  const [
    explainability,
    setExplainability,
  ] = useState<ExplainabilitySummary | null>(
    null,
  );

  const [
    explainabilityVehicles,
    setExplainabilityVehicles,
  ] = useState<ExplainabilityVehicleRow[]>(
    [],
  );

  const [
    explainabilityVehicleId,
    setExplainabilityVehicleId,
  ] = useState<string | null>(
    selectedVehicleId ?? null,
  );

  const [
    explainabilityDetail,
    setExplainabilityDetail,
  ] = useState<ExplainabilityDetail | null>(
    null,
  );

  const [
    queueSummary,
    setQueueSummary,
  ] = useState<QueueSummary | null>(
    null,
  );

  const [
    queue,
    setQueue,
  ] = useState<QueueRecord[]>(
    [],
  );

  const [
    recommendations,
    setRecommendations,
  ] = useState<Recommendation[]>(
    [],
  );

  const [
    evaluation,
    setEvaluation,
  ] = useState<EvaluationResponse | null>(
    null,
  );

  const [
    actor,
    setActor,
  ] = useState('operator');

  const [
    loading,
    setLoading,
  ] = useState(false);

  const [
    actionId,
    setActionId,
  ] = useState<number | null>(
    null,
  );

  const [
    error,
    setError,
  ] = useState<string | null>(
    null,
  );


  async function refreshCommand() {
    const [
      nextSummary,
      nextQueues,
      nextCohorts,
    ] = await Promise.all([
      json<CommandSummary>(
        withRun(
          '/api/v1/diagnostics/fleet-command/summary',
          runId,
        ),
      ),

      json<CommandQueuesResponse>(
        withRun(
          '/api/v1/diagnostics/fleet-command/queues?limit=5',
          runId,
        ),
      ),

      json<CommandCohorts>(
        withRun(
          `/api/v1/diagnostics/fleet-command/cohorts?dimension=${encodeURIComponent(
            cohortDimension,
          )}&measure=nonHealthy&limit=8`,
          runId,
        ),
      ),
    ]);

    setCommand(nextSummary);
    setCommandQueues(nextQueues);
    setCohorts(nextCohorts);
  }


  async function refreshExplainability() {
    const [
      nextSummary,
      nextVehicles,
    ] = await Promise.all([
      json<ExplainabilitySummary>(
        withRun(
          '/api/v1/diagnostics/explainability/summary',
          runId,
        ),
      ),

      json<ExplainabilityVehicles>(
        withRun(
          '/api/v1/diagnostics/explainability/vehicles?limit=50',
          runId,
        ),
      ),
    ]);

    setExplainability(
      nextSummary,
    );

    setExplainabilityVehicles(
      nextVehicles.vehicles,
    );

    setExplainabilityVehicleId(
      current => {
        if (
          current &&
          nextVehicles.vehicles.some(
            vehicle =>
              vehicle.vehicleId ===
              current,
          )
        ) {
          return current;
        }

        if (
          selectedVehicleId &&
          nextVehicles.vehicles.some(
            vehicle =>
              vehicle.vehicleId ===
              selectedVehicleId,
          )
        ) {
          return selectedVehicleId;
        }

        return (
          nextVehicles.vehicles[0]
            ?.vehicleId ??
          null
        );
      },
    );
  }


  async function refreshQueue() {
    const [
      nextSummary,
      nextQueue,
    ] = await Promise.all([
      json<QueueSummary>(
        withRun(
          '/api/v1/diagnostics/decision-queue/summary',
          runId,
        ),
      ),

      json<QueueResponse>(
        withRun(
          '/api/v1/diagnostics/decision-queue?limit=100',
          runId,
        ),
      ),
    ]);

    setQueueSummary(
      nextSummary,
    );

    setQueue(
      nextQueue.queue,
    );
  }


  async function refreshClosedLoop() {
    const result =
      await json<RecommendationResponse>(
        withRun(
          '/api/v1/diagnostics/closed-loop/recommendations?limit=100',
          runId,
        ),
      );

    setRecommendations(
      result.recommendations,
    );
  }


  async function refreshActiveWorkspace() {
    setLoading(true);

    try {
      if (workspace === 'COMMAND') {
        await refreshCommand();
      } else if (workspace === 'EXPLAINABILITY') {
        await refreshExplainability();
      } else if (workspace === 'QUEUE') {
        await refreshQueue();
      } else {
        await refreshClosedLoop();
      }

      setError(null);
    } catch (refreshError) {
      setError(
        refreshError instanceof Error
          ? refreshError.message
          : 'Fleet Command APIs unavailable',
      );
    } finally {
      setLoading(false);
    }
  }


  useEffect(() => {
    void refreshActiveWorkspace();

    const timer = setInterval(
      () => {
        void refreshActiveWorkspace();
      },
      20000,
    );

    return () =>
      clearInterval(timer);
  }, [runId, workspace]);


  useEffect(() => {
    if (workspace !== 'COMMAND') {
      return;
    }

    void refreshCommand().catch(
      refreshError => {
        setError(
          refreshError instanceof Error
            ? refreshError.message
            : 'Command cohort data unavailable',
        );
      },
    );
  }, [cohortDimension, workspace, runId]);


  useEffect(() => {
    if (workspace !== 'EXPLAINABILITY') {
      return;
    }

    if (!explainabilityVehicleId) {
      setExplainabilityDetail(
        null,
      );
      return;
    }

    void json<ExplainabilityDetail>(
      withRun(
        `/api/v1/diagnostics/explainability/vehicles/${encodeURIComponent(
          explainabilityVehicleId,
        )}`,
        runId,
      ),
    )
      .then(
        setExplainabilityDetail,
      )
      .catch(detailError => {
        setError(
          detailError instanceof Error
            ? detailError.message
            : 'Explainability detail unavailable',
        );
      });
  }, [
    explainabilityVehicleId,
    runId,
    workspace,
  ]);


  const topQueueGroups =
    useMemo(
      () =>
        commandQueues?.queues
          .filter(
            row =>
              row.vehicles > 0,
          )
          .slice(0, 7) ??
        [],
      [commandQueues],
    );


  const activeRecommendations =
    useMemo(
      () =>
        recommendations.filter(
          row =>
            ![
              'EXECUTED',
              'REJECTED',
              'CANCELLED',
              'SUPERSEDED',
            ].includes(
              row.status,
            ),
        ),
      [recommendations],
    );


  const unassignedQueue =
    useMemo(
      () =>
        queue.filter(
          row =>
            !row.assignedTo,
        ),
      [queue],
    );


  const assignedQueue =
    useMemo(
      () =>
        queue.filter(
          row =>
            Boolean(row.assignedTo),
        ),
      [queue],
    );


  async function evaluate(
    materialize: boolean,
  ) {
    if (
      materialize &&
      !selectedVehicleId
    ) {
      setError(
        'Select a vehicle before materializing closed-loop recommendations.',
      );
      return;
    }

    setLoading(true);

    try {
      const result =
        await postJson<EvaluationResponse>(
          withRun(
            '/api/v1/diagnostics/closed-loop/recommendations/evaluate',
            runId,
          ),
          {
            actor:
              actor.trim() ||
              'operator',
            materialize,

            // Preview may evaluate the complete selected run.
            // Persistent materialization is intentionally
            // restricted to the explicitly selected vehicle.
            vehicleIds:
              materialize
                ? [selectedVehicleId]
                : null,
          },
        );

      setEvaluation(result);
      setClosedLoopView(
        'RESULTS',
      );

      if (materialize) {
        await Promise.all([
          refreshQueue(),
          refreshClosedLoop(),
        ]);
      }

      setError(null);
    } catch (evaluateError) {
      setError(
        evaluateError instanceof Error
          ? evaluateError.message
          : 'Closed-loop evaluation failed',
      );
    } finally {
      setLoading(false);
    }
  }


  async function assign(
    recommendationId: number,
    assignedTo: string | null,
  ) {
    setActionId(
      recommendationId,
    );

    try {
      await postJson(
        withRun(
          `/api/v1/diagnostics/decision-queue/${recommendationId}/assign`,
          runId,
        ),
        {
          actor:
            actor.trim() ||
            'operator',
          assignedTo,
          note:
            'Decision Queue ownership update.',
        },
      );

      await Promise.all([
        refreshQueue(),
        refreshClosedLoop(),
      ]);

      setError(null);
    } catch (assignmentError) {
      setError(
        assignmentError instanceof Error
          ? assignmentError.message
          : 'Assignment update failed',
      );
    } finally {
      setActionId(null);
    }
  }


  async function transition(
    recommendationId: number,
    path: string,
  ) {
    setActionId(
      recommendationId,
    );

    try {
      await postJson(
        withRun(
          `/api/v1/diagnostics/decision-queue/${recommendationId}/${path}`,
          runId,
        ),
        {
          actor:
            actor.trim() ||
            'operator',
          note:
            'Explicit operator decision from Fleet Command.',
        },
      );

      await Promise.all([
        refreshQueue(),
        refreshClosedLoop(),
        refreshCommand(),
      ]);

      setError(null);
    } catch (transitionError) {
      setError(
        transitionError instanceof Error
          ? transitionError.message
          : 'Lifecycle transition failed',
      );
    } finally {
      setActionId(null);
    }
  }


  function selectExplainabilityVehicle(
    vehicleId: string,
  ) {
    setExplainabilityVehicleId(
      vehicleId,
    );

    onSelectVehicle?.(
      vehicleId,
    );
  }


  return (
    <section className="fleetCommandOperations">
      <div className="fleetCommandHeader">
        <div>
          <span className="diagnosticSectionLabel">
            PHASES 7.6–8.1 · FLEET COMMAND & OPERATIONS
          </span>

          <h2>
            Evidence, command and human-controlled execution
          </h2>

          <p className="muted">
            Operational intelligence and workflow control for selected Run{' '}
            <b>
              {command?.runId ??
                runId ??
                '—'}
            </b>
            . Queue priority is not physical failure risk, and workflow
            execution is not proof of physical maintenance.
          </p>
        </div>

        <button
          className="fleetOpsRefresh"
          type="button"
          onClick={() =>
            void refreshActiveWorkspace()
          }
          disabled={loading}
        >
          <RefreshCw
            size={15}
            className={
              loading
                ? 'spinning'
                : ''
            }
          />
          Refresh
        </button>
      </div>

      {error && (
        <div className="diagnosticError">
          <AlertTriangle
            size={15}
          />
          <span>{error}</span>
        </div>
      )}

      <div className="fleetOpsTruthBoundary">
        <ShieldCheck
          size={16}
        />
        <span>
          Model evidence ≠ causality · attention ≠ SHAP · queue priority ≠ physical risk · execution ≠ physical repair.
        </span>
      </div>

      <div className="fleetOpsTabs">
        <WorkspaceButton
          active={
            workspace ===
            'COMMAND'
          }
          icon={
            <Activity size={15} />
          }
          onClick={() =>
            setWorkspace(
              'COMMAND',
            )
          }
        >
          Command Center
        </WorkspaceButton>

        <WorkspaceButton
          active={
            workspace ===
            'EXPLAINABILITY'
          }
          icon={
            <GitBranch size={15} />
          }
          onClick={() =>
            setWorkspace(
              'EXPLAINABILITY',
            )
          }
        >
          Explainability
        </WorkspaceButton>

        <WorkspaceButton
          active={
            workspace ===
            'QUEUE'
          }
          icon={
            <ListChecks
              size={15}
            />
          }
          onClick={() =>
            setWorkspace(
              'QUEUE',
            )
          }
        >
          Decision Queue
        </WorkspaceButton>

        <WorkspaceButton
          active={
            workspace ===
            'CLOSED_LOOP'
          }
          icon={
            <Workflow size={15} />
          }
          onClick={() =>
            setWorkspace(
              'CLOSED_LOOP',
            )
          }
        >
          Closed Loop
        </WorkspaceButton>
      </div>

      {workspace ===
        'COMMAND' && (
        <div className="fleetOpsWorkspace">
          <SubTabs
            ariaLabel="Command Center views"
            active={commandView}
            onChange={value =>
              setCommandView(
                value as CommandView,
              )
            }
            tabs={[
              ['OVERVIEW', 'Overview'],
              ['QUEUES', 'Operator Queues'],
              ['COHORTS', 'Cohorts'],
              ['FACTORS', 'Attention Factors'],
            ]}
          />

          {commandView ===
            'OVERVIEW' && (
            <div className="fleetOpsSubTabPanel">
              <div className="fleetOpsMetricGrid">
                <Metric
                  label="Fleet vehicles"
                  value={number(
                    command?.totalVehicles,
                  )}
                  detail={`${number(
                    command?.nonHealthyHypotheses,
                  )} non-healthy hypotheses`}
                />

                <Metric
                  label="Attention required"
                  value={number(
                    command?.attentionRequired,
                  )}
                  detail={`Mean score ${number(
                    command?.meanAttentionScore,
                    1,
                  )}`}
                />

                <Metric
                  label="Workflow load"
                  value={number(
                    command?.totalWorkloadUnits,
                    2,
                  )}
                  detail="Synthetic workflow units"
                />

                <Metric
                  label="Coverage gaps"
                  value={number(
                    command?.coverageGapInstances,
                  )}
                  detail={`${number(
                    command?.vehiclesWithCoverageGaps,
                  )} vehicles`}
                />

                <Metric
                  label="Pending approvals"
                  value={number(
                    command?.workflow
                      ?.pendingApproval,
                  )}
                  detail={`${number(
                    command?.workflow
                      ?.executed,
                  )} automation actions executed`}
                />
              </div>

              <div className="fleetOpsOverviewStrip">
                <article className="panel fleetOpsPanel">
                  <div className="panelTitle">
                    <span>
                      DECISION STATES
                    </span>
                    <h3>
                      Fleet operating picture
                    </h3>
                  </div>

                  <div className="fleetOpsSummaryList">
                    {(command?.byDecisionState ?? [])
                      .slice(0, 8)
                      .map(row => (
                        <div key={row.state}>
                          <span>
                            {humanize(row.state)}
                          </span>
                          <strong>
                            {number(row.vehicles)}
                          </strong>
                        </div>
                      ))}
                  </div>
                </article>

                <article className="panel fleetOpsPanel">
                  <div className="panelTitle">
                    <span>
                      WORKFLOW
                    </span>
                    <h3>
                      Human-control snapshot
                    </h3>
                  </div>

                  <div className="fleetOpsSummaryList">
                    <div>
                      <span>Policies</span>
                      <strong>{number(command?.workflow?.totalPolicies)}</strong>
                    </div>
                    <div>
                      <span>Actions</span>
                      <strong>{number(command?.workflow?.totalActions)}</strong>
                    </div>
                    <div>
                      <span>Approved ready</span>
                      <strong>{number(command?.workflow?.approvedReady)}</strong>
                    </div>
                    <div>
                      <span>Executed</span>
                      <strong>{number(command?.workflow?.executed)}</strong>
                    </div>
                  </div>
                </article>
              </div>
            </div>
          )}

          {commandView ===
            'QUEUES' && (
            <div className="fleetOpsSubTabPanel">
              <article className="panel fleetOpsPanel">
                <div className="panelTitleRow">
                  <div className="panelTitle">
                    <span>
                      OPERATOR QUEUES
                    </span>
                    <h3>
                      Command attention
                    </h3>
                  </div>

                  <span className="methodBadge">
                    {number(
                      commandQueues
                        ?.queueCount,
                    )}{' '}
                    QUEUES
                  </span>
                </div>

                <div className="fleetOpsQueueGroups fleetOpsQueueGroupsExpanded">
                  {topQueueGroups.map(
                    group => (
                      <div
                        key={
                          group.queue
                        }
                        className="fleetOpsQueueGroup"
                      >
                        <div className="fleetOpsQueueGroupHead">
                          <div>
                            <b>
                              {humanize(
                                group.queue,
                              )}
                            </b>
                            <span>
                              {group.vehicles}{' '}
                              vehicles
                            </span>
                          </div>

                          <ArrowRight
                            size={14}
                          />
                        </div>

                        {group.topVehicles
                          .slice(0, 5)
                          .map(
                            vehicle => (
                              <button
                                type="button"
                                className="fleetOpsVehicleMini"
                                key={`${group.queue}-${vehicle.vehicleId}`}
                                onClick={() => {
                                  selectExplainabilityVehicle(
                                    vehicle.vehicleId,
                                  );

                                  setExplainabilityView(
                                    'ATTENTION',
                                  );

                                  setWorkspace(
                                    'EXPLAINABILITY',
                                  );
                                }}
                              >
                                <b>
                                  {
                                    vehicle.vehicleId
                                  }
                                </b>

                                <span>
                                  {humanize(
                                    vehicle.topClass,
                                  )}
                                </span>

                                <strong>
                                  {number(
                                    vehicle.attentionScore,
                                    1,
                                  )}
                                </strong>
                              </button>
                            ),
                          )}
                      </div>
                    ),
                  )}
                </div>
              </article>
            </div>
          )}

          {commandView ===
            'COHORTS' && (
            <div className="fleetOpsSubTabPanel">
              <article className="panel fleetOpsPanel">
                <div className="panelTitleRow">
                  <div className="panelTitle">
                    <span>
                      NORMALIZED COHORT WATCH
                    </span>
                    <h3>
                      Operational representation
                    </h3>
                  </div>

                  <select
                    className="fleetOpsSelect"
                    value={
                      cohortDimension
                    }
                    onChange={event =>
                      setCohortDimension(
                        event.target
                          .value,
                      )
                    }
                  >
                    <option value="factory">
                      Factory
                    </option>
                    <option value="model">
                      Model
                    </option>
                    <option value="firmware">
                      Firmware
                    </option>
                    <option value="pumpRevision">
                      Pump revision
                    </option>
                    <option value="hypothesisClass">
                      Hypothesis class
                    </option>
                  </select>
                </div>

                <p className="muted">
                  Normalized Phase 7.2 representation. Higher rate does not
                  establish higher physical failure risk.
                </p>

                <div className="fleetOpsCohortList">
                  {(cohorts?.cohorts ??
                    []).map(
                    row => (
                      <div
                        className="fleetOpsCohortRow"
                        key={
                          row.value
                        }
                      >
                        <div>
                          <b>
                            {humanize(
                              row.value,
                            )}
                          </b>
                          <span>
                            {row.populationCount}{' '}
                            vehicles ·{' '}
                            {percent(
                              row.populationSharePct,
                            )}{' '}
                            fleet
                          </span>
                        </div>

                        <div>
                          <span>
                            Non-healthy
                          </span>
                          <strong>
                            {percent(
                              row.nonHealthyRatePct,
                            )}
                          </strong>
                        </div>

                        <div>
                          <span>
                            Attention
                          </span>
                          <strong>
                            {percent(
                              row.attentionRatePct,
                            )}
                          </strong>
                        </div>

                        <div>
                          <span>
                            Workload / 100
                          </span>
                          <strong>
                            {number(
                              row.workloadUnitsPer100Vehicles,
                              1,
                            )}
                          </strong>
                        </div>
                      </div>
                    ),
                  )}
                </div>
              </article>
            </div>
          )}

          {commandView ===
            'FACTORS' && (
            <div className="fleetOpsSubTabPanel">
              <article className="panel fleetOpsPanel">
                <div className="panelTitleRow">
                  <div className="panelTitle">
                    <span>
                      ATTENTION EXPLANATION
                    </span>
                    <h3>
                      Deterministic score factors
                    </h3>
                  </div>

                  <span className="methodBadge">
                    {number(
                      command
                        ?.attentionExplanation
                        ?.reconciledVehicleCount,
                    )}
                    /
                    {number(
                      command?.totalVehicles,
                    )}{' '}
                    RECONCILED
                  </span>
                </div>

                <div className="fleetOpsFactorGrid fleetOpsFactorGridExpanded">
                  {(command
                    ?.attentionExplanation
                    ?.topFactors ??
                    [])
                    .slice(0, 12)
                    .map(
                      factor => (
                        <div
                          key={
                            factor.factor
                          }
                        >
                          <span>
                            {humanize(
                              factor.factor,
                            )}
                          </span>

                          <strong>
                            {number(
                              factor.totalContribution,
                              1,
                            )}
                          </strong>

                          <small>
                            {factor.vehicleCount}{' '}
                            vehicles · mean{' '}
                            {number(
                              factor.meanContributionWhenPresent,
                              2,
                            )}
                          </small>
                        </div>
                      ),
                    )}
                </div>
              </article>
            </div>
          )}
        </div>
      )}

      {workspace ===
        'EXPLAINABILITY' && (
        <div className="fleetOpsWorkspace">
          <SubTabs
            ariaLabel="Explainability views"
            active={explainabilityView}
            onChange={value =>
              setExplainabilityView(
                value as ExplainabilityView,
              )
            }
            tabs={[
              ['OVERVIEW', 'Overview'],
              ['ATTENTION', 'Attention'],
              ['EVIDENCE', 'Evidence'],
              ['LINEAGE', 'Lineage'],
            ]}
          />

          {explainabilityView ===
            'OVERVIEW' && (
            <div className="fleetOpsSubTabPanel">
              <div className="fleetOpsMetricGrid">
                <Metric
                  label="Vehicles explained"
                  value={number(
                    explainability
                      ?.vehicleCount,
                  )}
                  detail="Selected-run population"
                />

                <Metric
                  label="Score reconciliations"
                  value={number(
                    explainability
                      ?.reconciledVehicleCount,
                  )}
                  detail="Canonical Phase 7.0 math"
                />

                <Metric
                  label="Capped scores"
                  value={number(
                    explainability
                      ?.cappedVehicleCount,
                  )}
                  detail="Raw score exceeded 100"
                />
              </div>

              <article className="panel fleetOpsPanel">
                <div className="panelTitleRow">
                  <div className="panelTitle">
                    <span>
                      EXPLANATION COVERAGE
                    </span>
                    <h3>
                      Leading deterministic factors
                    </h3>
                  </div>

                  <span className="methodBadge">
                    NOT SHAP
                  </span>
                </div>

                <div className="fleetOpsFactorGrid">
                  {(explainability?.factors ?? [])
                    .slice(0, 8)
                    .map(factor => (
                      <div key={factor.factor}>
                        <span>{humanize(factor.factor)}</span>
                        <strong>{number(factor.totalContribution, 1)}</strong>
                        <small>{factor.vehicleCount} vehicles</small>
                      </div>
                    ))}
                </div>
              </article>
            </div>
          )}

          {explainabilityView ===
            'ATTENTION' && (
            <div className="fleetOpsSubTabPanel">
              <div className="fleetOpsExplainGrid">
                <article className="panel fleetOpsPanel">
                  <div className="panelTitleRow">
                    <div className="panelTitle">
                      <span>
                        VEHICLES
                      </span>
                      <h3>
                        Attention explanations
                      </h3>
                    </div>

                    <Search
                      size={15}
                    />
                  </div>

                  <div className="fleetOpsExplainVehicleList">
                    {explainabilityVehicles.map(
                      vehicle => (
                        <button
                          type="button"
                          key={
                            vehicle.vehicleId
                          }
                          className={
                            explainabilityVehicleId ===
                            vehicle.vehicleId
                              ? 'fleetOpsExplainVehicle selected'
                              : 'fleetOpsExplainVehicle'
                          }
                          onClick={() =>
                            selectExplainabilityVehicle(
                              vehicle.vehicleId,
                            )
                          }
                        >
                          <div>
                            <b>
                              {
                                vehicle.vehicleId
                              }
                            </b>
                            <span>
                              {humanize(
                                vehicle.topClass,
                              )}
                            </span>
                          </div>

                          <div>
                            <strong>
                              {number(
                                vehicle.attentionScore,
                                1,
                              )}
                            </strong>
                            <span>
                              attention
                            </span>
                          </div>

                          {vehicle.reconciles && (
                            <CheckCircle2
                              size={14}
                            />
                          )}
                        </button>
                      ),
                    )}
                  </div>
                </article>

                <article className="panel fleetOpsPanel">
                  <div className="panelTitleRow">
                    <div className="panelTitle">
                      <span>
                        ATTENTION DECOMPOSITION
                      </span>
                      <h3>
                        {explainabilityDetail
                          ?.vehicleId ??
                          'Select vehicle'}
                      </h3>
                    </div>

                    <span className="methodBadge">
                      NOT SHAP
                    </span>
                  </div>

                  {explainabilityDetail ? (
                    <>
                      <div className="fleetOpsAttentionHero">
                        <div>
                          <span>
                            Canonical score
                          </span>
                          <strong>
                            {number(
                              explainabilityDetail
                                .attention
                                .attentionScore,
                              1,
                            )}
                          </strong>
                        </div>

                        <ArrowRight
                          size={18}
                        />

                        <div>
                          <span>
                            Explained score
                          </span>
                          <strong>
                            {number(
                              explainabilityDetail
                                .attention
                                .explainedScore,
                              1,
                            )}
                          </strong>
                        </div>

                        <div>
                          <span>
                            Raw score
                          </span>
                          <strong>
                            {number(
                              explainabilityDetail
                                .attention
                                .rawAttentionScore,
                              1,
                            )}
                          </strong>
                        </div>
                      </div>

                      <div className="fleetOpsComponentList">
                        {explainabilityDetail
                          .attention
                          .components.map(
                            (
                              component,
                              index,
                            ) => (
                              <div
                                key={`${component.factor}-${index}`}
                                className="fleetOpsComponentRow"
                              >
                                <div>
                                  <b>
                                    {humanize(
                                      component.factor,
                                    )}
                                  </b>
                                  <span>
                                    {humanize(
                                      component.source,
                                    )}
                                  </span>
                                </div>

                                <strong>
                                  {component.contribution >
                                  0
                                    ? '+'
                                    : ''}
                                  {number(
                                    component.contribution,
                                    3,
                                  )}
                                </strong>
                              </div>
                            ),
                          )}
                      </div>
                    </>
                  ) : (
                    <div className="empty">
                      Select a vehicle to inspect deterministic attention
                      contributions.
                    </div>
                  )}
                </article>
              </div>
            </div>
          )}

          {explainabilityView ===
            'EVIDENCE' && (
            <div className="fleetOpsSubTabPanel">
              <VehicleContextBar
                vehicleId={explainabilityVehicleId}
                vehicles={explainabilityVehicles}
                onChange={selectExplainabilityVehicle}
              />

              {explainabilityDetail ? (
                <article className="panel fleetOpsPanel">
                  <div className="panelTitleRow">
                    <div className="panelTitle">
                      <span>
                        EVIDENCE INVENTORY
                      </span>
                      <h3>
                        Operational layers
                      </h3>
                    </div>

                    <span className="methodBadge">
                      {explainabilityDetail.evidenceInventory.presentLayerCount}
                      /
                      {explainabilityDetail.evidenceInventory.totalLayerCount}{' '}
                      PRESENT
                    </span>
                  </div>

                  <div className="fleetOpsEvidenceLayers fleetOpsEvidenceLayersExpanded">
                    {explainabilityDetail
                      .evidenceInventory
                      .layers.map(
                        layer => (
                          <div
                            key={
                              layer.layer
                            }
                            className={
                              layer.present
                                ? 'fleetOpsEvidenceLayer present'
                                : 'fleetOpsEvidenceLayer'
                            }
                          >
                            <Layers3
                              size={15}
                            />

                            <div>
                              <b>
                                {humanize(
                                  layer.layer,
                                )}
                              </b>
                              <span>
                                {
                                  layer.evidenceItemCount
                                }{' '}
                                evidence items
                              </span>
                            </div>
                          </div>
                        ),
                      )}
                  </div>

                  <div className="fleetOpsEvidenceSummary">
                    <Metric
                      label="Observable model evidence"
                      value={number(
                        explainabilityDetail
                          .evidenceInventory
                          .observableModelEvidenceCount,
                      )}
                      detail="Observable evidence only"
                    />
                    <Metric
                      label="Coverage gaps"
                      value={number(
                        explainabilityDetail
                          .evidenceInventory
                          .coverageGapCount,
                      )}
                      detail="Missing operational evidence"
                    />
                    <Metric
                      label="Automation actions"
                      value={number(
                        explainabilityDetail
                          .evidenceInventory
                          .automationActionCount,
                      )}
                      detail="Workflow actions, not repairs"
                    />
                  </div>
                </article>
              ) : (
                <div className="empty">
                  Select a vehicle to inspect evidence inventory.
                </div>
              )}
            </div>
          )}

          {explainabilityView ===
            'LINEAGE' && (
            <div className="fleetOpsSubTabPanel">
              <VehicleContextBar
                vehicleId={explainabilityVehicleId}
                vehicles={explainabilityVehicles}
                onChange={selectExplainabilityVehicle}
              />

              {explainabilityDetail ? (
                <article className="panel fleetOpsPanel">
                  <div className="panelTitle">
                    <span>
                      EVIDENCE LINEAGE
                    </span>
                    <h3>
                      Data/workflow path
                    </h3>
                  </div>

                  <p className="muted">
                    This graph expresses FleetMind workflow lineage, not physical
                    causality.
                  </p>

                  <div className="fleetOpsLineagePath fleetOpsLineagePathExpanded">
                    {explainabilityDetail
                      .lineage
                      .lineagePath.map(
                        (
                          node,
                          index,
                        ) => (
                          <div
                            key={
                              `${node}-${index}`
                            }
                            className="fleetOpsLineageNode"
                          >
                            <span>
                              {humanize(
                                node,
                              )}
                            </span>

                            {index <
                              explainabilityDetail
                                .lineage
                                .lineagePath
                                .length -
                                1 && (
                              <ArrowRight
                                size={14}
                              />
                            )}
                          </div>
                        ),
                      )}
                  </div>
                </article>
              ) : (
                <div className="empty">
                  Select a vehicle to inspect evidence lineage.
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {workspace ===
        'QUEUE' && (
        <div className="fleetOpsWorkspace">
          <OperatorBar
            actor={actor}
            onChange={setActor}
            icon={
              <UserCheck size={16} />
            }
            helper="Required for every queue mutation."
          />

          <SubTabs
            ariaLabel="Decision Queue views"
            active={queueView}
            onChange={value =>
              setQueueView(
                value as QueueView,
              )
            }
            tabs={[
              ['OVERVIEW', 'Overview'],
              ['ACTIVE', 'Active Queue'],
              ['OWNERSHIP', 'Ownership'],
              ['WORKFLOW', 'Workflow Status'],
            ]}
          />

          {queueView ===
            'OVERVIEW' && (
            <div className="fleetOpsSubTabPanel">
              <div className="fleetOpsMetricGrid">
                <Metric
                  label="Active decisions"
                  value={number(
                    queueSummary
                      ?.activeRecommendations,
                  )}
                  detail={`${number(
                    queueSummary
                      ?.terminalRecommendations,
                  )} terminal`}
                />

                <Metric
                  label="Unassigned"
                  value={number(
                    queueSummary
                      ?.unassignedActive,
                  )}
                  detail="Active workflow ownership"
                />

                <Metric
                  label="Review-target overdue"
                  value={number(
                    queueSummary
                      ?.overdueActive,
                  )}
                  detail="Operational timing only"
                />

                <Metric
                  label="Persisted"
                  value={number(
                    queueSummary
                      ?.totalRecommendations,
                  )}
                  detail="Closed-loop recommendations"
                />
              </div>

              <div className="fleetOpsOverviewStrip fleetOpsOverviewStripThree">
                <SummaryPanel
                  eyebrow="PRIORITY"
                  title="Active by priority"
                  rows={(queueSummary?.byPriority ?? []).map(
                    row => ({
                      label: row.priority,
                      value: row.active,
                    }),
                  )}
                />

                <SummaryPanel
                  eyebrow="AGE"
                  title="Active by age bucket"
                  rows={(queueSummary?.byAgeBucket ?? []).map(
                    row => ({
                      label: humanize(row.ageBucket),
                      value: row.active,
                    }),
                  )}
                />

                <SummaryPanel
                  eyebrow="OWNERSHIP"
                  title="Assignment"
                  rows={[
                    {
                      label: 'Assigned',
                      value: queueSummary?.assignment.assigned ?? 0,
                    },
                    {
                      label: 'Unassigned',
                      value: queueSummary?.assignment.unassigned ?? 0,
                    },
                  ]}
                />
              </div>
            </div>
          )}

          {queueView ===
            'ACTIVE' && (
            <div className="fleetOpsSubTabPanel">
              <DecisionQueueTable
                queue={queue}
                actor={actor}
                actionId={actionId}
                onAssign={assign}
                onTransition={transition}
                onSelectVehicle={vehicleId => {
                  selectExplainabilityVehicle(
                    vehicleId,
                  );
                  setExplainabilityView(
                    'ATTENTION',
                  );
                }}
              />
            </div>
          )}

          {queueView ===
            'OWNERSHIP' && (
            <div className="fleetOpsSubTabPanel">
              <div className="fleetOpsOwnershipGrid">
                <OwnershipPanel
                  title="Unassigned"
                  subtitle="Needs an explicit operator owner"
                  rows={unassignedQueue}
                  actor={actor}
                  actionId={actionId}
                  onAssign={assign}
                />

                <OwnershipPanel
                  title="Assigned"
                  subtitle="Current workflow ownership"
                  rows={assignedQueue}
                  actor={actor}
                  actionId={actionId}
                  onAssign={assign}
                />
              </div>
            </div>
          )}

          {queueView ===
            'WORKFLOW' && (
            <div className="fleetOpsSubTabPanel">
              <article className="panel fleetOpsPanel">
                <div className="panelTitle">
                  <span>
                    WORKFLOW STATUS
                  </span>
                  <h3>
                    Recommendation lifecycle distribution
                  </h3>
                </div>

                <div className="fleetOpsWorkflowGrid">
                  {(queueSummary?.byStatus ?? []).map(
                    row => (
                      <button
                        type="button"
                        key={row.status}
                        onClick={() =>
                          setQueueView(
                            'ACTIVE',
                          )
                        }
                      >
                        <span>
                          {humanize(
                            row.status,
                          )}
                        </span>
                        <strong>
                          {number(
                            row.count,
                          )}
                        </strong>
                        <small>
                          View active queue
                        </small>
                      </button>
                    ),
                  )}
                </div>
              </article>

              <div className="fleetOpsGuardrail">
                <ShieldCheck
                  size={17}
                />
                <div>
                  <b>
                    Queue status is workflow state, not physical condition.
                  </b>
                  <span>
                    Priority and review-target age organize human work; neither is a physical-risk claim or a safety deadline.
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {workspace ===
        'CLOSED_LOOP' && (
        <div className="fleetOpsWorkspace">
          <OperatorBar
            actor={actor}
            onChange={setActor}
            icon={
              <ClipboardCheck size={16} />
            }
            helper="Evaluation may preview without writing. Materialization requires an explicit action."
          />

          <SubTabs
            ariaLabel="Closed Loop views"
            active={closedLoopView}
            onChange={value =>
              setClosedLoopView(
                value as ClosedLoopView,
              )
            }
            tabs={[
              ['EVALUATE', 'Evaluate'],
              ['RESULTS', 'Evaluation Results'],
              ['RECOMMENDATIONS', 'Recommendations'],
              ['OUTCOMES', 'Outcomes'],
              ['LIFECYCLE', 'Lifecycle'],
            ]}
          />

          {closedLoopView ===
            'EVALUATE' && (
            <div className="fleetOpsSubTabPanel">
              <div className="fleetOpsClosedLoopHero">
                <div>
                  <Sparkles
                    size={22}
                  />
                  <div>
                    <span>
                      CLOSED-LOOP FOUNDATION
                    </span>
                    <h3>
                      Evaluate operational recommendations
                    </h3>
                    <p>
                      Evaluation derives deterministic workflow candidates. It
                      never approves or executes them automatically.
                    </p>
                    <div className="fleetOpsSelectedTarget">
                      <span>
                        Materialization target
                      </span>
                      <strong>
                        {selectedVehicleId ??
                          'Select a vehicle first'}
                      </strong>
                    </div>
                  </div>
                </div>

                <div className="fleetOpsClosedLoopActions">
                  <button
                    type="button"
                    onClick={() =>
                      void evaluate(
                        false,
                      )
                    }
                    disabled={loading}
                  >
                    <Eye
                      size={14}
                    />
                    Preview evaluation
                  </button>

                  <button
                    type="button"
                    className="primary"
                    onClick={() =>
                      void evaluate(
                        true,
                      )
                    }
                    disabled={
                      loading ||
                      !selectedVehicleId
                    }
                    title={
                      selectedVehicleId
                        ? `Materialize recommendations for ${selectedVehicleId}`
                        : 'Select a vehicle before materializing recommendations'
                    }
                  >
                    <ClipboardCheck
                      size={14}
                    />
                    Materialize recommendations
                  </button>
                </div>
              </div>
            </div>
          )}

          {closedLoopView ===
            'RESULTS' && (
            <div className="fleetOpsSubTabPanel">
              {evaluation ? (
                <>
                  <article className="panel fleetOpsPanel">
                    <div className="panelTitleRow">
                      <div className="panelTitle">
                        <span>
                          LATEST EVALUATION
                        </span>
                        <h3>
                          {evaluation.materializeRequested
                            ? 'Materialized'
                            : 'Preview only'}
                        </h3>
                      </div>

                      <span className="methodBadge">
                        {evaluation.candidateCount}{' '}
                        CANDIDATES
                      </span>
                    </div>

                    <div className="fleetOpsMetricGrid compact">
                      <Metric
                        label="Vehicles evaluated"
                        value={number(
                          evaluation.evaluatedVehicles,
                        )}
                        detail="Selected-run fleet"
                      />

                      <Metric
                        label="Candidates"
                        value={number(
                          evaluation.candidateCount,
                        )}
                        detail="Deterministic recommendations"
                      />

                      <Metric
                        label="Created"
                        value={number(
                          evaluation.createdCount,
                        )}
                        detail="Persisted this evaluation"
                      />

                      <Metric
                        label="Existing"
                        value={number(
                          evaluation.existingCount,
                        )}
                        detail="Idempotent matches"
                      />
                    </div>
                  </article>

                  <div className="fleetOpsOverviewStrip">
                    <SummaryPanel
                      eyebrow="TYPE"
                      title="Candidates by type"
                      rows={evaluation.byType.map(
                        row => ({
                          label: humanize(
                            row.recommendationType,
                          ),
                          value: row.count,
                        }),
                      )}
                    />

                    <SummaryPanel
                      eyebrow="PRIORITY"
                      title="Candidates by priority"
                      rows={evaluation.byPriority.map(
                        row => ({
                          label: row.priority,
                          value: row.count,
                        }),
                      )}
                    />
                  </div>

                  {(evaluation.candidates ?? []).length > 0 && (
                    <article className="panel fleetOpsPanel">
                      <div className="panelTitle">
                        <span>
                          CANDIDATE DETAIL
                        </span>
                        <h3>
                          Deterministic recommendation preview
                        </h3>
                      </div>

                      <div className="fleetOpsCandidateList">
                        {(evaluation.candidates ?? [])
                          .slice(0, 50)
                          .map(candidate => (
                            <div
                              key={candidate.recommendationKey}
                              className="fleetOpsCandidateRow"
                            >
                              <b>{candidate.vehicleId}</b>
                              <span>{humanize(candidate.recommendationType)}</span>
                              <span className={`fleetOpsPriority priority-${candidate.priority.toLowerCase()}`}>
                                {candidate.priority}
                              </span>
                              <p>{candidate.reason}</p>
                            </div>
                          ))}
                      </div>
                    </article>
                  )}
                </>
              ) : (
                <div className="empty fleetOpsEmptyState">
                  No evaluation has run in this session. Open Evaluate and run a preview first.
                </div>
              )}
            </div>
          )}

          {closedLoopView ===
            'RECOMMENDATIONS' && (
            <div className="fleetOpsSubTabPanel">
              <article className="panel fleetOpsPanel">
                <div className="panelTitleRow">
                  <div className="panelTitle">
                    <span>
                      PERSISTED RECOMMENDATIONS
                    </span>
                    <h3>
                      Closed-loop lifecycle
                    </h3>
                  </div>

                  <span className="methodBadge">
                    {activeRecommendations.length}{' '}
                    ACTIVE
                  </span>
                </div>

                {recommendations.length === 0 ? (
                  <div className="empty">
                    No closed-loop recommendations have been materialized.
                  </div>
                ) : (
                  <div className="fleetOpsRecommendationList">
                    {recommendations
                      .slice(0, 100)
                      .map(
                        row => (
                          <div
                            key={
                              row.id
                            }
                            className="fleetOpsRecommendation"
                          >
                            <div className="fleetOpsRecommendationIcon">
                              <Workflow
                                size={16}
                              />
                            </div>

                            <div className="fleetOpsRecommendationIdentity">
                              <b>
                                {
                                  row.vehicleId
                                }
                              </b>
                              <span>
                                {humanize(
                                  row.recommendationType,
                                )}
                              </span>
                            </div>

                            <div>
                              <span>
                                Priority
                              </span>
                              <b>
                                {
                                  row.priority
                                }
                              </b>
                            </div>

                            <div>
                              <span>
                                Status
                              </span>
                              <b>
                                {humanize(
                                  row.status,
                                )}
                              </b>
                            </div>

                            <div>
                              <span>
                                Owner
                              </span>
                              <b>
                                {row.assignedTo ??
                                  'Unassigned'}
                              </b>
                            </div>

                            <div className="fleetOpsRecommendationReason">
                              <span>
                                Reason
                              </span>
                              <p>
                                {row.reason}
                              </p>
                            </div>
                          </div>
                        ),
                      )}
                  </div>
                )}
              </article>
            </div>
          )}

          {closedLoopView ===
            'OUTCOMES' && (
            <div className="fleetOpsSubTabPanel">
              <ClosedLoopOutcomesPanel
                runId={runId}
                selectedVehicleId={selectedVehicleId}
              />
            </div>
          )}

          {closedLoopView ===
            'LIFECYCLE' && (
            <div className="fleetOpsSubTabPanel">
              <article className="panel fleetOpsPanel">
                <div className="panelTitle">
                  <span>
                    HUMAN-GATED LIFECYCLE
                  </span>
                  <h3>
                    Explicit operational progression
                  </h3>
                </div>

                <div className="fleetOpsLifecycle">
                  {[
                    'PROPOSED',
                    'ACKNOWLEDGED',
                    'APPROVAL REQUIRED',
                    'APPROVED',
                    'EXECUTION READY',
                    'EXECUTED',
                  ].map((state, index, states) => (
                    <div
                      className="fleetOpsLifecycleStep"
                      key={state}
                    >
                      <div>
                        <span>{index + 1}</span>
                        <b>{state}</b>
                      </div>

                      {index < states.length - 1 && (
                        <ArrowRight size={16} />
                      )}
                    </div>
                  ))}
                </div>
              </article>

              <div className="fleetOpsGuardrail">
                <ShieldCheck
                  size={17}
                />
                <div>
                  <b>
                    Human control remains mandatory.
                  </b>
                  <span>
                    PROPOSED → ACKNOWLEDGED → APPROVAL REQUIRED → APPROVED → EXECUTION READY → EXECUTED. No lifecycle state performs a physical maintenance or vehicle command.
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}


function WorkspaceButton({
  active,
  icon,
  children,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={
        active
          ? 'fleetOpsTab active'
          : 'fleetOpsTab'
      }
      onClick={onClick}
    >
      {icon}
      <span>{children}</span>
    </button>
  );
}


function SubTabs({
  ariaLabel,
  active,
  tabs,
  onChange,
}: {
  ariaLabel: string;
  active: string;
  tabs: Array<
    readonly [string, string]
  >;
  onChange: (
    value: string,
  ) => void;
}) {
  return (
    <div
      className="fleetOpsSubTabs"
      role="tablist"
      aria-label={ariaLabel}
    >
      {tabs.map(
        ([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={
              active === value
            }
            className={
              active === value
                ? 'fleetOpsSubTab active'
                : 'fleetOpsSubTab'
            }
            onClick={() =>
              onChange(value)
            }
          >
            {label}
          </button>
        ),
      )}
    </div>
  );
}


function OperatorBar({
  actor,
  onChange,
  icon,
  helper,
}: {
  actor: string;
  onChange: (
    value: string,
  ) => void;
  icon: ReactNode;
  helper: string;
}) {
  return (
    <div className="fleetOpsOperatorBar">
      {icon}

      <span>
        Operator
      </span>

      <input
        value={actor}
        onChange={event =>
          onChange(
            event.target.value,
          )
        }
        placeholder="operator"
        maxLength={64}
      />

      <small>
        {helper}
      </small>
    </div>
  );
}


function VehicleContextBar({
  vehicleId,
  vehicles,
  onChange,
}: {
  vehicleId: string | null;
  vehicles: ExplainabilityVehicleRow[];
  onChange: (
    vehicleId: string,
  ) => void;
}) {
  return (
    <div className="fleetOpsVehicleContext">
      <div>
        <span>
          Investigation vehicle
        </span>
        <strong>
          {vehicleId ??
            'Select vehicle'}
        </strong>
      </div>

      <select
        className="fleetOpsSelect"
        value={
          vehicleId ?? ''
        }
        onChange={event => {
          if (event.target.value) {
            onChange(
              event.target.value,
            );
          }
        }}
      >
        <option value="">
          Select vehicle
        </option>
        {vehicles.map(
          vehicle => (
            <option
              key={vehicle.vehicleId}
              value={vehicle.vehicleId}
            >
              {vehicle.vehicleId} · {humanize(vehicle.topClass)}
            </option>
          ),
        )}
      </select>
    </div>
  );
}


function SummaryPanel({
  eyebrow,
  title,
  rows,
}: {
  eyebrow: string;
  title: string;
  rows: Array<{
    label: string;
    value: number;
  }>;
}) {
  return (
    <article className="panel fleetOpsPanel">
      <div className="panelTitle">
        <span>
          {eyebrow}
        </span>
        <h3>
          {title}
        </h3>
      </div>

      <div className="fleetOpsSummaryList">
        {rows.length === 0 ? (
          <div className="empty">
            No data
          </div>
        ) : (
          rows.map(
            row => (
              <div key={row.label}>
                <span>
                  {row.label}
                </span>
                <strong>
                  {number(row.value)}
                </strong>
              </div>
            ),
          )
        )}
      </div>
    </article>
  );
}


function DecisionQueueTable({
  queue,
  actor,
  actionId,
  onAssign,
  onTransition,
  onSelectVehicle,
}: {
  queue: QueueRecord[];
  actor: string;
  actionId: number | null;
  onAssign: (
    recommendationId: number,
    assignedTo: string | null,
  ) => Promise<void>;
  onTransition: (
    recommendationId: number,
    path: string,
  ) => Promise<void>;
  onSelectVehicle: (
    vehicleId: string,
  ) => void;
}) {
  return (
    <article className="panel fleetOpsPanel">
      <div className="panelTitleRow">
        <div className="panelTitle">
          <span>
            HUMAN DECISION QUEUE
          </span>
          <h3>
            Approval orchestration
          </h3>
        </div>

        <span className="methodBadge">
          {queue.length}{' '}
          ACTIVE
        </span>
      </div>

      {queue.length === 0 ? (
        <div className="empty">
          No active recommendations are materialized yet. Use Closed Loop
          → Evaluate, then explicitly materialize candidates.
        </div>
      ) : (
        <div className="fleetOpsDecisionTable">
          <div className="fleetOpsDecisionHead">
            <span>#</span>
            <span>Vehicle</span>
            <span>Decision</span>
            <span>Priority</span>
            <span>Age</span>
            <span>Owner</span>
            <span>Status</span>
            <span>Action</span>
          </div>

          {queue.map(
            row => {
              const action =
                nextAction(
                  row.status,
                );

              return (
                <div
                  className="fleetOpsDecisionRow"
                  key={
                    row.id
                  }
                >
                  <span>
                    {row.queueRank}
                  </span>

                  <button
                    type="button"
                    className="fleetOpsVehicleLink"
                    onClick={() =>
                      onSelectVehicle(
                        row.vehicleId,
                      )
                    }
                  >
                    {
                      row.vehicleId
                    }
                  </button>

                  <span>
                    {humanize(
                      row.recommendationType,
                    )}
                  </span>

                  <span className={`fleetOpsPriority priority-${row.priority.toLowerCase()}`}>
                    {
                      row.priority
                    }
                  </span>

                  <span>
                    <Clock3
                      size={12}
                    />
                    {number(
                      row.ageHours,
                      1,
                    )}{' '}
                    h
                    {row.reviewTargetOverdue && (
                      <b>
                        {' '}
                        · overdue
                      </b>
                    )}
                  </span>

                  <span>
                    {row.assignedTo ??
                      'Unassigned'}
                  </span>

                  <span>
                    {humanize(
                      row.status,
                    )}
                  </span>

                  <div className="fleetOpsRowActions">
                    <button
                      type="button"
                      disabled={
                        actionId ===
                        row.id
                      }
                      onClick={() =>
                        void onAssign(
                          row.id,
                          row.assignedTo
                            ? null
                            : actor.trim() ||
                                'operator',
                        )
                      }
                    >
                      {row.assignedTo
                        ? 'Unassign'
                        : 'Assign me'}
                    </button>

                    {action && (
                      <button
                        type="button"
                        className="primary"
                        disabled={
                          actionId ===
                          row.id
                        }
                        onClick={() =>
                          void onTransition(
                            row.id,
                            action.path,
                          )
                        }
                      >
                        {
                          action.label
                        }
                      </button>
                    )}
                  </div>
                </div>
              );
            },
          )}
        </div>
      )}
    </article>
  );
}


function OwnershipPanel({
  title,
  subtitle,
  rows,
  actor,
  actionId,
  onAssign,
}: {
  title: string;
  subtitle: string;
  rows: QueueRecord[];
  actor: string;
  actionId: number | null;
  onAssign: (
    recommendationId: number,
    assignedTo: string | null,
  ) => Promise<void>;
}) {
  return (
    <article className="panel fleetOpsPanel">
      <div className="panelTitleRow">
        <div className="panelTitle">
          <span>
            OWNERSHIP
          </span>
          <h3>
            {title}
          </h3>
        </div>

        <span className="methodBadge">
          {rows.length}
        </span>
      </div>

      <p className="muted">
        {subtitle}
      </p>

      <div className="fleetOpsOwnershipList">
        {rows.length === 0 ? (
          <div className="empty">
            No recommendations in this group.
          </div>
        ) : (
          rows.map(
            row => (
              <div
                key={row.id}
                className="fleetOpsOwnershipRow"
              >
                <div>
                  <b>{row.vehicleId}</b>
                  <span>
                    {humanize(
                      row.recommendationType,
                    )}
                  </span>
                </div>

                <span className={`fleetOpsPriority priority-${row.priority.toLowerCase()}`}>
                  {row.priority}
                </span>

                <div>
                  <span>
                    {row.assignedTo ??
                      'Unassigned'}
                  </span>
                  <small>
                    {humanize(
                      row.status,
                    )}
                  </small>
                </div>

                <button
                  type="button"
                  disabled={
                    actionId ===
                    row.id
                  }
                  onClick={() =>
                    void onAssign(
                      row.id,
                      row.assignedTo
                        ? null
                        : actor.trim() ||
                            'operator',
                    )
                  }
                >
                  {row.assignedTo
                    ? 'Unassign'
                    : 'Assign me'}
                </button>
              </div>
            ),
          )
        )}
      </div>
    </article>
  );
}


function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="fleetOpsMetric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}
