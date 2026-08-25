import { useEffect, useMemo, useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  History,
  Lock,
  Radio,
} from 'lucide-react';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

type Hypothesis = {
  class: string;
  confidence: number;
};

type ObservedSignal = {
  feature: string;
  label: string;
  value: number;
  unit: string | null;
};

type ReplayPoint = {
  anchorTimestamp: string;
  anchorMileage: number;
  topClass: string;
  topConfidence: number;
  hypotheses: Hypothesis[];
  observableEvidence: ObservedSignal[];
};

type ReplayTimeline = {
  vehicleId: string;
  experimentId: string;
  runId: number;
  lineage: string;
  champion: string | null;
  points: ReplayPoint[];
  historyPolicy: {
    currentRunOnly: boolean;
    exactExperimentOnly: boolean;
    sameLineageOnly: boolean;
    usesPrivateFailureTruth: boolean;
    failureMarkersExposed: boolean;
    rowsPerVehicle: number | null;
    strideSamples: number | null;
    windowSize: number | null;
  };
  message: string;
};

const classLabels: Record<string, string> = {
  healthy: 'Healthy',
  coolant_pump: 'Coolant Pump',
  battery_pack: 'Battery Pack',
  inverter: 'Inverter',
  traction_motor: 'Traction Motor',
  coolant_temp_sensor: 'Coolant Sensor',
};

function humanize(value: string | null | undefined) {
  if (!value) return '—';
  return value.replaceAll('_', ' ').replace(/\b\w/g, char => char.toUpperCase());
}

function pct(value: number | null | undefined, digits = 1) {
  if (value == null) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

function miles(value: number | null | undefined) {
  if (value == null) return '—';
  return `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value)} mi`;
}

function timeLabel(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
}

async function fetchJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${url}`);
  }
  return response.json() as Promise<T>;
}

export function DiagnosticReplay({
  vehicleId,
  runId,
}: {
  vehicleId: string | null;
  runId?: number;
}) {
  const [timeline, setTimeline] = useState<ReplayTimeline | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!vehicleId) {
      setTimeline(null);
      setSelectedIndex(0);
      setError(null);
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    setError(null);

    fetchJson<ReplayTimeline>(
      `${API}/api/v1/diagnostics/vehicles/${encodeURIComponent(vehicleId)}/timeline?limit=64`,
      controller.signal,
    )
      .then(result => {
        setTimeline(result);
        setSelectedIndex(Math.max(0, result.points.length - 1));
      })
      .catch(fetchError => {
        if (!(fetchError instanceof DOMException && fetchError.name === 'AbortError')) {
          console.error('Diagnostic replay request failed:', fetchError);
          setTimeline(null);
          setError(fetchError instanceof Error ? fetchError.message : 'Replay unavailable');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [vehicleId, runId]);

  const point = timeline?.points[selectedIndex] ?? null;

  const geometry = useMemo(() => {
    const points = timeline?.points ?? [];
    if (points.length === 0) {
      return { polyline: '', points: [] as Array<ReplayPoint & { x: number; y: number }> };
    }

    const width = 920;
    const height = 210;
    const left = 42;
    const right = 18;
    const top = 18;
    const bottom = 32;
    const mileages = points.map(item => item.anchorMileage);
    const minMileage = Math.min(...mileages);
    const maxMileage = Math.max(...mileages);
    const mileageRange = Math.max(1, maxMileage - minMileage);

    const plotted = points.map(item => {
      const x = left + ((item.anchorMileage - minMileage) / mileageRange) * (width - left - right);
      const y = top + (1 - item.topConfidence) * (height - top - bottom);
      return { ...item, x, y };
    });

    return {
      polyline: plotted.map(item => `${item.x},${item.y}`).join(' '),
      points: plotted,
    };
  }, [timeline]);

  const first = timeline?.points[0] ?? null;
  const last = timeline?.points.at(-1) ?? null;

  return (
    <section className="panel diagnosticReplayPanel">
      <div className="panelTitleRow">
        <div className="panelTitle">
          <span>INCIDENT REPLAY</span>
          <h2>Diagnostic timeline</h2>
        </div>
        <span className="methodBadge">
          <History size={12} /> CURRENT RUN ONLY
        </span>
      </div>

      {!vehicleId ? (
        <div className="replayEmpty">
          <History size={24} />
          <span>Select a root-cause incident to replay its diagnostic evolution.</span>
        </div>
      ) : loading ? (
        <div className="replayEmpty">
          <Radio size={22} />
          <span>Loading observable-only replay…</span>
        </div>
      ) : error ? (
        <div className="replayEmpty">
          <History size={22} />
          <span>{error}</span>
        </div>
      ) : !timeline || timeline.points.length === 0 ? (
        <div className="replayEmpty">
          <History size={24} />
          <strong>No replay points persisted for this run.</strong>
          <span>{timeline?.message ?? 'Run the Phase 6.6 diagnostic trainer once to populate replay history.'}</span>
        </div>
      ) : (
        <>
          <div className="replaySummary">
            <div><span>Vehicle</span><b>{timeline.vehicleId}</b></div>
            <div><span>Snapshots</span><b>{timeline.points.length}</b></div>
            <div><span>Mileage range</span><b>{miles(first?.anchorMileage)} → {miles(last?.anchorMileage)}</b></div>
            <div><span>Model run</span><b>{timeline.runId}</b></div>
          </div>

          <div className="replayGrid">
            <div className="replayChartColumn">
              <div className="replayChartLegend">
                <span>Top-class confidence over mileage</span>
                <small>
                  {timeline.historyPolicy.rowsPerVehicle ?? '—'} observable rows · stride{' '}
                  {timeline.historyPolicy.strideSamples ?? '—'} samples
                </small>
              </div>

              <div className="replayChartWrap">
                <svg className="replayChart" viewBox="0 0 920 210" role="img" aria-label="Diagnostic confidence timeline">
                  {[0.25, 0.5, 0.75, 1].map(level => {
                    const y = 18 + (1 - level) * 160;
                    return (
                      <g key={level}>
                        <line className="replayGridLine" x1="42" x2="902" y1={y} y2={y} />
                        <text className="replayAxisLabel" x="5" y={y + 3}>{Math.round(level * 100)}%</text>
                      </g>
                    );
                  })}
                  <polyline className="replayConfidenceLine" points={geometry.polyline} />
                  {geometry.points.map((item, index) => (
                    <circle
                      key={`${item.anchorTimestamp}-${index}`}
                      className={`replayTimelinePoint class-${item.topClass} ${index === selectedIndex ? 'selected' : ''}`}
                      cx={item.x}
                      cy={item.y}
                      r={index === selectedIndex ? 6 : 4}
                      onClick={() => setSelectedIndex(index)}
                    />
                  ))}
                  <text className="replayAxisTitle" x="42" y="203">{miles(first?.anchorMileage)}</text>
                  <text className="replayAxisTitle" x="902" y="203" textAnchor="end">{miles(last?.anchorMileage)}</text>
                </svg>
              </div>

              <div className="replayScrubber">
                <button onClick={() => setSelectedIndex(index => Math.max(0, index - 1))} disabled={selectedIndex <= 0} aria-label="Previous replay point">
                  <ChevronLeft size={14} />
                </button>
                <input
                  type="range"
                  min={0}
                  max={Math.max(0, timeline.points.length - 1)}
                  value={selectedIndex}
                  onChange={event => setSelectedIndex(Number(event.currentTarget.value))}
                  aria-label="Replay position"
                />
                <button
                  onClick={() => setSelectedIndex(index => Math.min(timeline.points.length - 1, index + 1))}
                  disabled={selectedIndex >= timeline.points.length - 1}
                  aria-label="Next replay point"
                >
                  <ChevronRight size={14} />
                </button>
              </div>

              <div className="replayClassLegend">
                {['healthy', 'coolant_pump', 'battery_pack', 'inverter', 'traction_motor', 'coolant_temp_sensor'].map(value => (
                  <span key={value}>
                    <i className={`diagnosticClassDot class-${value}`} />
                    {classLabels[value]}
                  </span>
                ))}
              </div>
            </div>

            <div className="replayInspector">
              {point && (
                <>
                  <div className="replaySnapshotHeader">
                    <div>
                      <span>Replay snapshot</span>
                      <b>{miles(point.anchorMileage)}</b>
                      <small>{timeLabel(point.anchorTimestamp)}</small>
                    </div>
                    <div>
                      <strong>{pct(point.topConfidence)}</strong>
                      <span>{classLabels[point.topClass] ?? humanize(point.topClass)}</span>
                    </div>
                  </div>

                  <div className="replayHypotheses">
                    <span className="diagnosticSectionLabel">COMPETING HYPOTHESES</span>
                    {point.hypotheses.map((hypothesis, index) => (
                      <div className="replayHypothesisRow" key={hypothesis.class}>
                        <span>{index + 1}</span>
                        <b>{classLabels[hypothesis.class] ?? humanize(hypothesis.class)}</b>
                        <div><i style={{ width: `${Math.max(1, hypothesis.confidence * 100)}%` }} /></div>
                        <strong>{pct(hypothesis.confidence)}</strong>
                      </div>
                    ))}
                  </div>

                  <div className="replaySignals">
                    <span className="diagnosticSectionLabel">OBSERVED SIGNALS</span>
                    {point.observableEvidence.map(signal => (
                      <div key={signal.feature}>
                        <span>{signal.label}</span>
                        <b>{signal.value.toFixed(3)}{signal.unit ? ` ${signal.unit}` : ''}</b>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="replayPolicy">
            <Lock size={14} />
            <span>
              Replay points are scored from observable telemetry using the same experiment, model run, lineage, and champion. Private simulator failure truth is not used, and hidden failure markers are intentionally not shown on this timeline.
            </span>
          </div>
        </>
      )}
    </section>
  );
}
