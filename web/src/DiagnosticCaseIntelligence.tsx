import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  MessageSquarePlus,
  Search,
  ShieldCheck,
  UserRound,
} from 'lucide-react';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

type CaseStatus =
  | 'OPEN'
  | 'ACKNOWLEDGED'
  | 'INVESTIGATING'
  | 'MONITORING'
  | 'CLOSED';

type CasePriority = 'HIGH' | 'MEDIUM' | 'LOW';

type DiagnosticCase = {
  id: number;
  runId: number;
  experimentId: string;
  episodeId: number;
  rulesVersion: string;
  sourceEpisodeRulesVersion: string;
  sourceEventRulesVersion: string;
  vehicleId: string;
  hypothesisClass: string;
  episodeStateAtCreation: string;
  status: CaseStatus;
  reviewPriority: CasePriority;
  assignedTo: string | null;
  title: string;
  startTimestamp: string;
  startMileage: number;
  latestTimestamp: string;
  latestMileage: number;
  observedSpanMiles: number;
  latestConfidence: number | null;
  peakConfidence: number | null;
  eventCount: number;
  leftCensored: boolean;
  noteCount: number;
  createdAt: string;
  updatedAt: string;
  lastActivityAt: string;
  details: Record<string, unknown>;
};

type CaseActivity = {
  id: number;
  caseId: number;
  createdAt: string;
  activityType: string;
  actor: string;
  fromValue: string | null;
  toValue: string | null;
  note: string | null;
  details: Record<string, unknown>;
};

type CaseFeed = {
  runId: number;
  experimentId: string;
  totalMatched: number;
  returned: number;
  cases: DiagnosticCase[];
  interpretationPolicy: string;
};

type CaseSummary = {
  runId: number;
  experimentId: string;
  totalCases: number;
  activeCases: number;
  closedCases: number;
  unassignedCases: number;
  byStatus: Array<{ status: CaseStatus; cases: number }>;
  byPriority: Array<{ reviewPriority: CasePriority; cases: number }>;
  byClass: Array<{ hypothesisClass: string; cases: number }>;
};

type CaseDetail = {
  case: DiagnosticCase;
  activities: CaseActivity[];
  interpretationPolicy: string;
};

type Props = {
  selectedVehicleId: string | null;
  onSelectVehicle: (vehicleId: string) => void;
  runId?: number;
};

const statusOptions: CaseStatus[] = [
  'OPEN',
  'ACKNOWLEDGED',
  'INVESTIGATING',
  'MONITORING',
  'CLOSED',
];

const priorityOptions: CasePriority[] = ['HIGH', 'MEDIUM', 'LOW'];

function label(value: string | null | undefined) {
  if (!value) return '—';
  return value.replaceAll('_', ' ').replace(/\b\w/g, char => char.toUpperCase());
}

function pct(value: number | null | undefined) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`;
}

function miles(value: number | null | undefined) {
  return value == null
    ? '—'
    : `${new Intl.NumberFormat('en-US', {
        maximumFractionDigits: 0,
      }).format(value)} mi`;
}

async function requestJson<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(
      `${response.status} ${response.statusText}: ${message || url}`,
    );
  }
  return response.json() as Promise<T>;
}

export function DiagnosticCaseIntelligence({
  selectedVehicleId,
  onSelectVehicle,
  runId,
}: Props) {
  const [summary, setSummary] = useState<CaseSummary | null>(null);
  const [feed, setFeed] = useState<CaseFeed | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  const [classFilter, setClassFilter] = useState('');
  const [assignee, setAssignee] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const params = new URLSearchParams({ limit: '150' });
    if (statusFilter) params.set('status', statusFilter);
    if (priorityFilter) params.set('review_priority', priorityFilter);
    if (classFilter) params.set('hypothesis_class', classFilter);
    return params.toString();
  }, [statusFilter, priorityFilter, classFilter]);

  async function refresh() {
    const [nextSummary, nextFeed] = await Promise.all([
      requestJson<CaseSummary>(`${API}/api/v1/diagnostics/cases/summary`),
      requestJson<CaseFeed>(`${API}/api/v1/diagnostics/cases?${query}`),
    ]);

    setSummary(nextSummary);
    setFeed(nextFeed);
    setSelectedCaseId(current => {
      if (
        current &&
        nextFeed.cases.some(item => item.id === current)
      ) {
        return current;
      }

      if (selectedVehicleId) {
        const matched = nextFeed.cases.find(
          item => item.vehicleId === selectedVehicleId,
        );
        if (matched) return matched.id;
      }

      return nextFeed.cases[0]?.id ?? null;
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
              : 'Case API unavailable',
          );
        }
      } finally {
        if (alive) timer = setTimeout(cycle, 8000);
      }
    };

    void cycle();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [query, runId, selectedVehicleId]);

  useEffect(() => {
    if (!selectedCaseId) {
      setDetail(null);
      return;
    }

    let alive = true;
    requestJson<CaseDetail>(
      `${API}/api/v1/diagnostics/cases/${selectedCaseId}`,
    )
      .then(value => {
        if (!alive) return;
        setDetail(value);
        setAssignee(value.case.assignedTo ?? '');
        onSelectVehicle(value.case.vehicleId);
      })
      .catch(detailError => {
        if (alive) {
          setError(
            detailError instanceof Error
              ? detailError.message
              : 'Case detail unavailable',
          );
        }
      });

    return () => {
      alive = false;
    };
  }, [selectedCaseId, runId]);

  const classes = useMemo(
    () => summary?.byClass.map(item => item.hypothesisClass) ?? [],
    [summary],
  );

  async function updateCase(
    patch: Record<string, unknown>,
  ) {
    if (!selectedCaseId) return;
    setBusy(true);
    try {
      await requestJson<DiagnosticCase>(
        `${API}/api/v1/diagnostics/cases/${selectedCaseId}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            actor: 'dashboard_operator',
            ...patch,
          }),
        },
      );
      await refresh();
      setDetail(
        await requestJson<CaseDetail>(
          `${API}/api/v1/diagnostics/cases/${selectedCaseId}`,
        ),
      );
      setError(null);
    } catch (updateError) {
      setError(
        updateError instanceof Error
          ? updateError.message
          : 'Case update failed',
      );
    } finally {
      setBusy(false);
    }
  }

  async function addNote() {
    const trimmed = note.trim();
    if (!selectedCaseId || !trimmed) return;
    setBusy(true);
    try {
      await requestJson<CaseActivity>(
        `${API}/api/v1/diagnostics/cases/${selectedCaseId}/notes`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            actor: 'dashboard_operator',
            note: trimmed,
          }),
        },
      );
      setNote('');
      await refresh();
      setDetail(
        await requestJson<CaseDetail>(
          `${API}/api/v1/diagnostics/cases/${selectedCaseId}`,
        ),
      );
      setError(null);
    } catch (noteError) {
      setError(
        noteError instanceof Error
          ? noteError.message
          : 'Note update failed',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel diagnosticCasePanel">
      <div className="panelTitleRow">
        <div className="panelTitle">
          <span>DIAGNOSTIC OPERATIONS</span>
          <h2>Case intelligence & investigation workflow</h2>
        </div>
        <span className="methodBadge">
          EPISODE-DERIVED · AUDITABLE WORKFLOW
        </span>
      </div>

      <p className="muted diagnosticCasePolicy">
        Cases organize persisted model-hypothesis episodes for operational
        review. Priority, status, assignment and notes are workflow metadata —
        not physical-failure truth, attribution or causal proof.
      </p>

      {error && (
        <div className="diagnosticError">
          <AlertTriangle size={14} />
          <span>{error}</span>
        </div>
      )}

      <div className="diagnosticCaseMetrics">
        <CaseMetric
          label="Total cases"
          value={summary?.totalCases ?? 0}
          icon={<ClipboardList />}
        />
        <CaseMetric
          label="Active"
          value={summary?.activeCases ?? 0}
          icon={<Search />}
        />
        <CaseMetric
          label="High priority"
          value={
            summary?.byPriority.find(
              item => item.reviewPriority === 'HIGH',
            )?.cases ?? 0
          }
          icon={<AlertTriangle />}
        />
        <CaseMetric
          label="Unassigned"
          value={summary?.unassignedCases ?? 0}
          icon={<UserRound />}
        />
      </div>

      <div className="diagnosticCaseFilters">
        <select
          value={statusFilter}
          onChange={event => setStatusFilter(event.target.value)}
          aria-label="Filter cases by status"
        >
          <option value="">All statuses</option>
          {statusOptions.map(value => (
            <option key={value} value={value}>
              {label(value)}
            </option>
          ))}
        </select>

        <select
          value={priorityFilter}
          onChange={event => setPriorityFilter(event.target.value)}
          aria-label="Filter cases by priority"
        >
          <option value="">All priorities</option>
          {priorityOptions.map(value => (
            <option key={value} value={value}>
              {label(value)}
            </option>
          ))}
        </select>

        <select
          value={classFilter}
          onChange={event => setClassFilter(event.target.value)}
          aria-label="Filter cases by hypothesis class"
        >
          <option value="">All hypotheses</option>
          {classes.map(value => (
            <option key={value} value={value}>
              {label(value)}
            </option>
          ))}
        </select>

        <span>
          {feed?.totalMatched ?? 0} matched · {feed?.returned ?? 0} shown
        </span>
      </div>

      <div className="diagnosticCaseWorkspace">
        <div className="diagnosticCaseQueue">
          {(feed?.cases ?? []).length === 0 ? (
            <div className="diagnosticCaseEmpty">
              <ClipboardList size={22} />
              <span>
                No cases are materialized for this current run. Run the
                Phase 6.10 case materializer after episode generation.
              </span>
            </div>
          ) : (
            feed?.cases.map(item => (
              <button
                type="button"
                key={item.id}
                className={
                  selectedCaseId === item.id
                    ? 'diagnosticCaseRow selected'
                    : 'diagnosticCaseRow'
                }
                onClick={() => {
                  setSelectedCaseId(item.id);
                  onSelectVehicle(item.vehicleId);
                }}
              >
                <span
                  className={`diagnosticCasePriority priority-${item.reviewPriority.toLowerCase()}`}
                />
                <div>
                  <b>{item.vehicleId}</b>
                  <span>{label(item.hypothesisClass)}</span>
                  <small>
                    {label(item.status)} · {label(item.episodeStateAtCreation)}
                  </small>
                </div>
                <div>
                  <strong>{pct(item.latestConfidence)}</strong>
                  <span>{miles(item.latestMileage)}</span>
                </div>
              </button>
            ))
          )}
        </div>

        <div className="diagnosticCaseDetail">
          {!detail ? (
            <div className="diagnosticCaseEmpty">
              <Search size={24} />
              <span>Select a case to inspect its workflow and audit trail.</span>
            </div>
          ) : (
            <>
              <div className="diagnosticCaseHero">
                <div>
                  <span>CASE #{detail.case.id}</span>
                  <h3>{detail.case.title}</h3>
                  <small>
                    episode {detail.case.episodeId} · run {detail.case.runId}
                  </small>
                </div>
                <div
                  className={`diagnosticCasePriorityBadge priority-${detail.case.reviewPriority.toLowerCase()}`}
                >
                  {detail.case.reviewPriority}
                </div>
              </div>

              <div className="diagnosticCaseEvidenceGrid">
                <div>
                  <span>Hypothesis</span>
                  <b>{label(detail.case.hypothesisClass)}</b>
                </div>
                <div>
                  <span>Latest confidence</span>
                  <b>{pct(detail.case.latestConfidence)}</b>
                </div>
                <div>
                  <span>Observed span</span>
                  <b>{miles(detail.case.observedSpanMiles)}</b>
                </div>
                <div>
                  <span>Source events</span>
                  <b>{detail.case.eventCount}</b>
                </div>
                <div>
                  <span>Source state</span>
                  <b>{label(detail.case.episodeStateAtCreation)}</b>
                </div>
                <div>
                  <span>Left censored</span>
                  <b>{detail.case.leftCensored ? 'YES' : 'NO'}</b>
                </div>
              </div>

              <div className="diagnosticCaseControls">
                <label>
                  <span>Status</span>
                  <select
                    value={detail.case.status}
                    disabled={busy}
                    onChange={event =>
                      void updateCase({
                        status: event.target.value,
                      })
                    }
                  >
                    {statusOptions.map(value => (
                      <option key={value} value={value}>
                        {label(value)}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  <span>Review priority</span>
                  <select
                    value={detail.case.reviewPriority}
                    disabled={busy}
                    onChange={event =>
                      void updateCase({
                        review_priority: event.target.value,
                      })
                    }
                  >
                    {priorityOptions.map(value => (
                      <option key={value} value={value}>
                        {label(value)}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="diagnosticCaseAssignee">
                  <span>Assigned to</span>
                  <div>
                    <input
                      value={assignee}
                      disabled={busy}
                      placeholder="operator name"
                      onChange={event => setAssignee(event.target.value)}
                    />
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void updateCase({
                          assigned_to: assignee.trim() || null,
                          clear_assignment: !assignee.trim(),
                        })
                      }
                    >
                      Assign
                    </button>
                  </div>
                </label>
              </div>

              <div className="diagnosticCaseNoteComposer">
                <label htmlFor="diagnostic-case-note">
                  Investigation note
                </label>
                <textarea
                  id="diagnostic-case-note"
                  value={note}
                  disabled={busy}
                  maxLength={2000}
                  placeholder="Record observable evidence, review context, or next investigative step…"
                  onChange={event => setNote(event.target.value)}
                />
                <button
                  type="button"
                  disabled={busy || !note.trim()}
                  onClick={() => void addNote()}
                >
                  <MessageSquarePlus size={14} />
                  Add note
                </button>
              </div>

              <div className="diagnosticCaseActivity">
                <div className="diagnosticCaseActivityTitle">
                  <span>AUDIT TRAIL</span>
                  <b>{detail.activities.length} activities</b>
                </div>

                {detail.activities.map(activity => (
                  <div
                    className="diagnosticCaseActivityRow"
                    key={activity.id}
                  >
                    <div>
                      {activity.activityType === 'NOTE_ADDED' ? (
                        <MessageSquarePlus size={13} />
                      ) : activity.activityType === 'CASE_CREATED' ? (
                        <ShieldCheck size={13} />
                      ) : (
                        <CheckCircle2 size={13} />
                      )}
                    </div>
                    <div>
                      <b>{label(activity.activityType)}</b>
                      <span>
                        {activity.actor} ·{' '}
                        {new Date(activity.createdAt).toLocaleString()}
                      </span>
                      {activity.note && <p>{activity.note}</p>}
                      {!activity.note &&
                        (activity.fromValue || activity.toValue) && (
                          <p>
                            {label(activity.fromValue)} →{' '}
                            {label(activity.toValue)}
                          </p>
                        )}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function CaseMetric({
  label: metricLabel,
  value,
  icon,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
}) {
  return (
    <div className="diagnosticCaseMetric">
      <div>{icon}</div>
      <span>{metricLabel}</span>
      <strong>{value}</strong>
    </div>
  );
}
