import { useEffect, useMemo, useState } from 'react';
import {
  ArrowRight,
  CircleDot,
  Layers3,
  Radio,
  ShieldCheck,
} from 'lucide-react';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

type Episode = {
  id: number;
  runId: number;
  experimentId: string;
  rulesVersion: string;
  sourceEventRulesVersion: string;
  vehicleId: string;
  hypothesisClass: string;
  state: string;
  startReason: string;
  startTimestamp: string;
  startMileage: number;
  endTimestamp: string;
  endMileage: number;
  observedSpanMiles: number;
  isOpen: boolean;
  leftCensored: boolean;
  eventCount: number;
  escalationCount: number;
  deescalationCount: number;
  classChangeCount: number;
  stabilizedCount: number;
  destabilizedCount: number;
  peakConfidence: number | null;
  latestConfidence: number | null;
};

type EpisodeFeed = {
  runId: number;
  experimentId: string;
  lineage: string;
  champion: string | null;
  totalMatched: number;
  returned: number;
  episodes: Episode[];
};

type EpisodeSummary = {
  runId: number;
  experimentId: string;
  lineage: string;
  champion: string | null;
  rulesVersion: string | null;
  sourceEventRulesVersion: string | null;
  totalEpisodes: number;
  vehiclesWithEpisodes: number;
  openEpisodes: number;
  closedEpisodes: number;
  leftCensoredEpisodes: number;
  byState: Array<{
    state: string;
    episodes: number;
    vehicles: number;
  }>;
};

const STATES = [
  '',
  'EMERGING',
  'EVOLVING',
  'STABILIZED',
  'DESTABILIZED',
  'RESOLVED',
  'SUPERSEDED',
];

const CLASSES = [
  '',
  'coolant_pump',
  'battery_pack',
  'inverter',
  'traction_motor',
  'coolant_temp_sensor',
];

const classLabels: Record<string, string> = {
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
  return `${new Intl.NumberFormat('en-US', {
    maximumFractionDigits: 0,
  }).format(value)} mi`;
}

async function fetchJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${url}`);
  }
  return response.json() as Promise<T>;
}

export function DiagnosticEpisodeIntelligence({
  selectedVehicleId,
  onSelectVehicle,
  runId,
}: {
  selectedVehicleId: string | null;
  onSelectVehicle: (vehicleId: string) => void;
  runId?: number;
}) {
  const [summary, setSummary] = useState<EpisodeSummary | null>(null);
  const [feed, setFeed] = useState<EpisodeFeed | null>(null);
  const [stateFilter, setStateFilter] = useState('');
  const [classFilter, setClassFilter] = useState('');
  const [openOnly, setOpenOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let timerId: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;

    async function refresh() {
      if (!alive) return;
      controller = new AbortController();

      const params = new URLSearchParams({ limit: '80' });
      if (stateFilter) params.set('state', stateFilter);
      if (classFilter) params.set('hypothesis_class', classFilter);
      if (openOnly) params.set('open_only', 'true');

      try {
        const [nextSummary, nextFeed] = await Promise.all([
          fetchJson<EpisodeSummary>(
            `${API}/api/v1/diagnostics/episodes/summary`,
            controller.signal,
          ),
          fetchJson<EpisodeFeed>(
            `${API}/api/v1/diagnostics/episodes?${params.toString()}`,
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
          console.error('Diagnostic episode intelligence refresh failed:', refreshError);
          setError(
            refreshError instanceof Error
              ? refreshError.message
              : 'Diagnostic episode intelligence unavailable',
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
  }, [runId, stateFilter, classFilter, openOnly]);

  const stateMap = useMemo(
    () => new Map(
      (summary?.byState ?? []).map(item => [item.state, item.episodes]),
    ),
    [summary],
  );

  const selectedEpisode = useMemo(
    () => feed?.episodes.find(
      episode => episode.vehicleId === selectedVehicleId,
    ) ?? null,
    [feed, selectedVehicleId],
  );

  return (
    <section className="panel diagnosticEpisodePanel">
      <div className="panelTitleRow">
        <div className="panelTitle">
          <span>DIAGNOSTIC EPISODE INTELLIGENCE</span>
          <h2>Grouped model-hypothesis evolution</h2>
        </div>
        <span className="methodBadge">
          <Layers3 size={12} /> EVENT-DERIVED
        </span>
      </div>

      <p className="muted diagnosticEpisodePolicy">
        Episodes group persisted diagnostic events into observed periods of one
        non-healthy model hypothesis. They are not physical degradation or
        failure intervals, not calibrated risk, and not causal proof.
      </p>

      {error && <div className="diagnosticEpisodeError">{error}</div>}

      <div className="diagnosticEpisodeMetrics">
        <div><span>Total episodes</span><b>{summary?.totalEpisodes ?? '—'}</b></div>
        <div><span>Vehicles</span><b>{summary?.vehiclesWithEpisodes ?? '—'}</b></div>
        <div><span>Open</span><b>{summary?.openEpisodes ?? '—'}</b></div>
        <div><span>Resolved</span><b>{stateMap.get('RESOLVED') ?? 0}</b></div>
        <div><span>Superseded</span><b>{stateMap.get('SUPERSEDED') ?? 0}</b></div>
        <div><span>Left-censored</span><b>{summary?.leftCensoredEpisodes ?? '—'}</b></div>
      </div>

      <div className="diagnosticEpisodeFilters">
        <label>
          <span>Episode state</span>
          <select value={stateFilter} onChange={event => setStateFilter(event.currentTarget.value)}>
            {STATES.map(value => (
              <option key={value || 'all'} value={value}>
                {value ? humanize(value) : 'All states'}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Hypothesis class</span>
          <select value={classFilter} onChange={event => setClassFilter(event.currentTarget.value)}>
            {CLASSES.map(value => (
              <option key={value || 'all'} value={value}>
                {value ? classLabels[value] : 'All classes'}
              </option>
            ))}
          </select>
        </label>

        <label className="diagnosticEpisodeCheck">
          <input
            type="checkbox"
            checked={openOnly}
            onChange={event => setOpenOnly(event.currentTarget.checked)}
          />
          <span>Open only</span>
        </label>

        <div className="diagnosticEpisodeFilterMeta">
          <Radio size={12} />
          <span>{feed?.totalMatched ?? 0} matching · showing {feed?.returned ?? 0}</span>
        </div>
      </div>

      <div className="diagnosticEpisodeList">
        {(feed?.episodes ?? []).length === 0 ? (
          <div className="diagnosticEpisodeEmpty">
            No persisted diagnostic episodes match these filters.
          </div>
        ) : (
          feed!.episodes.map(episode => (
            <button
              key={episode.id}
              className={
                selectedVehicleId === episode.vehicleId
                  ? 'diagnosticEpisodeRow selected'
                  : 'diagnosticEpisodeRow'
              }
              onClick={() => onSelectVehicle(episode.vehicleId)}
            >
              <span className={`diagnosticClassDot class-${episode.hypothesisClass}`} />
              <div className="diagnosticEpisodeIdentity">
                <b>{episode.vehicleId}</b>
                <span>{classLabels[episode.hypothesisClass] ?? humanize(episode.hypothesisClass)}</span>
              </div>
              <div className={`diagnosticEpisodeState state-${episode.state}`}>
                <CircleDot size={10} /> {humanize(episode.state)}
              </div>
              <div className="diagnosticEpisodeSpan">
                <span>{miles(episode.startMileage)}</span>
                <ArrowRight size={11} />
                <b>{miles(episode.endMileage)}</b>
              </div>
              <div className="diagnosticEpisodeEventCount">
                <b>{episode.eventCount}</b><span>events</span>
              </div>
              <div className="diagnosticEpisodeConfidence">
                <b>{pct(episode.peakConfidence)}</b><span>peak</span>
              </div>
              <ArrowRight size={13} />
            </button>
          ))
        )}
      </div>

      {selectedEpisode && (
        <div className="diagnosticEpisodeSelected">
          <div>
            <span>SELECTED VEHICLE EPISODE</span>
            <b>
              {selectedEpisode.vehicleId} ·{' '}
              {classLabels[selectedEpisode.hypothesisClass] ?? humanize(selectedEpisode.hypothesisClass)}
            </b>
          </div>
          <div className="diagnosticEpisodeSelectedGrid">
            <div><span>State</span><b>{humanize(selectedEpisode.state)}</b></div>
            <div><span>Observed event span</span><b>{miles(selectedEpisode.observedSpanMiles)}</b></div>
            <div><span>Peak confidence</span><b>{pct(selectedEpisode.peakConfidence)}</b></div>
            <div><span>Latest confidence</span><b>{pct(selectedEpisode.latestConfidence)}</b></div>
            <div><span>Escalations</span><b>{selectedEpisode.escalationCount}</b></div>
            <div><span>De-escalations</span><b>{selectedEpisode.deescalationCount}</b></div>
            <div><span>Class changes</span><b>{selectedEpisode.classChangeCount}</b></div>
            <div>
              <span>Start visibility</span>
              <b>{selectedEpisode.leftCensored ? 'Observed in progress' : humanize(selectedEpisode.startReason)}</b>
            </div>
          </div>
        </div>
      )}

      <div className="diagnosticEpisodeFooter">
        <span><ShieldCheck size={11} /> Rules {summary?.rulesVersion ?? '—'}</span>
        <span>Source events {summary?.sourceEventRulesVersion ?? '—'}</span>
      </div>
    </section>
  );
}
