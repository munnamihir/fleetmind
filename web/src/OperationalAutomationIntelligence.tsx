import { useEffect, useMemo, useState } from 'react';
import {
  Bot,
  CheckCircle2,
  ClipboardCheck,
  FlaskConical,
  History,
  Play,
  RefreshCw,
  Settings2,
  ShieldCheck,
  XCircle,
} from 'lucide-react';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

type AutomationSummary = {
  runId: number;
  experimentId: string;
  rulesVersion: string;
  totalPolicies: number;
  enabledPolicies: number;
  totalActions: number;
  pendingApproval: number;
  approvedReady: number;
  rejected: number;
  executed: number;
  byStatus: Array<{ status: string; actions: number }>;
  interpretationPolicy: string;
};

type AutomationPolicy = {
  id: number;
  policyKey: string;
  name: string;
  description: string;
  enabled: boolean;
  priority: number;
  severity: string;
  conditions: Array<{
    field: string;
    operator: string;
    value: unknown;
  }>;
  actionType: string;
  actionPayload: Record<string, unknown>;
  requiresApproval: boolean;
};

type PolicyResponse = {
  totalPolicies: number;
  enabledPolicies: number;
  policies: AutomationPolicy[];
};

type Simulation = {
  simulationOnly: boolean;
  wouldQueue: number;
  byPolicy: Array<{
    policyKey: string;
    enabled: boolean;
    matches: number;
    actionType: string;
    severity: string;
  }>;
  byActionType: Array<{ actionType: string; matches: number }>;
  sampleMatches: Array<{
    policyKey: string;
    policyName: string;
    severity: string;
    actionType: string;
    requiresApproval: boolean;
    caseId: number;
    vehicleId: string;
    hypothesisClass: string;
    maintenanceTier: string;
    priorityScore: number;
    reason: string;
  }>;
  interpretationPolicy: string;
};

type AutomationAction = {
  id: number;
  policyKey: string;
  caseId: number;
  vehicleId: string;
  status: string;
  severity: string;
  actionType: string;
  reason: string;
  sourceSnapshot: {
    hypothesisClass?: string;
    caseStatus?: string;
    reviewPriority?: string;
    episodeState?: string;
    watchlisted?: boolean;
    trajectoryEligible?: boolean;
    trajectoryPointCount?: number;
    latestConfidence?: number | null;
    slopePer1kMiles?: number | null;
    priorityScore?: number | null;
    maintenanceTier?: string;
    recommendedReviewWindow?: string;
    maintenancePlanPresent?: boolean;
    thresholdAlreadyReached?: boolean;
    estimatedMilesToThreshold?: number | null;
  };
  approvedAt: string | null;
  approvedBy: string | null;
  rejectedAt: string | null;
  rejectedBy: string | null;
  executedAt: string | null;
  executedBy: string | null;
  executionResult: Record<string, unknown>;
};

type ActionResponse = {
  totalMatched: number;
  actions: AutomationAction[];
};

type ActionDetail = {
  action: AutomationAction;
  policy: AutomationPolicy | null;
  activities: Array<{
    id: number;
    activityType: string;
    actor: string;
    note: string | null;
    createdAt: string;
    details: Record<string, unknown>;
  }>;
};

type Props = {
  selectedVehicleId: string | null;
  onSelectVehicle: (vehicleId: string) => void;
  runId?: number;
};

function humanize(value: string | null | undefined) {
  if (!value) return '—';
  return value.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function pct(value: number | null | undefined) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`;
}

function miles(value: number | null | undefined) {
  return value == null ? '—' : `${Math.round(value).toLocaleString()} mi`;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status}: ${body || url}`);
  }
  return response.json() as Promise<T>;
}

export function OperationalAutomationIntelligence({
  selectedVehicleId,
  onSelectVehicle,
  runId,
}: Props) {
  const [summary, setSummary] = useState<AutomationSummary | null>(null);
  const [policies, setPolicies] = useState<PolicyResponse | null>(null);
  const [simulation, setSimulation] = useState<Simulation | null>(null);
  const [actions, setActions] = useState<ActionResponse | null>(null);
  const [selectedActionId, setSelectedActionId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ActionDetail | null>(null);
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function bootstrapPolicies() {
    await requestJson(
      `${API}/api/v1/diagnostics/automation/policies/bootstrap`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actor: 'dashboard_operator' }),
      },
    );
  }

  async function refresh() {
    const statusQuery = statusFilter === 'ALL'
      ? ''
      : `&status=${encodeURIComponent(statusFilter)}`;
    const [nextSummary, nextPolicies, nextSimulation, nextActions] =
      await Promise.all([
        requestJson<AutomationSummary>(
          `${API}/api/v1/diagnostics/automation/summary`,
        ),
        requestJson<PolicyResponse>(
          `${API}/api/v1/diagnostics/automation/policies`,
        ),
        requestJson<Simulation>(
          `${API}/api/v1/diagnostics/automation/simulate?limit=30`,
        ),
        requestJson<ActionResponse>(
          `${API}/api/v1/diagnostics/automation/actions?limit=100${statusQuery}`,
        ),
      ]);
    setSummary(nextSummary);
    setPolicies(nextPolicies);
    setSimulation(nextSimulation);
    setActions(nextActions);
    setSelectedActionId(current => {
      if (current && nextActions.actions.some(item => item.id === current)) {
        return current;
      }
      const selectedVehicleAction = nextActions.actions.find(
        item => item.vehicleId === selectedVehicleId,
      );
      return selectedVehicleAction?.id ?? nextActions.actions[0]?.id ?? null;
    });
  }

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const cycle = async () => {
      try {
        await bootstrapPolicies();
        await refresh();
        if (alive) setError(null);
      } catch (refreshError) {
        if (alive) {
          setError(
            refreshError instanceof Error
              ? refreshError.message
              : 'Operational automation API unavailable',
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
  }, [runId, statusFilter]);

  useEffect(() => {
    if (!selectedActionId) {
      setDetail(null);
      return;
    }
    let alive = true;
    requestJson<ActionDetail>(
      `${API}/api/v1/diagnostics/automation/actions/${selectedActionId}`,
    )
      .then(next => {
        if (alive) setDetail(next);
      })
      .catch(detailError => {
        if (alive) {
          setError(
            detailError instanceof Error
              ? detailError.message
              : 'Automation action detail unavailable',
          );
        }
      });
    return () => {
      alive = false;
    };
  }, [selectedActionId, runId]);

  useEffect(() => {
    if (!selectedVehicleId || !actions?.actions.length) return;
    const match = actions.actions.find(
      item => item.vehicleId === selectedVehicleId,
    );
    if (match) setSelectedActionId(match.id);
  }, [selectedVehicleId, actions]);

  const statusCounts = useMemo(
    () => new Map((summary?.byStatus ?? []).map(item => [item.status, item.actions])),
    [summary],
  );

  async function togglePolicy(policy: AutomationPolicy) {
    setBusy(true);
    try {
      await requestJson(
        `${API}/api/v1/diagnostics/automation/policies/${encodeURIComponent(policy.policyKey)}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            enabled: !policy.enabled,
            actor: 'dashboard_operator',
          }),
        },
      );
      await refresh();
      setError(null);
    } catch (toggleError) {
      setError(toggleError instanceof Error ? toggleError.message : 'Policy update failed');
    } finally {
      setBusy(false);
    }
  }

  async function evaluatePolicies() {
    setBusy(true);
    try {
      await requestJson(
        `${API}/api/v1/diagnostics/automation/evaluate`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            actor: 'dashboard_operator',
            note: 'Materialized from the Phase 6.13 operational automation cockpit.',
          }),
        },
      );
      await refresh();
      setError(null);
    } catch (evaluateError) {
      setError(
        evaluateError instanceof Error
          ? evaluateError.message
          : 'Policy evaluation failed',
      );
    } finally {
      setBusy(false);
    }
  }

  async function transitionAction(operation: 'approve' | 'reject' | 'execute') {
    if (!selectedActionId) return;
    setBusy(true);
    try {
      await requestJson(
        `${API}/api/v1/diagnostics/automation/actions/${selectedActionId}/${operation}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            actor: 'dashboard_operator',
            note: `Action ${operation} requested from the operational automation cockpit.`,
          }),
        },
      );
      await refresh();
      const nextDetail = await requestJson<ActionDetail>(
        `${API}/api/v1/diagnostics/automation/actions/${selectedActionId}`,
      );
      setDetail(nextDetail);
      setError(null);
    } catch (transitionError) {
      setError(
        transitionError instanceof Error
          ? transitionError.message
          : `Action ${operation} failed`,
      );
    } finally {
      setBusy(false);
    }
  }

  const selected = detail?.action ?? null;

  return (
    <section className="panel automationPanel">
      <div className="panelTitleRow">
        <div className="panelTitle">
          <span>OPERATIONAL AUTOMATION</span>
          <h2>Policy simulation, approval queue & guarded workflow execution</h2>
        </div>
        <span className="methodBadge automationGuardBadge">
          HUMAN APPROVAL REQUIRED · WORKFLOW METADATA ONLY
        </span>
      </div>

      <p className="muted automationPolicyText">
        Phase 6.13 evaluates deterministic, source-versioned policies against
        run-frozen prognostic workflow inputs. Evaluation only queues actions.
        Nothing executes without an explicit human approval followed by a
        separate execute request. No private failure truth or physical-failure
        inference is used.
      </p>

      {error && <div className="diagnosticError">{error}</div>}

      <div className="automationMetrics">
        <Metric
          label="Enabled policies"
          value={summary?.enabledPolicies ?? 0}
          detail={`${summary?.totalPolicies ?? 0} pinned policies`}
        />
        <Metric
          label="Pending approval"
          value={summary?.pendingApproval ?? 0}
          detail="no execution yet"
        />
        <Metric
          label="Approved / ready"
          value={summary?.approvedReady ?? 0}
          detail="requires separate execute"
        />
        <Metric
          label="Executed"
          value={summary?.executed ?? 0}
          detail="workflow metadata actions"
        />
      </div>

      <div className="automationStatusStrip">
        {['PENDING_APPROVAL', 'APPROVED', 'EXECUTED', 'REJECTED'].map(status => (
          <div key={status}>
            <span>{humanize(status)}</span>
            <strong>{statusCounts.get(status) ?? 0}</strong>
          </div>
        ))}
      </div>

      <div className="automationGrid">
        <article className="automationCard">
          <div className="automationCardTitle">
            <Settings2 size={16} />
            <div>
              <span>PINNED POLICIES</span>
              <b>Enablement only; conditions remain source-declared</b>
            </div>
          </div>

          <div className="automationPolicyList">
            {(policies?.policies ?? []).map(policy => (
              <div className="automationPolicyRow" key={policy.policyKey}>
                <div>
                  <div className="automationPolicyName">
                    <b>{policy.name}</b>
                    <span className={`automationSeverity severity-${policy.severity.toLowerCase()}`}>
                      {policy.severity}
                    </span>
                  </div>
                  <span>{humanize(policy.actionType)}</span>
                  <small>{policy.description}</small>
                  <code>{policy.policyKey}</code>
                </div>
                <button
                  className={policy.enabled ? 'automationToggle enabled' : 'automationToggle'}
                  disabled={busy}
                  onClick={() => void togglePolicy(policy)}
                >
                  {policy.enabled ? 'Enabled' : 'Disabled'}
                </button>
              </div>
            ))}
          </div>
        </article>

        <article className="automationCard">
          <div className="automationCardTitle">
            <FlaskConical size={16} />
            <div>
              <span>DRY-RUN SIMULATOR</span>
              <b>Current policy matches without writes or execution</b>
            </div>
          </div>

          <div className="automationSimulationHero">
            <div>
              <span>Would queue</span>
              <strong>{simulation?.wouldQueue ?? 0}</strong>
              <small>approval-pending actions</small>
            </div>
            <button disabled={busy} onClick={() => void refresh()}>
              <RefreshCw size={14} /> Refresh dry run
            </button>
            <button className="primary" disabled={busy} onClick={() => void evaluatePolicies()}>
              <ClipboardCheck size={14} /> Evaluate & queue
            </button>
          </div>

          <div className="automationPolicyMatchGrid">
            {(simulation?.byPolicy ?? []).map(item => (
              <div key={item.policyKey}>
                <span>{item.policyKey}</span>
                <strong>{item.matches}</strong>
                <small>{humanize(item.actionType)}</small>
              </div>
            ))}
          </div>

          <p className="muted automationDryRunNote">
            Dry run is read-only. “Evaluate & queue” persists action records in
            PENDING APPROVAL status and still performs no operational action.
          </p>
        </article>
      </div>

      <div className="automationGrid lower">
        <article className="automationCard automationQueueCard">
          <div className="automationCardTitle queueTitle">
            <Bot size={16} />
            <div>
              <span>APPROVAL QUEUE</span>
              <b>Human-controlled operational actions</b>
            </div>
            <select
              value={statusFilter}
              onChange={event => setStatusFilter(event.target.value)}
            >
              <option value="ALL">All statuses</option>
              <option value="PENDING_APPROVAL">Pending approval</option>
              <option value="APPROVED">Approved</option>
              <option value="EXECUTED">Executed</option>
              <option value="REJECTED">Rejected</option>
            </select>
          </div>

          <div className="automationActionList">
            {(actions?.actions ?? []).map(action => (
              <button
                key={action.id}
                className={selectedActionId === action.id ? 'selected' : ''}
                onClick={() => {
                  setSelectedActionId(action.id);
                  onSelectVehicle(action.vehicleId);
                }}
              >
                <span className={`automationStatusDot status-${action.status.toLowerCase()}`} />
                <div>
                  <b>#{action.id} · {action.vehicleId}</b>
                  <span>{humanize(action.actionType)}</span>
                  <small>{action.policyKey}</small>
                </div>
                <div>
                  <strong>{humanize(action.status)}</strong>
                  <span>{action.severity}</span>
                </div>
              </button>
            ))}
            {(actions?.actions ?? []).length === 0 && (
              <div className="automationEmpty">
                No actions match this filter. Run the dry-run simulator, then
                explicitly evaluate policies to populate the queue.
              </div>
            )}
          </div>
        </article>

        <article className="automationCard automationDetailCard">
          <div className="automationCardTitle">
            <ShieldCheck size={16} />
            <div>
              <span>GUARDED EXECUTION</span>
              <b>{selected ? `Action #${selected.id} · ${selected.vehicleId}` : 'Select an action'}</b>
            </div>
          </div>

          {!selected ? (
            <div className="automationEmpty">Select an action from the approval queue.</div>
          ) : (
            <>
              <div className="automationActionHero">
                <div>
                  <span>Status</span>
                  <strong>{humanize(selected.status)}</strong>
                </div>
                <div>
                  <span>Action</span>
                  <strong>{humanize(selected.actionType)}</strong>
                </div>
                <div>
                  <span>Case</span>
                  <strong>#{selected.caseId}</strong>
                </div>
              </div>

              <p className="automationReason">{selected.reason}</p>

              <div className="automationSnapshotGrid">
                <Stat label="Hypothesis" value={humanize(selected.sourceSnapshot.hypothesisClass)} />
                <Stat label="Maintenance tier" value={humanize(selected.sourceSnapshot.maintenanceTier)} />
                <Stat label="Priority score" value={selected.sourceSnapshot.priorityScore?.toFixed(1) ?? '—'} />
                <Stat label="Latest confidence" value={pct(selected.sourceSnapshot.latestConfidence)} />
                <Stat label="Episode state" value={humanize(selected.sourceSnapshot.episodeState)} />
                <Stat label="Review window" value={humanize(selected.sourceSnapshot.recommendedReviewWindow)} />
                <Stat label="Threshold horizon" value={miles(selected.sourceSnapshot.estimatedMilesToThreshold)} />
                <Stat label="Plan existed" value={selected.sourceSnapshot.maintenancePlanPresent ? 'Yes' : 'No'} />
              </div>

              <div className="automationActionButtons">
                <button
                  disabled={busy || selected.status !== 'PENDING_APPROVAL'}
                  onClick={() => void transitionAction('approve')}
                >
                  <CheckCircle2 size={14} /> Approve
                </button>
                <button
                  disabled={busy || !['PENDING_APPROVAL', 'APPROVED'].includes(selected.status)}
                  onClick={() => void transitionAction('reject')}
                >
                  <XCircle size={14} /> Reject
                </button>
                <button
                  className="primary"
                  disabled={busy || selected.status !== 'APPROVED'}
                  onClick={() => void transitionAction('execute')}
                >
                  <Play size={14} /> Execute approved action
                </button>
              </div>

              <div className="automationExecutionGuard">
                <ShieldCheck size={15} />
                <span>
                  Execution can only create non-destructive workflow metadata:
                  a REVIEW maintenance plan when absent, or a watchlist entry
                  when absent. Existing plans are never overwritten.
                </span>
              </div>

              {Object.keys(selected.executionResult ?? {}).length > 0 && (
                <div className="automationExecutionResult">
                  <span>Execution result</span>
                  <code>{JSON.stringify(selected.executionResult)}</code>
                </div>
              )}
            </>
          )}
        </article>
      </div>

      <article className="automationCard automationAuditCard">
        <div className="automationCardTitle">
          <History size={16} />
          <div>
            <span>ACTION AUDIT TRAIL</span>
            <b>Immutable workflow lifecycle for the selected action</b>
          </div>
        </div>
        <div className="automationAuditList">
          {(detail?.activities ?? []).map(activity => (
            <div key={activity.id}>
              <span>{humanize(activity.activityType)}</span>
              <b>{activity.actor}</b>
              <small>{new Date(activity.createdAt).toLocaleString()}</small>
              {activity.note && <p>{activity.note}</p>}
            </div>
          ))}
          {(detail?.activities ?? []).length === 0 && (
            <div className="automationEmpty">No action audit entries yet.</div>
          )}
        </div>
      </article>

      <div className="automationSafetyFooter">
        <ShieldCheck size={16} />
        <span>
          Deterministic workflow automation only · run-frozen prognostic inputs
          · no private failure truth · no automatic execution · no benchmark or
          model mutation · no physical-failure or causal claim.
        </span>
      </div>
    </section>
  );
}

function Metric({ label, value, detail }: { label: string; value: number; detail: string }) {
  return (
    <div className="automationMetric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="automationStat">
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}
