import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  BrainCircuit,
  ChevronRight,
  Cpu,
  Gauge,
  Lock,
  ShieldCheck,
  Target,
} from 'lucide-react';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

type DiagnosticClass =
  | 'healthy'
  | 'coolant_pump'
  | 'battery_pack'
  | 'inverter'
  | 'traction_motor'
  | 'coolant_temp_sensor';

type DiagnosticSummary = {
  runId: number;
  experimentId: string;
  lineage: string;
  champion: string | null;
  totalVehicles: number;
  nonHealthyVehicles: number;
  highConfidenceIncidents: number;
  highConfidenceThreshold: number;
  averageTopConfidence: number | null;
  byClass: Array<{
    class: string;
    vehicles: number;
    averageConfidence: number;
    maxConfidence: number;
  }>;
  interpretationPolicy: string;
  generatedAt: string;
};

type DiagnosticStatus = {
  status: string;
  runId?: number;
  experimentId?: string | null;
  lineage?: string;
  champion?: string | null;
  featureCount?: number;
  featureSchemaSha256?: string | null;
  developmentStatus?: string;
  benchmarkStatus?: string;
  snapshotStatus?: string;
};

type PerClassMetric = {
  precision: number;
  recall: number;
  f1: number;
  support: number;
};

type DiagnosticMetrics = {
  balancedAccuracy: number;
  macroF1: number;
  multiclassBrier: number;
  top2Accuracy: number;
  perClass: Record<string, PerClassMetric>;
  confusionMatrix: number[][];
};

type DiagnosticBenchmark = {
  runId: number;
  experimentId: string;
  lineage: string;
  champion: string | null;
  qualification: {
    status: string;
    examples: number;
    vehicles: number;
    reasons: string[];
    examplesByClass: Record<string, number>;
    vehiclesByClass: Record<string, number>;
    claimPolicy: string;
  } | null;
  snapshot: {
    status: string;
    sha256?: string | null;
    featureSchemaSha256?: string | null;
    message?: string;
  } | null;
  benchmark: {
    status: string;
    models: {
      multinomialLogistic: DiagnosticMetrics;
      transparentBaseline: DiagnosticMetrics;
      xgboostMulticlass: DiagnosticMetrics;
    } | null;
  } | null;
  metricsPublishable: boolean;
};

type Hypothesis = { class: string; confidence: number };
type ObservedSignal = {
  feature: string;
  label: string;
  value: number;
  unit: string | null;
};

type DiagnosticIncident = {
  vehicleId: string;
  experimentId: string;
  runId: number;
  topClass: string;
  topConfidence: number;
  anchorTimestamp: string;
  anchorMileage: number;
  hypotheses: Hypothesis[];
  observableEvidence: ObservedSignal[];
};

type VehicleDiagnostic = DiagnosticIncident & {
  modelLineage: string;
  champion: string | null;
  generatedAt: string;
  context: {
    model: string;
    factory: string;
    firmware: string;
    pumpRevision: string;
    mileage: number;
  } | null;
  interpretationPolicy: string;
};

const classOrder: DiagnosticClass[] = [
  'healthy',
  'coolant_pump',
  'battery_pack',
  'inverter',
  'traction_motor',
  'coolant_temp_sensor',
];

const classLabels: Record<string, string> = {
  healthy: 'Healthy',
  coolant_pump: 'Coolant Pump',
  battery_pack: 'Battery Pack',
  inverter: 'Inverter',
  traction_motor: 'Traction Motor',
  coolant_temp_sensor: 'Coolant Sensor',
};

const modelLabels: Record<string, string> = {
  xgboost_multiclass: 'XGBoost',
  multinomial_logistic: 'Multinomial Logistic',
  transparent_baseline: 'Transparent Baseline',
};

function humanize(value: string | null | undefined) {
  if (!value) return '—';
  return value.replaceAll('_', ' ').replace(/\b\w/g, char => char.toUpperCase());
}

function pct(value: number | null | undefined, digits = 1) {
  if (value == null) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

function number(value: number | null | undefined) {
  if (value == null) return '—';
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value);
}

function miles(value: number | null | undefined) {
  return value == null ? '—' : `${number(value)} mi`;
}

function compactHash(value: string | null | undefined) {
  if (!value) return '—';
  return `${value.slice(0, 10)}…${value.slice(-8)}`;
}

async function fetchJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${url}`);
  return response.json() as Promise<T>;
}

export function RootCauseDashboard() {
  const [summary, setSummary] = useState<DiagnosticSummary | null>(null);
  const [status, setStatus] = useState<DiagnosticStatus | null>(null);
  const [benchmark, setBenchmark] = useState<DiagnosticBenchmark | null>(null);
  const [incidents, setIncidents] = useState<DiagnosticIncident[]>([]);
  const [selectedVehicleId, setSelectedVehicleId] = useState<string | null>(null);
  const [selectedVehicle, setSelectedVehicle] = useState<VehicleDiagnostic | null>(null);
  const [loadingVehicle, setLoadingVehicle] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let timerId: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;

    async function refresh() {
      if (!alive) return;
      controller = new AbortController();
      try {
        const [nextSummary, nextStatus, nextBenchmark, nextIncidents] =
          await Promise.all([
            fetchJson<DiagnosticSummary>(
              `${API}/api/v1/diagnostics/summary?high_confidence_threshold=0.70`,
              controller.signal,
            ),
            fetchJson<DiagnosticStatus>(`${API}/api/v1/diagnostics/status`, controller.signal),
            fetchJson<DiagnosticBenchmark>(`${API}/api/v1/diagnostics/benchmark`, controller.signal),
            fetchJson<DiagnosticIncident[]>(
              `${API}/api/v1/diagnostics/incidents?limit=50&min_confidence=0.70`,
              controller.signal,
            ),
          ]);

        if (alive) {
          setSummary(nextSummary);
          setStatus(nextStatus);
          setBenchmark(nextBenchmark);
          setIncidents(nextIncidents);
          setError(null);
          setSelectedVehicleId(current => {
            if (current && nextIncidents.some(item => item.vehicleId === current)) {
              return current;
            }
            return nextIncidents[0]?.vehicleId ?? current;
          });
        }
      } catch (refreshError) {
        if (
          alive &&
          !(refreshError instanceof DOMException && refreshError.name === 'AbortError')
        ) {
          console.error('Root Cause dashboard refresh failed:', refreshError);
          setError(refreshError instanceof Error ? refreshError.message : 'Diagnostic API unavailable');
        }
      } finally {
        controller = undefined;
        if (alive) timerId = setTimeout(refresh, 8000);
      }
    }

    void refresh();
    return () => {
      alive = false;
      if (timerId !== undefined) clearTimeout(timerId);
      controller?.abort();
    };
  }, []);

  useEffect(() => {
    if (!selectedVehicleId) {
      setSelectedVehicle(null);
      return;
    }

    const controller = new AbortController();
    setLoadingVehicle(true);
    fetchJson<VehicleDiagnostic>(
      `${API}/api/v1/diagnostics/vehicles/${encodeURIComponent(selectedVehicleId)}`,
      controller.signal,
    )
      .then(setSelectedVehicle)
      .catch(vehicleError => {
        if (!(vehicleError instanceof DOMException && vehicleError.name === 'AbortError')) {
          console.error('Vehicle diagnostic request failed:', vehicleError);
          setSelectedVehicle(null);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingVehicle(false);
      });

    return () => controller.abort();
  }, [selectedVehicleId, status?.runId]);

  const classDistribution = useMemo(() => {
    const byClass = new Map((summary?.byClass ?? []).map(item => [item.class, item]));
    return classOrder.map(diagnosticClass => ({
      class: diagnosticClass,
      label: classLabels[diagnosticClass],
      vehicles: byClass.get(diagnosticClass)?.vehicles ?? 0,
      averageConfidence: byClass.get(diagnosticClass)?.averageConfidence ?? 0,
    }));
  }, [summary]);

  const championMetrics = useMemo(() => {
    const models = benchmark?.benchmark?.models;
    if (!models || !benchmark?.champion) return null;
    if (benchmark.champion === 'xgboost_multiclass') return models.xgboostMulticlass;
    if (benchmark.champion === 'multinomial_logistic') return models.multinomialLogistic;
    if (benchmark.champion === 'transparent_baseline') return models.transparentBaseline;
    return null;
  }, [benchmark]);

  const weakestClass = useMemo(() => {
    if (!championMetrics) return null;
    return Object.entries(championMetrics.perClass)
      .map(([diagnosticClass, metrics]) => ({
        diagnosticClass,
        recall: metrics.recall,
        support: metrics.support,
      }))
      .sort((a, b) => a.recall - b.recall)[0] ?? null;
  }, [championMetrics]);

  const maxClassVehicles = Math.max(1, ...classDistribution.map(item => item.vehicles));

  return (
    <div className="rootCauseDashboard">
      {error && (
        <div className="diagnosticError">
          <AlertTriangle size={15} />
          <span>{error}</span>
        </div>
      )}

      <section className="metrics diagnosticMetrics">
        <DiagnosticMetric
          icon={<Cpu />}
          label="Vehicles scored"
          value={number(summary?.totalVehicles)}
          detail={`run ${summary?.runId ?? '—'} · ${humanize(summary?.champion)}`}
        />
        <DiagnosticMetric
          icon={<Activity />}
          label="Non-healthy hypotheses"
          value={number(summary?.nonHealthyVehicles)}
          detail={
            summary
              ? `${pct(summary.nonHealthyVehicles / Math.max(1, summary.totalVehicles))} of current model outputs`
              : 'current model outputs'
          }
        />
        <DiagnosticMetric
          icon={<AlertTriangle />}
          label="High-confidence incidents"
          value={number(summary?.highConfidenceIncidents)}
          detail={`≥ ${pct(summary?.highConfidenceThreshold ?? 0.70, 0)} top-class confidence`}
        />
        <DiagnosticMetric
          icon={<Lock />}
          label="Frozen benchmark"
          value={number(benchmark?.qualification?.examples)}
          detail={
            benchmark?.snapshot?.status === 'locked'
              ? `${number(benchmark.qualification?.vehicles)} vehicles · SHA locked`
              : humanize(benchmark?.snapshot?.status)
          }
        />
      </section>

      <section className="diagnosticTopGrid">
        <article className="panel diagnosticDistributionPanel">
          <div className="panelTitleRow">
            <div className="panelTitle">
              <span>CURRENT MODEL OUTPUT</span>
              <h2>Fleet hypothesis distribution</h2>
            </div>
            <span className="methodBadge">RUN {summary?.runId ?? '—'}</span>
          </div>
          <p className="muted diagnosticPolicy">
            These are current model hypotheses across the scored fleet, not failure ground truth.
          </p>

          <div className="diagnosticClassList">
            {classDistribution.map(item => (
              <div className="diagnosticClassRow" key={item.class}>
                <div className="diagnosticClassMeta">
                  <span className={`diagnosticClassDot class-${item.class}`} />
                  <b>{item.label}</b>
                  <small>{pct(item.averageConfidence)} avg confidence</small>
                </div>
                <div className="diagnosticClassBar">
                  <span
                    className={`class-${item.class}`}
                    style={{
                      width: `${Math.max(
                        item.vehicles > 0 ? 2 : 0,
                        (item.vehicles / maxClassVehicles) * 100,
                      )}%`,
                    }}
                  />
                </div>
                <strong>{item.vehicles}</strong>
              </div>
            ))}
          </div>

          <div className="diagnosticRunMeta">
            <div><span>Experiment</span><b>{summary?.experimentId ?? status?.experimentId ?? '—'}</b></div>
            <div><span>Lineage</span><b>{summary?.lineage ?? status?.lineage ?? '—'}</b></div>
            <div><span>Feature schema</span><b>{compactHash(status?.featureSchemaSha256)}</b></div>
          </div>
        </article>

        <article className="panel diagnosticBenchmarkPanel">
          <div className="panelTitleRow">
            <div className="panelTitle">
              <span>MODEL EVIDENCE</span>
              <h2>Locked benchmark</h2>
            </div>
            <span className={`diagnosticLockBadge ${benchmark?.metricsPublishable ? 'qualified' : ''}`}>
              <ShieldCheck size={13} />
              {benchmark?.metricsPublishable ? 'PUBLISHABLE' : 'WITHHELD'}
            </span>
          </div>

          <div className="benchmarkHero">
            <div>
              <span>Validation-selected champion</span>
              <strong>{modelLabels[benchmark?.champion ?? ''] ?? humanize(benchmark?.champion)}</strong>
            </div>
            <div><span>Macro F1</span><strong>{pct(championMetrics?.macroF1)}</strong></div>
          </div>

          <div className="benchmarkStatGrid">
            <div><span>Balanced accuracy</span><b>{pct(championMetrics?.balancedAccuracy)}</b></div>
            <div><span>Top-2 accuracy</span><b>{pct(championMetrics?.top2Accuracy)}</b></div>
            <div>
              <span>Multiclass Brier</span>
              <b>{championMetrics?.multiclassBrier != null ? championMetrics.multiclassBrier.toFixed(4) : '—'}</b>
            </div>
            <div><span>Benchmark vehicles</span><b>{number(benchmark?.qualification?.vehicles)}</b></div>
          </div>

          <div className="snapshotBox">
            <Lock size={14} />
            <div>
              <span>{humanize(benchmark?.snapshot?.status)} snapshot</span>
              <b>{compactHash(benchmark?.snapshot?.sha256)}</b>
            </div>
          </div>

          {weakestClass && (
            <div className="diagnosticLimitation">
              <Target size={15} />
              <div>
                <span>Known benchmark limitation</span>
                <p>
                  Lowest champion recall is{' '}
                  <b>{classLabels[weakestClass.diagnosticClass] ?? humanize(weakestClass.diagnosticClass)}</b>{' '}
                  at <b>{pct(weakestClass.recall)}</b> across {number(weakestClass.support)} locked examples.
                </p>
              </div>
            </div>
          )}
        </article>
      </section>

      <section className="diagnosticWorkGrid">
        <article className="panel diagnosticIncidentPanel">
          <div className="panelTitleRow">
            <div className="panelTitle">
              <span>ROOT CAUSE QUEUE</span>
              <h2>High-confidence incidents</h2>
            </div>
            <span className="methodBadge">≥ {pct(summary?.highConfidenceThreshold ?? 0.70, 0)}</span>
          </div>

          <div className="diagnosticIncidentList">
            {incidents.length === 0 ? (
              <div className="empty">No non-healthy hypotheses currently exceed the incident threshold.</div>
            ) : incidents.map(incident => (
              <button
                key={incident.vehicleId}
                className={selectedVehicleId === incident.vehicleId ? 'diagnosticIncidentRow selected' : 'diagnosticIncidentRow'}
                onClick={() => setSelectedVehicleId(incident.vehicleId)}
              >
                <span className={`diagnosticClassDot class-${incident.topClass}`} />
                <div className="diagnosticIncidentIdentity">
                  <b>{incident.vehicleId}</b>
                  <span>{classLabels[incident.topClass] ?? humanize(incident.topClass)}</span>
                </div>
                <div className="diagnosticIncidentMileage">
                  <span>Diagnosed at</span>
                  <b>{miles(incident.anchorMileage)}</b>
                </div>
                <div className="diagnosticIncidentConfidence">
                  <strong>{pct(incident.topConfidence)}</strong>
                  <span>confidence</span>
                </div>
                <ChevronRight size={15} />
              </button>
            ))}
          </div>
        </article>

        <article className="panel vehicleInvestigationPanel">
          <div className="panelTitle">
            <span>VEHICLE INVESTIGATION</span>
            <h2>{selectedVehicle?.vehicleId ?? selectedVehicleId ?? 'Select an incident'}</h2>
          </div>

          {loadingVehicle ? (
            <div className="diagnosticVehicleEmpty"><BrainCircuit size={24} /><span>Loading diagnostic context…</span></div>
          ) : !selectedVehicle ? (
            <div className="diagnosticVehicleEmpty"><BrainCircuit size={24} /><span>Select a queued vehicle to inspect competing hypotheses.</span></div>
          ) : (
            <>
              <div className="diagnosticPrimary">
                <div>
                  <span>Primary hypothesis</span>
                  <strong>{classLabels[selectedVehicle.topClass] ?? humanize(selectedVehicle.topClass)}</strong>
                </div>
                <div><strong>{pct(selectedVehicle.topConfidence)}</strong><span>model confidence</span></div>
              </div>

              <div className="diagnosticMileagePair">
                <div><span>Diagnosed at</span><b>{miles(selectedVehicle.anchorMileage)}</b></div>
                <div><span>Current telemetry</span><b>{miles(selectedVehicle.context?.mileage)}</b></div>
              </div>

              <div className="hypothesisRank">
                <span className="diagnosticSectionLabel">COMPETING HYPOTHESES</span>
                {selectedVehicle.hypotheses.map((hypothesis, index) => (
                  <div className="hypothesisRankRow" key={hypothesis.class}>
                    <span>{index + 1}</span>
                    <b>{classLabels[hypothesis.class] ?? humanize(hypothesis.class)}</b>
                    <div><i style={{ width: `${Math.max(hypothesis.confidence * 100, 1)}%` }} /></div>
                    <strong>{pct(hypothesis.confidence)}</strong>
                  </div>
                ))}
              </div>

              <div className="observedSignals">
                <span className="diagnosticSectionLabel">OBSERVED SIGNALS</span>
                <p className="muted">
                  Telemetry context associated with the hypothesis. These values are not feature-attribution scores or causal proof.
                </p>
                <div className="observedSignalGrid">
                  {selectedVehicle.observableEvidence.map(signal => (
                    <div key={signal.feature}>
                      <span>{signal.label}</span>
                      <b>{signal.value.toFixed(3)}{signal.unit ? ` ${signal.unit}` : ''}</b>
                    </div>
                  ))}
                </div>
              </div>

              {selectedVehicle.context && (
                <div className="vehicleContext">
                  <span>{selectedVehicle.context.model}</span>
                  <span>{selectedVehicle.context.factory}</span>
                  <span>{selectedVehicle.context.firmware}</span>
                  <span>{selectedVehicle.context.pumpRevision}</span>
                </div>
              )}
            </>
          )}
        </article>
      </section>

      <section className="panel diagnosticComparisonPanel">
        <div className="panelTitleRow">
          <div className="panelTitle">
            <span>MODEL COMPARISON</span>
            <h2>Frozen benchmark performance</h2>
          </div>
          <span className="methodBadge">SELECTED ON VALIDATION · EVALUATED ON LOCKED HOLDOUT</span>
        </div>

        <ModelComparison benchmark={benchmark} />

        <div className="diagnosticClaimPolicy">
          <Gauge size={15} />
          <span>
            Benchmark metrics are shown only when the frozen evidence gate is qualified and the immutable snapshot is available. Model selection remains validation-only.
          </span>
        </div>
      </section>
    </div>
  );
}

function DiagnosticMetric({
  icon,
  label,
  value,
  detail,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <article className="metric">
      <div className="metricIcon">{icon}</div>
      <div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>
    </article>
  );
}

function ModelComparison({ benchmark }: { benchmark: DiagnosticBenchmark | null }) {
  const models = benchmark?.benchmark?.models;
  if (!benchmark?.metricsPublishable || !models) {
    return (
      <div className="diagnosticVehicleEmpty compact">
        <Lock size={20} />
        <span>Frozen benchmark metrics are currently withheld.</span>
      </div>
    );
  }

  const rows = [
    ['XGBoost', 'xgboost_multiclass', models.xgboostMulticlass] as const,
    ['Multinomial Logistic', 'multinomial_logistic', models.multinomialLogistic] as const,
    ['Transparent Baseline', 'transparent_baseline', models.transparentBaseline] as const,
  ];

  return (
    <div className="diagnosticModelTable">
      <div className="diagnosticModelHead">
        <span>Model</span><span>Macro F1</span><span>Balanced Acc.</span><span>Top-2</span><span>Brier ↓</span><span>Role</span>
      </div>
      {rows.map(([label, key, metrics]) => (
        <div className={benchmark.champion === key ? 'diagnosticModelRow champion' : 'diagnosticModelRow'} key={key}>
          <b>{label}</b>
          <span>{pct(metrics.macroF1)}</span>
          <span>{pct(metrics.balancedAccuracy)}</span>
          <span>{pct(metrics.top2Accuracy)}</span>
          <span>{metrics.multiclassBrier.toFixed(4)}</span>
          <strong>{benchmark.champion === key ? 'Champion' : 'Comparator'}</strong>
        </div>
      ))}
    </div>
  );
}
