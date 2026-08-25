import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  ArrowRight,
  Clock3,
  GitBranch,
  Radio,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

type DiagnosticEvent = {
  id: number;
  runId: number;
  experimentId: string;
  rulesVersion: string;
  vehicleId: string;
  eventType: string;
  anchorTimestamp: string;
  anchorMileage: number;
  previousClass: string | null;
  currentClass: string | null;
  previousConfidence: number | null;
  currentConfidence: number | null;
  confidenceDelta: number | null;
  slopePer1kMiles: number | null;
  observableEvidence: Array<{
    feature: string;
    label: string;
    value: number;
    unit: string | null;
  }>;
  details: Record<string, unknown>;
};

type EventFeedResponse = {
  runId: number;
  experimentId: string;
  lineage: string;
  champion: string | null;
  totalMatched: number;
  returned: number;
  filters: {
    eventType: string | null;
    vehicleId: string | null;
    hypothesisClass: string | null;
    minConfidence: number | null;
  };
  events: DiagnosticEvent[];
  scopePolicy: {
    currentRunOnly: boolean;
    exactExperimentOnly: boolean;
    replayDerivedOnly: boolean;
    usesPrivateFailureTruth: boolean;
    failureMarkersExposed: boolean;
  };
  interpretationPolicy: string;
};

type EventSummary = {
  runId: number;
  experimentId: string;
  lineage: string;
  rulesVersion: string | null;
  totalEvents: number;
  vehiclesWithEvents: number;
  byType: Array<{
    eventType: string;
    events: number;
    vehicles: number;
  }>;
};

const EVENT_TYPES = [
  '',
  'HYPOTHESIS_EMERGED',
  'HYPOTHESIS_CHANGED',
  'CONFIDENCE_ESCALATED',
  'CONFIDENCE_DEESCALATED',
  'HYPOTHESIS_STABILIZED',
  'HYPOTHESIS_DESTABILIZED',
];

const CLASSES = [
  '',
  'healthy',
  'coolant_pump',
  'battery_pack',
  'inverter',
  'traction_motor',
  'coolant_temp_sensor',
];

const eventLabels: Record<string, string> = {
  HYPOTHESIS_EMERGED: 'Hypothesis emerged',
  HYPOTHESIS_CHANGED: 'Hypothesis changed',
  CONFIDENCE_ESCALATED: 'Confidence escalated',
  CONFIDENCE_DEESCALATED: 'Confidence de-escalated',
  HYPOTHESIS_STABILIZED: 'Hypothesis stabilized',
  HYPOTHESIS_DESTABILIZED: 'Hypothesis destabilized',
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

function signedPp(value: number | null | undefined, digits = 1) {
  if (value == null) return '—';
  const points = value * 100;
  return `${points >= 0 ? '+' : ''}${points.toFixed(digits)} pp`;
}

function miles(value: number | null | undefined) {
  if (value == null) return '—';
  return `${new Intl.NumberFormat('en-US', {
    maximumFractionDigits: 0,
  }).format(value)} mi`;
}

function timestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function EventIcon({ type }: { type: string }) {
  if (type === 'HYPOTHESIS_EMERGED' || type === 'HYPOTHESIS_CHANGED') {
    return <GitBranch size={13} />;
  }
  if (type === 'CONFIDENCE_ESCALATED') return <TrendingUp size={13} />;
  if (type === 'CONFIDENCE_DEESCALATED') return <TrendingDown size={13} />;
  return <Activity size={13} />;
}

async function fetchJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${url}`);
  }
  return response.json() as Promise<T>;
}

export function DiagnosticEventFeed({
  selectedVehicleId,
  onSelectVehicle,
  runId,
}: {
  selectedVehicleId: string | null;
  onSelectVehicle: (vehicleId: string) => void;
  runId?: number;
}) {
  const [summary, setSummary] = useState<EventSummary | null>(null);
  const [feed, setFeed] = useState<EventFeedResponse | null>(null);
  const [eventType, setEventType] = useState('');
  const [hypothesisClass, setHypothesisClass] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let timerId: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;

    async function refresh() {
      if (!alive) return;
      controller = new AbortController();

      const params = new URLSearchParams({ limit: '80' });
      if (eventType) params.set('event_type', eventType);
      if (hypothesisClass) params.set('hypothesis_class', hypothesisClass);

      try {
        const [nextSummary, nextFeed] = await Promise.all([
          fetchJson<EventSummary>(
            `${API}/api/v1/diagnostics/events/summary`,
            controller.signal,
          ),
          fetchJson<EventFeedResponse>(
            `${API}/api/v1/diagnostics/events?${params.toString()}`,
            controller.signal,
          ),
        ]);

        if (alive) {
          setSummary(nextSummary);
          setFeed(nextFeed);
          setError(null);
        }
      } catch (refreshError) {
        if (
          alive &&
          !(refreshError instanceof DOMException && refreshError.name === 'AbortError')
        ) {
          console.error('Diagnostic event feed refresh failed:', refreshError);
          setError(
            refreshError instanceof Error
              ? refreshError.message
              : 'Diagnostic event feed unavailable',
          );
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
  }, [runId, eventType, hypothesisClass]);

  const summaryMap = useMemo(
    () => new Map(
      (summary?.byType ?? []).map(item => [item.eventType, item.events]),
    ),
    [summary],
  );

  return (
    <section className="panel diagnosticEventPanel">
      <div className="panelTitleRow">
        <div className="panelTitle">
          <span>DIAGNOSTIC EVENT INTELLIGENCE</span>
          <h2>Observable model-event audit feed</h2>
        </div>
        <span className="methodBadge">
          <Clock3 size={12} />
          RUN {feed?.runId ?? runId ?? '—'}
        </span>
      </div>

      <p className="muted diagnosticEventPolicy">
        Events are deterministic state changes derived from persisted replayed
        model hypotheses. They are not physical failure events, not calibrated
        failure risk, private simulator truth, attribution, or causal proof.
      </p>

      {error && <div className="diagnosticEventError">{error}</div>}

      <div className="diagnosticEventMetrics">
        <div><span>Total events</span><b>{summary?.totalEvents ?? '—'}</b></div>
        <div><span>Vehicles with events</span><b>{summary?.vehiclesWithEvents ?? '—'}</b></div>
        <div><span>Emergence</span><b>{summaryMap.get('HYPOTHESIS_EMERGED') ?? 0}</b></div>
        <div><span>Class changes</span><b>{summaryMap.get('HYPOTHESIS_CHANGED') ?? 0}</b></div>
        <div><span>Escalations</span><b>{summaryMap.get('CONFIDENCE_ESCALATED') ?? 0}</b></div>
        <div><span>De-escalations</span><b>{summaryMap.get('CONFIDENCE_DEESCALATED') ?? 0}</b></div>
      </div>

      <div className="diagnosticEventFilters">
        <label>
          <span>Event type</span>
          <select value={eventType} onChange={event => setEventType(event.currentTarget.value)}>
            {EVENT_TYPES.map(value => (
              <option key={value || 'all'} value={value}>
                {value ? eventLabels[value] : 'All event types'}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Hypothesis class</span>
          <select value={hypothesisClass} onChange={event => setHypothesisClass(event.currentTarget.value)}>
            {CLASSES.map(value => (
              <option key={value || 'all'} value={value}>
                {value ? classLabels[value] : 'All classes'}
              </option>
            ))}
          </select>
        </label>
        <div className="diagnosticEventFilterMeta">
          <Radio size={12} />
          <span>{feed?.totalMatched ?? 0} matching · showing {feed?.returned ?? 0}</span>
        </div>
      </div>

      <div className="diagnosticEventList">
        {(feed?.events ?? []).length === 0 ? (
          <div className="diagnosticEventEmpty">
            No persisted diagnostic events match these filters.
          </div>
        ) : (
          feed!.events.map(event => (
            <button
              key={event.id}
              className={
                selectedVehicleId === event.vehicleId
                  ? 'diagnosticEventRow selected'
                  : 'diagnosticEventRow'
              }
              onClick={() => onSelectVehicle(event.vehicleId)}
            >
              <span className={`diagnosticEventIcon event-${event.eventType}`}>
                <EventIcon type={event.eventType} />
              </span>
              <div className="diagnosticEventIdentity">
                <b>{event.vehicleId}</b>
                <span>{timestamp(event.anchorTimestamp)}</span>
              </div>
              <div className="diagnosticEventType">
                <b>{eventLabels[event.eventType] ?? humanize(event.eventType)}</b>
                <span>{miles(event.anchorMileage)}</span>
              </div>
              <div className="diagnosticEventTransition">
                <span>{classLabels[event.previousClass ?? ''] ?? humanize(event.previousClass)}</span>
                <ArrowRight size={11} />
                <b>{classLabels[event.currentClass ?? ''] ?? humanize(event.currentClass)}</b>
              </div>
              <div className="diagnosticEventConfidence">
                <strong>{pct(event.currentConfidence)}</strong>
                <span>{signedPp(event.confidenceDelta)}</span>
              </div>
              <ArrowRight size={13} />
            </button>
          ))
        )}
      </div>

      <div className="diagnosticEventFooter">
        <span>Rules: {summary?.rulesVersion ?? '—'}</span>
        <span>Current run + exact experiment only · observable replay-derived</span>
      </div>
    </section>
  );
}
