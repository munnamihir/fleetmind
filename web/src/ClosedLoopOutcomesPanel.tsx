import {
  useEffect,
  useMemo,
  useState,
} from 'react';
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Eye,
  RefreshCw,
  Save,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';

import './ClosedLoopOutcomesPanel.css';


const API =
  import.meta.env.VITE_API_URL ??
  'http://localhost:8000';


type Props = {
  runId?: number;
  selectedVehicleId?: string | null;
};


type OutcomeSummary = {
  runId: number;
  experimentId: string;
  evaluationVersion: string;
  total: number;
  byStatus: Array<{
    status: string;
    count: number;
  }>;
  executedRecommendationsWithOutcome: number;
};


type Outcome = {
  id?: number;
  recommendationId: number;
  runId?: number;
  experimentId?: string;
  vehicleId: string;
  recommendationType: string;
  evaluationKey: string;
  evaluationVersion: string;
  status: string;
  score: number;
  createdAt?: string;
  updatedAt?: string;
  executedAt?: string | null;
  observationCompletedAt?: string | null;
  baseline: Record<string, unknown>;
  post: Record<string, unknown> | null;
  factors: Array<{
    metric: string;
    baseline: unknown;
    post: unknown;
    delta: number | null;
    contribution: number;
    interpretation: string;
  }>;
};


type Effectiveness = {
  rulesVersion: string;
  recommendations: number;
  outcomes: number;
  outcomeDistribution: Record<string, number>;
  funnel: Record<string, number>;
  latency: {
    assignment: Latency;
    approval: Latency;
    execution: Latency;
    executionToObservation: Latency;
  };
  repeatedRecommendations: {
    repeatedGroups: number;
    recommendationsInRepeatedGroups: number;
  };
  coverageGapClosure: {
    comparableOutcomes: number;
    meanGapReduction: number | null;
  };
  groups: Array<{
    dimension: string;
    value: string;
    outcomes: number;
    eligibleOutcomes: number;
    evidenceGateMet: boolean;
    distribution: Record<string, number>;
    claimStatus: string;
  }>;
};


type Latency = {
  count: number;
  meanHours: number | null;
  medianHours: number | null;
  maxHours: number | null;
};


type EvaluationResponse = {
  runId: number;
  experimentId: string;
  evaluationVersion: string;
  executedRecommendations: number;
  materializeRequested: boolean;
  createdCount: number;
  updatedCount: number;
  existingCount: number;
  outcomes: Outcome[];
};


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


function n(
  value: number | null | undefined,
  digits = 0,
) {
  if (value == null) return '—';
  return value.toLocaleString(
    undefined,
    {
      maximumFractionDigits:
        digits,
    },
  );
}


function snapshotValue(
  snapshot: Record<string, unknown> | null,
  key: string,
  digits = 2,
) {
  if (!snapshot) return '—';
  const value = snapshot[key];

  if (typeof value === 'number') {
    return n(value, digits);
  }

  if (
    typeof value === 'string' &&
    value
  ) {
    return humanize(value);
  }

  return '—';
}


export function ClosedLoopOutcomesPanel({
  runId,
  selectedVehicleId,
}: Props) {
  const [
    summary,
    setSummary,
  ] = useState<OutcomeSummary | null>(
    null,
  );
  const [
    outcomes,
    setOutcomes,
  ] = useState<Outcome[]>([]);
  const [
    effectiveness,
    setEffectiveness,
  ] = useState<Effectiveness | null>(
    null,
  );
  const [
    preview,
    setPreview,
  ] = useState<EvaluationResponse | null>(
    null,
  );
  const [
    selectedOutcomeId,
    setSelectedOutcomeId,
  ] = useState<number | null>(
    null,
  );
  const [
    loading,
    setLoading,
  ] = useState(false);
  const [
    error,
    setError,
  ] = useState<string | null>(
    null,
  );

  async function refresh() {
    setLoading(true);

    try {
      const [
        nextSummary,
        nextOutcomes,
        nextEffectiveness,
      ] = await Promise.all([
        json<OutcomeSummary>(
          withRun(
            '/api/v1/diagnostics/closed-loop/outcomes/summary',
            runId,
          ),
        ),
        json<{
          outcomes: Outcome[];
        }>(
          withRun(
            '/api/v1/diagnostics/closed-loop/outcomes?limit=100',
            runId,
          ),
        ),
        json<Effectiveness>(
          withRun(
            '/api/v1/diagnostics/closed-loop/effectiveness?cohort_dimension=recommendationType',
            runId,
          ),
        ),
      ]);

      setSummary(nextSummary);
      setOutcomes(
        nextOutcomes.outcomes,
      );
      setEffectiveness(
        nextEffectiveness,
      );
      setSelectedOutcomeId(
        current => {
          if (
            current != null &&
            nextOutcomes.outcomes.some(
              row => row.id === current,
            )
          ) {
            return current;
          }

          return (
            nextOutcomes.outcomes[0]
              ?.id ??
            null
          );
        },
      );
      setError(null);
    } catch (refreshError) {
      setError(
        refreshError instanceof Error
          ? refreshError.message
          : 'Outcome APIs unavailable',
      );
    } finally {
      setLoading(false);
    }
  }

  async function evaluate(
    materialize: boolean,
  ) {
    setLoading(true);

    try {
      const result =
        await postJson<EvaluationResponse>(
          withRun(
            '/api/v1/diagnostics/closed-loop/outcomes/evaluate',
            runId,
          ),
          {
            actor: 'operator',
            materialize,
          },
        );

      setPreview(result);
      setError(null);

      if (materialize) {
        await refresh();
      }
    } catch (evaluationError) {
      setError(
        evaluationError instanceof Error
          ? evaluationError.message
          : 'Outcome evaluation failed',
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();

    const timer = setInterval(
      () => {
        void refresh();
      },
      20000,
    );

    return () =>
      clearInterval(timer);
  }, [runId]);

  const visibleOutcomes =
    useMemo(
      () => {
        if (!selectedVehicleId) {
          return outcomes;
        }

        const selected =
          outcomes.filter(
            row =>
              row.vehicleId ===
              selectedVehicleId,
          );

        return selected.length
          ? selected
          : outcomes;
      },
      [
        outcomes,
        selectedVehicleId,
      ],
    );

  const selectedOutcome =
    visibleOutcomes.find(
      row =>
        row.id ===
        selectedOutcomeId,
    ) ??
    visibleOutcomes[0] ??
    null;

  const byStatus =
    Object.fromEntries(
      (
        summary?.byStatus ?? []
      ).map(row => [
        row.status,
        row.count,
      ]),
    );

  return (
    <div className="closedLoopOutcomes">
      <div className="closedLoopOutcomeHeader">
        <div>
          <span className="diagnosticSectionLabel">
            PHASES 8.2–8.3 · OBSERVED OUTCOMES
          </span>
          <h3>
            Post-execution evidence
          </h3>
          <p className="muted">
            Compare observable evidence before and after an executed workflow.
            Classification does not prove that maintenance repaired a component
            or caused the observed change.
          </p>
        </div>

        <div className="closedLoopOutcomeActions">
          <button
            type="button"
            onClick={() =>
              void evaluate(false)
            }
            disabled={loading}
          >
            <Eye size={14} />
            Preview
          </button>
          <button
            type="button"
            className="primary"
            onClick={() =>
              void evaluate(true)
            }
            disabled={loading}
          >
            <Save size={14} />
            Persist observations
          </button>
          <button
            type="button"
            onClick={() =>
              void refresh()
            }
            disabled={loading}
          >
            <RefreshCw
              size={14}
              className={
                loading
                  ? 'spinning'
                  : ''
              }
            />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="diagnosticError">
          {error}
        </div>
      )}

      <div className="closedLoopOutcomeMetricGrid">
        <OutcomeMetric
          label="Observed outcomes"
          value={n(summary?.total)}
          detail={`${n(
            summary
              ?.executedRecommendationsWithOutcome,
          )} executed recommendations`}
        />
        <OutcomeMetric
          label="Improved"
          value={n(
            byStatus.IMPROVED,
          )}
          detail="Observed supportive change"
        />
        <OutcomeMetric
          label="Worsened"
          value={n(
            byStatus.WORSENED,
          )}
          detail="Observed adverse change"
        />
        <OutcomeMetric
          label="Pending / insufficient"
          value={n(
            (byStatus.PENDING_OBSERVATION ??
              0) +
              (byStatus.INSUFFICIENT_DATA ??
                0),
          )}
          detail="Evidence gate not complete"
        />
      </div>

      {preview && (
        <div className="closedLoopPreviewBanner">
          <Activity size={15} />
          <span>
            Latest {preview.materializeRequested
              ? 'materialized'
              : 'preview'} evaluation inspected{' '}
            <b>{preview.executedRecommendations}</b>{' '}
            executed recommendations ·{' '}
            {preview.createdCount} created ·{' '}
            {preview.updatedCount} updated.
          </span>
        </div>
      )}

      <div className="closedLoopOutcomeGrid">
        <article className="panel closedLoopOutcomeListPanel">
          <div className="panelTitleRow">
            <div className="panelTitle">
              <span>
                OUTCOME QUEUE
              </span>
              <h3>
                Observable classifications
              </h3>
            </div>
            {selectedVehicleId && (
              <span className="methodBadge">
                TARGET {selectedVehicleId}
              </span>
            )}
          </div>

          {visibleOutcomes.length === 0 ? (
            <div className="empty">
              No materialized post-execution outcomes yet. Execute a workflow,
              let new evidence accumulate, then persist outcome observations.
            </div>
          ) : (
            <div className="closedLoopOutcomeList">
              {visibleOutcomes.map(
                row => (
                  <button
                    type="button"
                    key={
                      row.id ??
                      row.evaluationKey
                    }
                    className={
                      selectedOutcome ===
                      row
                        ? 'closedLoopOutcomeRow selected'
                        : 'closedLoopOutcomeRow'
                    }
                    onClick={() =>
                      setSelectedOutcomeId(
                        row.id ?? null,
                      )
                    }
                  >
                    <div>
                      <b>
                        {row.vehicleId}
                      </b>
                      <span>
                        {humanize(
                          row.recommendationType,
                        )}
                      </span>
                    </div>
                    <OutcomeBadge
                      status={row.status}
                    />
                    <strong>
                      {row.score >= 0
                        ? '+'
                        : ''}
                      {n(row.score, 1)}
                    </strong>
                    <ArrowRight
                      size={14}
                    />
                  </button>
                ),
              )}
            </div>
          )}
        </article>

        <article className="panel closedLoopEvidencePanel">
          <div className="panelTitle">
            <span>
              BEFORE / AFTER
            </span>
            <h3>
              {selectedOutcome?.vehicleId ??
                'Select an outcome'}
            </h3>
          </div>

          {!selectedOutcome ? (
            <div className="empty">
              Select an observed outcome.
            </div>
          ) : (
            <>
              <div className="closedLoopEvidenceColumns">
                <SnapshotCard
                  label="Before execution"
                  snapshot={
                    selectedOutcome.baseline
                  }
                />
                <ArrowRight
                  size={20}
                  className="closedLoopEvidenceArrow"
                />
                <SnapshotCard
                  label="After execution"
                  snapshot={
                    selectedOutcome.post
                  }
                />
              </div>

              <div className="closedLoopFactorList">
                <span className="diagnosticSectionLabel">
                  DETERMINISTIC FACTORS
                </span>

                {selectedOutcome.factors.length ===
                0 ? (
                  <div className="empty compact">
                    No comparable factors met the evidence gate.
                  </div>
                ) : (
                  selectedOutcome.factors.map(
                    factor => (
                      <div
                        key={
                          factor.metric
                        }
                        className="closedLoopFactorRow"
                      >
                        <div>
                          {factor.contribution >
                          0 ? (
                            <TrendingDown
                              size={15}
                            />
                          ) : factor.contribution <
                            0 ? (
                            <TrendingUp
                              size={15}
                            />
                          ) : (
                            <Activity
                              size={15}
                            />
                          )}
                          <b>
                            {humanize(
                              factor.metric,
                            )}
                          </b>
                        </div>
                        <span>
                          Δ{' '}
                          {factor.delta == null
                            ? '—'
                            : n(
                                factor.delta,
                                3,
                              )}
                        </span>
                        <strong>
                          {factor.contribution >
                          0
                            ? '+'
                            : ''}
                          {n(
                            factor.contribution,
                            1,
                          )}
                        </strong>
                      </div>
                    ),
                  )
                )}
              </div>
            </>
          )}
        </article>
      </div>

      <article className="panel closedLoopEffectivenessPanel">
        <div className="panelTitleRow">
          <div className="panelTitle">
            <span>
              PHASE 8.3 · EFFECTIVENESS ANALYTICS
            </span>
            <h3>
              Workflow observations
            </h3>
          </div>
          <span className="methodBadge">
            DESCRIPTIVE · NON-CAUSAL
          </span>
        </div>

        <div className="closedLoopEffectivenessGrid">
          <EffectivenessMetric
            label="Assignment median"
            value={
              effectiveness
                ?.latency.assignment
                .medianHours
            }
            suffix="h"
          />
          <EffectivenessMetric
            label="Approval median"
            value={
              effectiveness
                ?.latency.approval
                .medianHours
            }
            suffix="h"
          />
          <EffectivenessMetric
            label="Execution median"
            value={
              effectiveness
                ?.latency.execution
                .medianHours
            }
            suffix="h"
          />
          <EffectivenessMetric
            label="Observation median"
            value={
              effectiveness
                ?.latency
                .executionToObservation
                .medianHours
            }
            suffix="h"
          />
          <EffectivenessMetric
            label="Repeated groups"
            value={
              effectiveness
                ?.repeatedRecommendations
                .repeatedGroups
            }
          />
          <EffectivenessMetric
            label="Mean gap reduction"
            value={
              effectiveness
                ?.coverageGapClosure
                .meanGapReduction
            }
          />
        </div>

        <div className="closedLoopCohortOutcomeList">
          {(effectiveness?.groups ?? [])
            .slice(0, 12)
            .map(group => (
              <div
                key={group.value}
                className="closedLoopCohortOutcomeRow"
              >
                <div>
                  <b>
                    {humanize(
                      group.value,
                    )}
                  </b>
                  <span>
                    {group.eligibleOutcomes}{' '}
                    eligible outcomes
                  </span>
                </div>
                <span>
                  {group.evidenceGateMet
                    ? 'Evidence gate met'
                    : 'Withheld — low evidence'}
                </span>
                <strong>
                  {group.evidenceGateMet
                    ? Object.entries(
                        group.distribution,
                      )
                        .map(
                          ([key, value]) =>
                            `${humanize(
                              key,
                            )}: ${value}`,
                        )
                        .join(' · ')
                    : '—'}
                </strong>
              </div>
            ))}
        </div>
      </article>

      <div className="fleetOpsGuardrail">
        <ShieldCheck size={17} />
        <div>
          <b>
            Observed improvement ≠ proven maintenance causality.
          </b>
          <span>
            FleetMind records model, telemetry and workflow changes after execution.
            It does not claim a physical repair, prevented failure, or safety effect.
          </span>
        </div>
      </div>
    </div>
  );
}


function OutcomeMetric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="closedLoopOutcomeMetric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}


function EffectivenessMetric({
  label,
  value,
  suffix = '',
}: {
  label: string;
  value:
    | number
    | null
    | undefined;
  suffix?: string;
}) {
  return (
    <div>
      <span>{label}</span>
      <strong>
        {value == null
          ? '—'
          : `${n(value, 2)}${suffix}`}
      </strong>
    </div>
  );
}


function OutcomeBadge({
  status,
}: {
  status: string;
}) {
  let icon = (
    <Activity size={13} />
  );

  if (status === 'IMPROVED') {
    icon = (
      <CheckCircle2 size={13} />
    );
  } else if (
    status === 'WORSENED'
  ) {
    icon = (
      <TrendingUp size={13} />
    );
  }

  return (
    <span
      className={`closedLoopOutcomeBadge status-${status.toLowerCase()}`}
    >
      {icon}
      {humanize(status)}
    </span>
  );
}


function SnapshotCard({
  label,
  snapshot,
}: {
  label: string;
  snapshot:
    | Record<string, unknown>
    | null;
}) {
  return (
    <div className="closedLoopSnapshot">
      <span>{label}</span>

      <div>
        <small>
          Anomaly score
        </small>
        <b>
          {snapshotValue(
            snapshot,
            'riskScore',
            4,
          )}
        </b>
      </div>

      <div>
        <small>
          Telemetry state
        </small>
        <b>
          {snapshotValue(
            snapshot,
            'telemetryStatus',
          )}
        </b>
      </div>

      <div>
        <small>
          Hypothesis
        </small>
        <b>
          {snapshotValue(
            snapshot,
            'topClass',
          )}
        </b>
      </div>

      <div>
        <small>
          Confidence
        </small>
        <b>
          {snapshotValue(
            snapshot,
            'topConfidence',
            4,
          )}
        </b>
      </div>

      <div>
        <small>
          Attention
        </small>
        <b>
          {snapshotValue(
            snapshot,
            'attentionScore',
            1,
          )}
        </b>
      </div>

      <div>
        <small>
          Coverage gaps
        </small>
        <b>
          {snapshotValue(
            snapshot,
            'coverageGapCount',
            0,
          )}
        </b>
      </div>

      <div>
        <small>
          Case state
        </small>
        <b>
          {snapshotValue(
            snapshot,
            'caseStatus',
          )}
        </b>
      </div>

      <div>
        <small>
          Mileage
        </small>
        <b>
          {snapshotValue(
            snapshot,
            'mileage',
            1,
          )}
        </b>
      </div>
    </div>
  );
}
