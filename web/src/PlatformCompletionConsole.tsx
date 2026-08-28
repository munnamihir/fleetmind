import {
  useEffect,
  useMemo,
  useState,
  type ChangeEvent,
  type ReactNode,
} from 'react';
import {
  Activity,
  Boxes,
  CheckCircle2,
  FlaskConical,
  Gauge,
  GitCompareArrows,
  Layers3,
  RefreshCw,
  Rocket,
  ServerCog,
  ShieldCheck,
  Waypoints,
} from 'lucide-react';

import './PlatformCompletionConsole.css';


const API =
  import.meta.env.VITE_API_URL ??
  'http://localhost:8000';


type View =
  | 'OVERVIEW'
  | 'POLICIES'
  | 'SHADOW'
  | 'OBSERVABILITY'
  | 'MODEL_OPS'
  | 'ASSETS'
  | 'DEPLOYMENT';


type Props = {
  runId?: number;
};


type PlatformStatus = {
  phase: string;
  environment: string;
  counts: Record<string, number>;
  latestTelemetryAt: string | null;
  archive: {
    manifestPath: string;
    manifestPresent: boolean;
  };
  capabilities: Record<string, unknown>;
  validationBoundary: {
    implementationDelivered: boolean;
    hundredKEventsPerSecondEmpiricallyVerified: boolean;
    disasterRecoveryEmpiricallyVerified: boolean;
    productionSLOsClaimedAchieved: boolean;
  };
};


type Slo = {
  version: string;
  measurementOnly: boolean;
  objectives: Array<{
    name: string;
    target?: number;
    targetSeconds?: number;
    window: string;
    indicator: string;
  }>;
};


type Policy = {
  id: number;
  policyKey: string;
  version: string;
  name: string;
  description: string;
  status: string;
  rules: Record<string, unknown>;
  createdAt: string;
  promotedAt: string | null;
};


type PolicyEvaluation = {
  id: number;
  policyId: number;
  createdAt: string;
  inputSource: string;
  inputIsFrozen: boolean;
  candidateCount: number;
  duplicateSuppressed: number;
  conflictCount: number;
  summary: Record<string, unknown>;
};


type ShadowExperiment = {
  id: number;
  experimentKey: string;
  controlPolicyId: number;
  candidatePolicyId: number;
  createdAt: string;
  inputSource: string;
  inputIsFrozen: boolean;
  comparison: {
    controlCandidateCount?: number;
    candidateCandidateCount?: number;
    overlapCount?: number;
    candidateVolumeDelta?: number;
    candidateVolumeDeltaPct?: number;
    candidateConflicts?: number;
  };
};


type RegisteredModel = {
  id: number;
  modelName: string;
  version: string;
  lineage: string;
  stage: string;
  featureSchemaSha256: string;
  benchmarkSnapshotSha256: string | null;
  benchmarkStatus: string | null;
  createdAt: string;
};


type DriftReport = {
  model: RegisteredModel;
  drift: {
    status: string;
    features: Array<{
      feature: string;
      baselineMean: number;
      currentMean: number;
      standardizedMeanShift: number;
      status: string;
    }>;
  };
};


type AssetSummary = {
  assetCount: number;
  attentionRequired: number;
  byType: Array<{
    assetType: string;
    assets: number;
    healthy: number;
    degraded: number;
    critical: number;
  }>;
};


type AssetPlugins = {
  rulesVersion: string;
  plugins: Array<{
    assetType: string;
    requiredMetrics: string[];
    metricRules: Array<{
      metric: string;
      warnAbove: number;
      criticalAbove: number;
      unit: string;
    }>;
  }>;
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


function post<T>(
  url: string,
  body: unknown = {},
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


function number(
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


function compactHash(
  value: string | null | undefined,
) {
  if (!value) return '—';
  return value.length <= 14
    ? value
    : `${value.slice(0, 8)}…${value.slice(-6)}`;
}


export function PlatformCompletionConsole({
  runId,
}: Props) {
  const [
    view,
    setView,
  ] = useState<View>('OVERVIEW');

  const [
    status,
    setStatus,
  ] = useState<PlatformStatus | null>(
    null,
  );
  const [
    slo,
    setSlo,
  ] = useState<Slo | null>(
    null,
  );
  const [
    policies,
    setPolicies,
  ] = useState<Policy[]>([]);
  const [
    evaluations,
    setEvaluations,
  ] = useState<PolicyEvaluation[]>([]);
  const [
    shadow,
    setShadow,
  ] = useState<ShadowExperiment[]>([]);
  const [
    models,
    setModels,
  ] = useState<RegisteredModel[]>([]);
  const [
    drift,
    setDrift,
  ] = useState<DriftReport | null>(
    null,
  );
  const [
    assets,
    setAssets,
  ] = useState<AssetSummary | null>(
    null,
  );
  const [
    plugins,
    setPlugins,
  ] = useState<AssetPlugins | null>(
    null,
  );

  const [
    selectedPolicyId,
    setSelectedPolicyId,
  ] = useState<number | null>(
    null,
  );
  const [
    controlPolicyId,
    setControlPolicyId,
  ] = useState<number | null>(
    null,
  );
  const [
    candidatePolicyId,
    setCandidatePolicyId,
  ] = useState<number | null>(
    null,
  );
  const [
    selectedModelId,
    setSelectedModelId,
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
        nextStatus,
        nextSlo,
        nextPolicies,
        nextEvaluations,
        nextShadow,
        nextModels,
        nextAssets,
        nextPlugins,
      ] = await Promise.all([
        json<PlatformStatus>(
          `${API}/api/v1/platform/status`,
        ),
        json<Slo>(
          `${API}/api/v1/platform/slo`,
        ),
        json<{ policies: Policy[] }>(
          `${API}/api/v1/diagnostics/closed-loop/policies`,
        ),
        json<{
          evaluations: PolicyEvaluation[];
        }>(
          withRun(
            '/api/v1/diagnostics/closed-loop/policy-evaluations?limit=50',
            runId,
          ),
        ),
        json<{
          experiments: ShadowExperiment[];
        }>(
          withRun(
            '/api/v1/diagnostics/closed-loop/shadow-experiments?limit=25',
            runId,
          ),
        ),
        json<{
          models: RegisteredModel[];
        }>(
          `${API}/api/v1/platform/model-registry`,
        ),
        json<AssetSummary>(
          `${API}/api/v1/platform/assets/summary`,
        ),
        json<AssetPlugins>(
          `${API}/api/v1/platform/assets/plugins`,
        ),
      ]);

      setStatus(nextStatus);
      setSlo(nextSlo);
      setPolicies(
        nextPolicies.policies,
      );
      setEvaluations(
        nextEvaluations.evaluations,
      );
      setShadow(
        nextShadow.experiments,
      );
      setModels(nextModels.models);
      setAssets(nextAssets);
      setPlugins(nextPlugins);

      setSelectedPolicyId(
        current =>
          current ??
          nextPolicies.policies[0]
            ?.id ??
          null,
      );

      setControlPolicyId(
        current =>
          current ??
          nextPolicies.policies[0]
            ?.id ??
          null,
      );

      setCandidatePolicyId(
        current =>
          current ??
          nextPolicies.policies[1]
            ?.id ??
          nextPolicies.policies[0]
            ?.id ??
          null,
      );

      setSelectedModelId(
        current =>
          current ??
          nextModels.models[0]
            ?.id ??
          null,
      );

      setError(null);
    } catch (refreshError) {
      setError(
        refreshError instanceof Error
          ? refreshError.message
          : 'Platform APIs unavailable',
      );
    } finally {
      setLoading(false);
    }
  }

  async function bootstrapPolicies() {
    setLoading(true);

    try {
      await post(
        `${API}/api/v1/diagnostics/closed-loop/policies/bootstrap?actor=operator`,
      );
      await refresh();
    } catch (actionError) {
      setError(
        actionError instanceof Error
          ? actionError.message
          : 'Policy bootstrap failed',
      );
    } finally {
      setLoading(false);
    }
  }

  async function evaluatePolicy() {
    if (!selectedPolicyId) {
      return;
    }

    setLoading(true);

    try {
      await post(
        withRun(
          `/api/v1/diagnostics/closed-loop/policies/${selectedPolicyId}/evaluate`,
          runId,
        ),
        {
          actor: 'operator',
          persist: true,
        },
      );
      await refresh();
    } catch (actionError) {
      setError(
        actionError instanceof Error
          ? actionError.message
          : 'Policy replay failed',
      );
    } finally {
      setLoading(false);
    }
  }

  async function runShadow() {
    if (
      !controlPolicyId ||
      !candidatePolicyId ||
      controlPolicyId ===
        candidatePolicyId
    ) {
      setError(
        'Choose different control and candidate policies.',
      );
      return;
    }

    setLoading(true);

    try {
      await post(
        withRun(
          '/api/v1/diagnostics/closed-loop/shadow-experiments',
          runId,
        ),
        {
          controlPolicyId,
          candidatePolicyId,
          actor: 'operator',
          persist: true,
        },
      );
      await refresh();
    } catch (actionError) {
      setError(
        actionError instanceof Error
          ? actionError.message
          : 'Shadow experiment failed',
      );
    } finally {
      setLoading(false);
    }
  }

  async function loadDrift() {
    if (!selectedModelId) {
      return;
    }

    setLoading(true);

    try {
      setDrift(
        await json<DriftReport>(
          `${API}/api/v1/platform/model-registry/${selectedModelId}/drift`,
        ),
      );
      setError(null);
    } catch (actionError) {
      setError(
        actionError instanceof Error
          ? actionError.message
          : 'Drift report failed',
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
      30000,
    );

    return () =>
      clearInterval(timer);
  }, [runId]);

  const selectedPolicy =
    policies.find(
      row =>
        row.id ===
        selectedPolicyId,
    ) ??
    policies[0] ??
    null;

  const selectedModel =
    models.find(
      row =>
        row.id ===
        selectedModelId,
    ) ??
    models[0] ??
    null;

  const latestEvaluation =
    useMemo(
      () =>
        evaluations.find(
          row =>
            row.policyId ===
            selectedPolicy?.id,
        ) ??
        null,
      [
        evaluations,
        selectedPolicy,
      ],
    );

  return (
    <section className="platformCompletion">
      <div className="platformCompletionHeader">
        <div>
          <span className="diagnosticSectionLabel">
            PHASES 8.4–9.5 · PLATFORM COMPLETION
          </span>
          <h2>
            Policy learning, platform operations and multi-asset reliability
          </h2>
          <p className="muted">
            FleetMind's remaining roadmap is exposed here as governed,
            observable platform capability. Runtime benchmarks and production
            SLO achievement remain evidence-dependent claims.
          </p>
        </div>

        <button
          type="button"
          className="platformRefresh"
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

      {error && (
        <div className="diagnosticError">
          {error}
        </div>
      )}

      <div className="platformTabs">
        {([
          [
            'OVERVIEW',
            'Overview',
            <Layers3 size={14} />,
          ],
          [
            'POLICIES',
            'Policy Lab',
            <FlaskConical size={14} />,
          ],
          [
            'SHADOW',
            'Shadow',
            <GitCompareArrows size={14} />,
          ],
          [
            'OBSERVABILITY',
            'Observability',
            <Gauge size={14} />,
          ],
          [
            'MODEL_OPS',
            'Model Ops',
            <Rocket size={14} />,
          ],
          [
            'ASSETS',
            'Multi-Asset',
            <Boxes size={14} />,
          ],
          [
            'DEPLOYMENT',
            'Deployment',
            <ServerCog size={14} />,
          ],
        ] as Array<
          [
            View,
            string,
            ReactNode,
          ]
        >).map(
          ([
            id,
            label,
            icon,
          ]) => (
            <button
              key={id}
              type="button"
              className={
                view === id
                  ? 'active'
                  : ''
              }
              onClick={() =>
                setView(id)
              }
            >
              {icon}
              {label}
            </button>
          ),
        )}
      </div>

      {view === 'OVERVIEW' && (
        <div className="platformView">
          <div className="platformMetricGrid">
            <PlatformMetric
              label="Observed outcomes"
              value={number(
                status?.counts
                  ?.outcomes,
              )}
              detail="Phase 8.2"
            />
            <PlatformMetric
              label="Policies"
              value={number(
                status?.counts
                  ?.policies,
              )}
              detail="Phase 8.4"
            />
            <PlatformMetric
              label="Shadow experiments"
              value={number(
                status?.counts
                  ?.shadowExperiments,
              )}
              detail="Phase 8.5"
            />
            <PlatformMetric
              label="Registered models"
              value={number(
                status?.counts
                  ?.registeredModels,
              )}
              detail="Phase 9.4"
            />
            <PlatformMetric
              label="Multi-asset rows"
              value={number(
                status?.counts
                  ?.assetTelemetryRows,
              )}
              detail="Phase 9.5"
            />
          </div>

          <div className="platformOverviewGrid">
            <article className="panel">
              <div className="panelTitle">
                <span>
                  PLATFORM CAPABILITIES
                </span>
                <h3>
                  Implemented surfaces
                </h3>
              </div>

              <div className="platformCapabilityList">
                {Object.entries(
                  status?.capabilities ??
                    {},
                ).map(
                  ([
                    key,
                    value,
                  ]) => (
                    <div key={key}>
                      <CheckCircle2
                        size={14}
                      />
                      <span>
                        {humanize(
                          key,
                        )}
                      </span>
                      <b>
                        {Array.isArray(
                          value,
                        )
                          ? value.join(
                              ', ',
                            )
                          : String(
                              value,
                            )}
                      </b>
                    </div>
                  ),
                )}
              </div>
            </article>

            <article className="panel">
              <div className="panelTitle">
                <span>
                  VALIDATION BOUNDARY
                </span>
                <h3>
                  What is not claimed
                </h3>
              </div>

              <div className="platformBoundaryList">
                <div>
                  <span>
                    100K events/sec
                  </span>
                  <b>
                    Harness delivered ·
                    environment result
                    pending
                  </b>
                </div>
                <div>
                  <span>
                    Disaster recovery
                  </span>
                  <b>
                    Procedure delivered ·
                    production RPO/RTO
                    unproven
                  </b>
                </div>
                <div>
                  <span>
                    Production SLOs
                  </span>
                  <b>
                    Defined and measured ·
                    not claimed achieved
                  </b>
                </div>
                <div>
                  <span>
                    Physical AI
                  </span>
                  <b>
                    Reliability telemetry
                    only · no autonomous
                    control
                  </b>
                </div>
              </div>
            </article>
          </div>
        </div>
      )}

      {view === 'POLICIES' && (
        <div className="platformView">
          <div className="platformActionBar">
            <button
              type="button"
              onClick={() =>
                void bootstrapPolicies()
              }
              disabled={loading}
            >
              Bootstrap defaults
            </button>
            <select
              value={
                selectedPolicyId ??
                ''
              }
              onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                setSelectedPolicyId(
                  event.target.value
                    ? Number(
                        event.target
                          .value,
                      )
                    : null,
                )
              }
            >
              {policies.map(
                row => (
                  <option
                    key={row.id}
                    value={row.id}
                  >
                    {row.name} ·{' '}
                    {row.version}
                  </option>
                ),
              )}
            </select>
            <button
              type="button"
              className="primary"
              onClick={() =>
                void evaluatePolicy()
              }
              disabled={
                loading ||
                !selectedPolicyId
              }
            >
              Replay frozen evidence
            </button>
          </div>

          {policies.length === 0 ? (
            <div className="empty">
              No recommendation policies
              exist yet. Bootstrap the
              default control/candidate
              pair.
            </div>
          ) : (
            <div className="platformPolicyGrid">
              <article className="panel">
                <div className="panelTitle">
                  <span>
                    VERSIONED POLICY
                  </span>
                  <h3>
                    {selectedPolicy?.name}
                  </h3>
                </div>

                <div className="platformKeyValues">
                  <div>
                    <span>
                      Identity
                    </span>
                    <b>
                      {
                        selectedPolicy
                          ?.policyKey
                      }
                    </b>
                  </div>
                  <div>
                    <span>
                      Version
                    </span>
                    <b>
                      {
                        selectedPolicy
                          ?.version
                      }
                    </b>
                  </div>
                  <div>
                    <span>
                      Status
                    </span>
                    <b>
                      {humanize(
                        selectedPolicy
                          ?.status,
                      )}
                    </b>
                  </div>
                </div>

                <pre className="platformJson">
                  {JSON.stringify(
                    selectedPolicy?.rules ??
                      {},
                    null,
                    2,
                  )}
                </pre>
              </article>

              <article className="panel">
                <div className="panelTitle">
                  <span>
                    LATEST REPLAY
                  </span>
                  <h3>
                    Policy evidence
                  </h3>
                </div>

                {!latestEvaluation ? (
                  <div className="empty">
                    Evaluate the selected
                    policy against the
                    current frozen
                    evidence.
                  </div>
                ) : (
                  <>
                    <div className="platformMetricGrid compact">
                      <PlatformMetric
                        label="Candidates"
                        value={number(
                          latestEvaluation
                            .candidateCount,
                        )}
                        detail="No recommendation writes"
                      />
                      <PlatformMetric
                        label="Duplicates removed"
                        value={number(
                          latestEvaluation
                            .duplicateSuppressed,
                        )}
                        detail="Deterministic suppression"
                      />
                      <PlatformMetric
                        label="Conflicts"
                        value={number(
                          latestEvaluation
                            .conflictCount,
                        )}
                        detail="Configured conflict rules"
                      />
                    </div>

                    <div className="platformEvidenceFlag">
                      <ShieldCheck
                        size={15}
                      />
                      <span>
                        Input:{' '}
                        {
                          latestEvaluation.inputSource
                        } ·{' '}
                        {latestEvaluation.inputIsFrozen
                          ? 'frozen'
                          : 'partial / non-frozen'}
                      </span>
                    </div>
                  </>
                )}
              </article>
            </div>
          )}
        </div>
      )}

      {view === 'SHADOW' && (
        <div className="platformView">
          <div className="platformActionBar">
            <label>
              Control
              <select
                value={
                  controlPolicyId ??
                  ''
                }
                onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                  setControlPolicyId(
                    Number(
                      event.target
                        .value,
                    ),
                  )
                }
              >
                {policies.map(
                  row => (
                    <option
                      key={row.id}
                      value={row.id}
                    >
                      {row.name}
                    </option>
                  ),
                )}
              </select>
            </label>

            <label>
              Candidate
              <select
                value={
                  candidatePolicyId ??
                  ''
                }
                onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                  setCandidatePolicyId(
                    Number(
                      event.target
                        .value,
                    ),
                  )
                }
              >
                {policies.map(
                  row => (
                    <option
                      key={row.id}
                      value={row.id}
                    >
                      {row.name}
                    </option>
                  ),
                )}
              </select>
            </label>

            <button
              type="button"
              className="primary"
              onClick={() =>
                void runShadow()
              }
              disabled={
                loading ||
                policies.length < 2
              }
            >
              Run shadow comparison
            </button>
          </div>

          <article className="panel">
            <div className="panelTitleRow">
              <div className="panelTitle">
                <span>
                  NO-WRITE EXPERIMENTS
                </span>
                <h3>
                  Control vs candidate
                </h3>
              </div>
              <span className="methodBadge">
                NO AUTOMATIC PROMOTION
              </span>
            </div>

            <div className="platformShadowList">
              {shadow.length === 0 ? (
                <div className="empty">
                  No shadow experiments
                  have been persisted.
                </div>
              ) : (
                shadow.map(
                  row => (
                    <div
                      key={row.id}
                      className="platformShadowRow"
                    >
                      <div>
                        <b>
                          Shadow #{row.id}
                        </b>
                        <span>
                          {row.inputSource} ·{' '}
                          {row.inputIsFrozen
                            ? 'frozen'
                            : 'partial'}
                        </span>
                      </div>
                      <div>
                        <span>
                          Control
                        </span>
                        <strong>
                          {number(
                            row
                              .comparison
                              .controlCandidateCount,
                          )}
                        </strong>
                      </div>
                      <div>
                        <span>
                          Candidate
                        </span>
                        <strong>
                          {number(
                            row
                              .comparison
                              .candidateCandidateCount,
                          )}
                        </strong>
                      </div>
                      <div>
                        <span>
                          Delta
                        </span>
                        <strong>
                          {number(
                            row
                              .comparison
                              .candidateVolumeDelta,
                          )}
                        </strong>
                      </div>
                      <div>
                        <span>
                          Overlap
                        </span>
                        <strong>
                          {number(
                            row
                              .comparison
                              .overlapCount,
                          )}
                        </strong>
                      </div>
                    </div>
                  ),
                )
              )}
            </div>
          </article>
        </div>
      )}

      {view ===
        'OBSERVABILITY' && (
        <div className="platformView">
          <div className="platformMetricGrid">
            <PlatformMetric
              label="Environment"
              value={
                status?.environment ??
                '—'
              }
              detail="FLEETMIND_ENV"
            />
            <PlatformMetric
              label="Telemetry freshness"
              value={
                status?.latestTelemetryAt
                  ? new Date(
                      status.latestTelemetryAt,
                    ).toLocaleTimeString()
                  : '—'
              }
              detail="Latest persisted telemetry"
            />
            <PlatformMetric
              label="Archive manifest"
              value={
                status?.archive
                  .manifestPresent
                  ? 'Present'
                  : 'Not mounted'
              }
              detail={
                status?.archive
                  .manifestPath ??
                '—'
              }
            />
          </div>

          <article className="panel">
            <div className="panelTitleRow">
              <div className="panelTitle">
                <span>
                  SLO TARGETS
                </span>
                <h3>
                  Measurable, not assumed
                </h3>
              </div>
              <span className="methodBadge">
                {slo?.version ?? '—'}
              </span>
            </div>

            <div className="platformSloGrid">
              {(slo?.objectives ?? [])
                .map(
                  objective => (
                    <div
                      key={
                        objective.name
                      }
                    >
                      <span>
                        {humanize(
                          objective.name,
                        )}
                      </span>
                      <strong>
                        {objective.targetSeconds !=
                        null
                          ? `< ${objective.targetSeconds}s`
                          : objective.target !=
                            null
                          ? `${(
                              objective.target *
                              100
                            ).toFixed(
                              2,
                            )}%`
                          : '—'}
                      </strong>
                      <small>
                        {objective.window} ·{' '}
                        {
                          objective.indicator
                        }
                      </small>
                    </div>
                  ),
                )}
            </div>

            <div className="platformEvidenceFlag">
              <Gauge size={15} />
              <span>
                Prometheus: :9090 ·
                Grafana: :3000 · API
                metrics: :8000/metrics
                when the optional platform
                profile is running.
              </span>
            </div>
          </article>
        </div>
      )}

      {view === 'MODEL_OPS' && (
        <div className="platformView">
          <div className="platformActionBar">
            <select
              value={
                selectedModelId ??
                ''
              }
              onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                setSelectedModelId(
                  event.target.value
                    ? Number(
                        event.target
                          .value,
                      )
                    : null,
                )
              }
            >
              {models.map(
                row => (
                  <option
                    key={row.id}
                    value={row.id}
                  >
                    {row.modelName} ·{' '}
                    {row.version} ·{' '}
                    {row.stage}
                  </option>
                ),
              )}
            </select>

            <button
              type="button"
              onClick={() =>
                void loadDrift()
              }
              disabled={
                loading ||
                !selectedModelId
              }
            >
              Evaluate drift
            </button>
          </div>

          {models.length === 0 ? (
            <div className="empty">
              No model-registry entries
              exist yet. Register a
              version through
              POST /api/v1/platform/model-registry.
            </div>
          ) : (
            <div className="platformModelGrid">
              <article className="panel">
                <div className="panelTitle">
                  <span>
                    REGISTRY
                  </span>
                  <h3>
                    {selectedModel
                      ?.modelName}{' '}
                    {selectedModel
                      ?.version}
                  </h3>
                </div>

                <div className="platformKeyValues">
                  <div>
                    <span>
                      Stage
                    </span>
                    <b>
                      {
                        selectedModel
                          ?.stage
                      }
                    </b>
                  </div>
                  <div>
                    <span>
                      Lineage
                    </span>
                    <b>
                      {
                        selectedModel
                          ?.lineage
                      }
                    </b>
                  </div>
                  <div>
                    <span>
                      Feature schema
                    </span>
                    <b>
                      {compactHash(
                        selectedModel
                          ?.featureSchemaSha256,
                      )}
                    </b>
                  </div>
                  <div>
                    <span>
                      Benchmark
                    </span>
                    <b>
                      {humanize(
                        selectedModel
                          ?.benchmarkStatus,
                      )}
                    </b>
                  </div>
                </div>
              </article>

              <article className="panel">
                <div className="panelTitle">
                  <span>
                    DISTRIBUTION SHIFT
                  </span>
                  <h3>
                    {drift
                      ? humanize(
                          drift.drift
                            .status,
                        )
                      : 'Run drift evaluation'}
                  </h3>
                </div>

                <div className="platformDriftList">
                  {(drift?.drift
                    .features ??
                    [])
                    .slice(0, 12)
                    .map(
                      row => (
                        <div
                          key={
                            row.feature
                          }
                        >
                          <b>
                            {humanize(
                              row.feature,
                            )}
                          </b>
                          <span>
                            shift{' '}
                            {number(
                              row.standardizedMeanShift,
                              3,
                            )}
                          </span>
                          <strong>
                            {
                              row.status
                            }
                          </strong>
                        </div>
                      ),
                    )}
                </div>
              </article>
            </div>
          )}
        </div>
      )}

      {view === 'ASSETS' && (
        <div className="platformView">
          <div className="platformMetricGrid">
            <PlatformMetric
              label="Assets"
              value={number(
                assets?.assetCount,
              )}
              detail="Latest asset states"
            />
            <PlatformMetric
              label="Attention required"
              value={number(
                assets?.attentionRequired,
              )}
              detail="Operational attention only"
            />
            <PlatformMetric
              label="Plugin types"
              value={number(
                plugins?.plugins
                  .length,
              )}
              detail="Robot · charger · energy"
            />
          </div>

          <div className="platformAssetGrid">
            {(assets?.byType ?? [])
              .map(row => (
                <article
                  className="panel"
                  key={
                    row.assetType
                  }
                >
                  <div className="panelTitle">
                    <span>
                      ASSET COHORT
                    </span>
                    <h3>
                      {humanize(
                        row.assetType,
                      )}
                    </h3>
                  </div>

                  <div className="platformKeyValues">
                    <div>
                      <span>
                        Assets
                      </span>
                      <b>
                        {row.assets}
                      </b>
                    </div>
                    <div>
                      <span>
                        Healthy
                      </span>
                      <b>
                        {row.healthy}
                      </b>
                    </div>
                    <div>
                      <span>
                        Degraded
                      </span>
                      <b>
                        {row.degraded}
                      </b>
                    </div>
                    <div>
                      <span>
                        Critical
                      </span>
                      <b>
                        {row.critical}
                      </b>
                    </div>
                  </div>
                </article>
              ))}

            {(plugins?.plugins ?? [])
              .map(plugin => (
                <article
                  className="panel"
                  key={
                    `plugin-${plugin.assetType}`
                  }
                >
                  <div className="panelTitle">
                    <span>
                      RELIABILITY PLUGIN
                    </span>
                    <h3>
                      {humanize(
                        plugin.assetType,
                      )}
                    </h3>
                  </div>
                  <p className="muted">
                    Required observable
                    metrics
                  </p>
                  <div className="platformPluginMetrics">
                    {plugin.requiredMetrics.map(
                      metric => (
                        <span
                          key={
                            metric
                          }
                        >
                          {humanize(
                            metric,
                          )}
                        </span>
                      ),
                    )}
                  </div>
                </article>
              ))}
          </div>

          <div className="fleetOpsGuardrail">
            <ShieldCheck
              size={17}
            />
            <div>
              <b>
                Multi-asset reliability ≠
                autonomous physical
                control.
              </b>
              <span>
                Robot, charger and energy
                plugins score observable
                operational attention only.
              </span>
            </div>
          </div>
        </div>
      )}

      {view === 'DEPLOYMENT' && (
        <div className="platformView">
          <div className="platformDeploymentGrid">
            <DeploymentCard
              icon={
                <Waypoints
                  size={18}
                />
              }
              title="Kafka scale"
              body="Target-rate load generator, worker backlog/replay test and broker-restart smoke test."
              command="python3 tools/kafka_load_generator.py --rate 100000 --duration 30"
            />
            <DeploymentCard
              icon={
                <ServerCog
                  size={18}
                />
              }
              title="Helm"
              body="API/worker/web deployments, migration job, HPA, PDB and environment overlays."
              command="helm template fleetmind deploy/helm/fleetmind -f deploy/helm/fleetmind/values-dev.yaml"
            />
            <DeploymentCard
              icon={
                <Activity
                  size={18}
                />
              }
              title="Platform profile"
              body="Optional asset ingestion, archive, Prometheus and Grafana services."
              command="docker compose -f docker-compose.yml -f docker-compose.platform.yml --profile platform up --build"
            />
            <DeploymentCard
              icon={
                <ShieldCheck
                  size={18}
                />
              }
              title="Recovery"
              body="Local backup/restore smoke test. Production RPO/RTO still requires environment-specific exercise."
              command="tools/disaster_recovery_smoke.sh"
            />
          </div>
        </div>
      )}
    </section>
  );
}


function PlatformMetric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="platformMetric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}


function DeploymentCard({
  icon,
  title,
  body,
  command,
}: {
  icon: ReactNode;
  title: string;
  body: string;
  command: string;
}) {
  return (
    <article className="panel platformDeploymentCard">
      <div>
        {icon}
        <h3>{title}</h3>
      </div>
      <p>{body}</p>
      <code>{command}</code>
    </article>
  );
}
