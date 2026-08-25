import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  ArrowRight,
  Gauge,
  GitBranch,
  Radar,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

type TransitionVehicle = {
  vehicleId: string;
  experimentId: string;
  runId: number;
  latestClass: string;
  latestConfidence: number;
  latestAnchorMileage: number;
  firstClass: string;
  firstAnchorMileage: number;
  classChanges: number;
  recentClassChanges: number;
  recentStability: number;
  currentClassConfidenceSlopePer1kMiles: number;
  currentClassConfidenceDelta: number;
  newlyEmerging: boolean;
  emergenceObserved: boolean;
  firstEmergenceClass: string | null;
  firstEmergenceMileage: number | null;
  milesSinceEmergence: number | null;
  historicalTransitions: boolean;
  escalating: boolean;
  deescalating: boolean;
  volatile: boolean;
  persistent: boolean;
  attentionTier: string;
  attentionReason: string;
};

type TransitionResponse = {
  runId: number;
  experimentId: string;
  lineage: string;
  champion: string | null;
  thresholds: {
    recentWindowPoints: number;
    incidentConfidence: number;
    escalationPer1kMiles: number;
    stableFraction: number;
    volatileFraction: number;
    volatileClassChanges: number;
  };
  summary: {
    vehiclesAnalyzed: number;
    currentNonHealthy: number;
    newlyEmerging: number;
    emergenceObserved: number;
    historicalTransitions: number;
    escalating: number;
    deescalating: number;
    recentTransitions: number;
    volatile: number;
    persistent: number;
  };
  vehicles: TransitionVehicle[];
  interpretationPolicy: string;
  generatedAt: string;
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

function signedPct(value: number | null | undefined, digits = 1) {
  if (value == null) return '—';
  const pctValue = value * 100;
  return `${pctValue >= 0 ? '+' : ''}${pctValue.toFixed(digits)} pp`;
}

function miles(value: number | null | undefined) {
  if (value == null) return '—';
  return `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value)} mi`;
}

async function fetchJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${url}`);
  return response.json() as Promise<T>;
}

export function DiagnosticTransitionIntelligence({
  selectedVehicleId,
  onSelectVehicle,
  runId,
}: {
  selectedVehicleId: string | null;
  onSelectVehicle: (vehicleId: string) => void;
  runId?: number;
}) {
  const [data, setData] = useState<TransitionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let timerId: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;

    async function refresh() {
      if (!alive) return;
      controller = new AbortController();
      try {
        const next = await fetchJson<TransitionResponse>(
          `${API}/api/v1/diagnostics/transitions?limit=60&min_confidence=0.70`,
          controller.signal,
        );
        if (alive) {
          setData(next);
          setError(null);
        }
      } catch (refreshError) {
        if (alive && !(refreshError instanceof DOMException && refreshError.name === 'AbortError')) {
          console.error('Diagnostic transition intelligence refresh failed:', refreshError);
          setError(refreshError instanceof Error ? refreshError.message : 'Transition intelligence unavailable');
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
  }, [runId]);

  const strongest = useMemo(() => data?.vehicles.slice(0, 12) ?? [], [data]);

  return (
    <section className="panel transitionIntelPanel">
      <div className="panelTitleRow">
        <div className="panelTitle">
          <span>DIAGNOSTIC TRANSITION INTELLIGENCE</span>
          <h2>What is changing now</h2>
        </div>
        <span className="methodBadge"><Radar size={12} /> REPLAY-DERIVED</span>
      </div>

      <p className="muted transitionPolicy">
        Transition signals summarize changes in model hypotheses across the current run replay.
        They are prioritization heuristics from observable model outputs—not failure ground truth,
        not calibrated risk, feature attribution, or causal proof.
      </p>

      {error && <div className="transitionError">{error}</div>}

      <div className="transitionMetricGrid">
        <TransitionMetric icon={<GitBranch />} label="Newly emerging" value={data?.summary.newlyEmerging ?? null} detail="latest anchor crossed healthy → non-healthy" />
        <TransitionMetric icon={<Radar />} label="Emergence observed" value={data?.summary.emergenceObserved ?? null} detail="historical healthy → non-healthy transition in replay" />
        <TransitionMetric icon={<Activity />} label="Historical transitions" value={data?.summary.historicalTransitions ?? null} detail="one or more top-class changes across persisted replay" />
        <TransitionMetric icon={<TrendingUp />} label="Escalating" value={data?.summary.escalating ?? null} detail={`≥ ${signedPct(data?.thresholds.escalationPer1kMiles)} / 1k mi`} />
        <TransitionMetric icon={<Activity />} label="Recent transitions" value={data?.summary.recentTransitions ?? null} detail={`within last ${data?.thresholds.recentWindowPoints ?? 5} replay anchors`} />
        <TransitionMetric icon={<Gauge />} label="Persistent" value={data?.summary.persistent ?? null} detail={`≥ ${pct(data?.thresholds.stableFraction ?? 0.8, 0)} recent class stability`} />
      </div>

      <div className="transitionBody">
        <div className="transitionQueue">
          <div className="transitionQueueHeader">
            <div><span>ATTENTION QUEUE</span><b>Model-output changes worth reviewing</b></div>
            <small>{data?.summary.vehiclesAnalyzed ?? '—'} replayed vehicles analyzed</small>
          </div>

          {strongest.length === 0 ? (
            <div className="transitionEmpty">No current transition signals exceed the display threshold.</div>
          ) : strongest.map(vehicle => (
            <button
              key={vehicle.vehicleId}
              className={selectedVehicleId === vehicle.vehicleId ? 'transitionRow selected' : 'transitionRow'}
              onClick={() => onSelectVehicle(vehicle.vehicleId)}
            >
              <span className={`diagnosticClassDot class-${vehicle.latestClass}`} />
              <div className="transitionVehicle">
                <b>{vehicle.vehicleId}</b>
                <span>{classLabels[vehicle.latestClass] ?? humanize(vehicle.latestClass)}</span>
              </div>
              <div className={`transitionTier tier-${vehicle.attentionTier}`}>{humanize(vehicle.attentionTier)}</div>
              <div className="transitionConfidence">
                <strong>{pct(vehicle.latestConfidence)}</strong>
                <span>{vehicle.attentionReason}</span>
              </div>
              <ArrowRight size={14} />
            </button>
          ))}
        </div>

        <div className="transitionMethod">
          <span className="diagnosticSectionLabel">PREDECLARED TRANSITION RULES</span>
          <div><b>Recent window</b><span>{data?.thresholds.recentWindowPoints ?? 5} replay anchors</span></div>
          <div><b>Escalating</b><span>current-class confidence slope ≥ {signedPct(data?.thresholds.escalationPer1kMiles ?? 0.01)} / 1k mi</span></div>
          <div><b>Stable</b><span>latest class occupies ≥ {pct(data?.thresholds.stableFraction ?? 0.8, 0)} of recent anchors</span></div>
          <div><b>Volatile</b><span>stability &lt; {pct(data?.thresholds.volatileFraction ?? 0.6, 0)} or ≥ {data?.thresholds.volatileClassChanges ?? 3} total class changes</span></div>
          <div><b>Scope</b><span>current experiment + current diagnostic run only</span></div>
        </div>
      </div>

      {selectedVehicleId && data && (
        <VehicleTransitionDetail vehicle={data.vehicles.find(item => item.vehicleId === selectedVehicleId) ?? null} />
      )}
    </section>
  );
}

function TransitionMetric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: number | null; detail: string }) {
  return (
    <div className="transitionMetric">
      <div>{icon}</div><span>{label}</span><strong>{value ?? '—'}</strong><small>{detail}</small>
    </div>
  );
}

function VehicleTransitionDetail({ vehicle }: { vehicle: TransitionVehicle | null }) {
  if (!vehicle) return null;
  return (
    <div className="transitionSelectedDetail">
      <div className="transitionSelectedTitle">
        <div><span>SELECTED VEHICLE TRANSITION</span><b>{vehicle.vehicleId}</b></div>
        <div><strong>{classLabels[vehicle.latestClass] ?? humanize(vehicle.latestClass)}</strong><span>{pct(vehicle.latestConfidence)} latest confidence</span></div>
      </div>
      <div className="transitionSelectedGrid">
        <div><span>Recent stability</span><b>{pct(vehicle.recentStability)}</b></div>
        <div><span>Class changes</span><b>{vehicle.classChanges}</b></div>
        <div><span>Current-class slope</span><b>{signedPct(vehicle.currentClassConfidenceSlopePer1kMiles)} / 1k mi</b></div>
        <div><span>Recent confidence change</span><b>{signedPct(vehicle.currentClassConfidenceDelta)}</b></div>
        <div><span>First observed emergence</span><b>{vehicle.firstEmergenceMileage == null ? '—' : miles(vehicle.firstEmergenceMileage)}</b></div>
        <div><span>Miles since emergence</span><b>{vehicle.milesSinceEmergence == null ? '—' : miles(vehicle.milesSinceEmergence)}</b></div>
        <div><span>Replay start</span><b>{miles(vehicle.firstAnchorMileage)}</b></div>
        <div><span>Latest anchor</span><b>{miles(vehicle.latestAnchorMileage)}</b></div>
      </div>
      <div className="transitionFlags">
        {vehicle.newlyEmerging && <span><GitBranch size={11} /> newly emerging</span>}
        {vehicle.emergenceObserved && <span><Radar size={11} /> emergence observed</span>}
        {vehicle.escalating && <span><TrendingUp size={11} /> escalating</span>}
        {vehicle.deescalating && <span><TrendingDown size={11} /> de-escalating</span>}
        {vehicle.volatile && <span><Activity size={11} /> volatile</span>}
        {vehicle.persistent && <span><Gauge size={11} /> persistent</span>}
      </div>
    </div>
  );
}
