import { useEffect, useMemo, useState } from 'react';
import {
  Bookmark,
  Boxes,
  GitCompareArrows,
  Radar,
  Save,
  Star,
  Trash2,
} from 'lucide-react';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

type DimensionRow = {
  value: string;
  cases: number;
  vehicles: number;
  highPriorityCases: number;
  activeCases: number;
  averageLatestConfidence: number | null;
};

type PatternOverview = {
  runId: number;
  experimentId: string;
  rulesVersion: string;
  totalCases: number;
  casesWithTelemetryContext: number;
  dimensions: Record<string, DimensionRow[]>;
  topHotspots: Array<DimensionRow & { dimension: string }>;
  interpretationPolicy: string;
};

type Cluster = {
  clusterKey: string;
  hypothesisClass: string;
  firmware: string;
  factory: string;
  cases: number;
  vehicles: number;
  highPriorityCases: number;
  averageLatestConfidence: number | null;
  pumpRevisions: string[];
  models: string[];
  caseIds: number[];
  vehicleIds: string[];
};

type ClusterResponse = {
  totalClusters: number;
  clusters: Cluster[];
  interpretationPolicy: string;
};

type SimilarCase = {
  caseId: number;
  vehicleId: string;
  hypothesisClass: string;
  reviewPriority: string;
  status: string;
  episodeState: string;
  latestConfidence: number | null;
  firmware: string | null;
  factory: string | null;
  pumpRevision: string | null;
  model: string | null;
  similarityScore: number;
  matchedDimensions: string[];
};

type SimilarResponse = {
  target: { caseId: number; vehicleId: string };
  similarCases: SimilarCase[];
  interpretationPolicy: string;
};

type CaseLookup = {
  cases: Array<{ id: number; vehicleId: string }>;
};

type WatchlistEntry = {
  id: number;
  caseId: number;
  vehicleId: string;
  note: string | null;
  case: {
    hypothesisClass: string;
    reviewPriority: string;
    status: string;
  } | null;
};

type WatchlistResponse = {
  total: number;
  entries: WatchlistEntry[];
};

type InvestigationView = {
  id: number;
  name: string;
  filters: Record<string, unknown>;
};

type InvestigationViewsResponse = {
  total: number;
  views: InvestigationView[];
};

type Props = {
  selectedVehicleId: string | null;
  onSelectVehicle: (vehicleId: string) => void;
  runId?: number;
};

type Dimension =
  | 'hypothesisClass'
  | 'firmware'
  | 'factory'
  | 'pumpRevision'
  | 'model';

const dimensions: Array<{ key: Dimension; label: string }> = [
  { key: 'hypothesisClass', label: 'Hypothesis' },
  { key: 'firmware', label: 'Firmware' },
  { key: 'factory', label: 'Factory' },
  { key: 'pumpRevision', label: 'Pump revision' },
  { key: 'model', label: 'Vehicle model' },
];

const viewPresets = {
  'High priority': { reviewPriority: 'HIGH' },
  'Unassigned active': { unassignedOnly: true },
  'Investigating': { status: 'INVESTIGATING' },
  'Inverter cases': { hypothesisClass: 'inverter' },
};

function humanize(value: string | null | undefined) {
  if (!value) return '—';
  return value.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function pct(value: number | null | undefined) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`;
}

async function requestJson<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status}: ${body || url}`);
  }
  return response.json() as Promise<T>;
}

export function FleetPatternIntelligence({
  selectedVehicleId,
  onSelectVehicle,
  runId,
}: Props) {
  const [overview, setOverview] = useState<PatternOverview | null>(null);
  const [clusters, setClusters] = useState<ClusterResponse | null>(null);
  const [similar, setSimilar] = useState<SimilarResponse | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistResponse | null>(null);
  const [views, setViews] = useState<InvestigationViewsResponse | null>(null);
  const [dimension, setDimension] = useState<Dimension>('hypothesisClass');
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);
  const [viewName, setViewName] = useState('High priority');
  const [viewPreset, setViewPreset] =
    useState<keyof typeof viewPresets>('High priority');
  const [error, setError] = useState<string | null>(null);

  async function refreshBase() {
    const [nextOverview, nextClusters, nextWatchlist, nextViews] =
      await Promise.all([
        requestJson<PatternOverview>(
          `${API}/api/v1/diagnostics/patterns/overview`,
        ),
        requestJson<ClusterResponse>(
          `${API}/api/v1/diagnostics/patterns/clusters?min_cases=2&limit=20`,
        ),
        requestJson<WatchlistResponse>(
          `${API}/api/v1/diagnostics/watchlist`,
        ),
        requestJson<InvestigationViewsResponse>(
          `${API}/api/v1/diagnostics/investigation-views`,
        ),
      ]);
    setOverview(nextOverview);
    setClusters(nextClusters);
    setWatchlist(nextWatchlist);
    setViews(nextViews);
  }

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const cycle = async () => {
      try {
        await refreshBase();
        if (alive) setError(null);
      } catch (refreshError) {
        if (alive) {
          setError(
            refreshError instanceof Error
              ? refreshError.message
              : 'Pattern API unavailable',
          );
        }
      } finally {
        if (alive) timer = setTimeout(cycle, 10000);
      }
    };

    void cycle();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [runId]);

  useEffect(() => {
    if (!selectedVehicleId) {
      setSelectedCaseId(null);
      setSimilar(null);
      return;
    }

    let alive = true;
    requestJson<CaseLookup>(
      `${API}/api/v1/diagnostics/cases?vehicle_id=${encodeURIComponent(
        selectedVehicleId,
      )}&limit=1`,
    )
      .then(async result => {
        if (!alive) return;
        const caseId = result.cases[0]?.id ?? null;
        setSelectedCaseId(caseId);
        if (!caseId) {
          setSimilar(null);
          return;
        }
        const next = await requestJson<SimilarResponse>(
          `${API}/api/v1/diagnostics/patterns/similar/${caseId}?limit=8&min_score=0.20`,
        );
        if (alive) setSimilar(next);
      })
      .catch(lookupError => {
        if (alive) {
          setError(
            lookupError instanceof Error
              ? lookupError.message
              : 'Similarity lookup failed',
          );
        }
      });

    return () => {
      alive = false;
    };
  }, [selectedVehicleId, runId]);

  const dimensionRows = useMemo(
    () => overview?.dimensions[dimension] ?? [],
    [overview, dimension],
  );

  const watched = selectedCaseId
    ? watchlist?.entries.some(item => item.caseId === selectedCaseId) ?? false
    : false;

  async function toggleWatchlist() {
    if (!selectedCaseId) return;
    if (watched) {
      await requestJson(
        `${API}/api/v1/diagnostics/watchlist/${selectedCaseId}`,
        { method: 'DELETE' },
      );
    } else {
      await requestJson(
        `${API}/api/v1/diagnostics/watchlist/${selectedCaseId}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            actor: 'dashboard_operator',
            note: 'Added from Fleet Pattern Intelligence',
          }),
        },
      );
    }
    await refreshBase();
  }

  async function saveView() {
    const name = viewName.trim();
    if (!name) return;
    await requestJson(
      `${API}/api/v1/diagnostics/investigation-views`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          actor: 'dashboard_operator',
          name,
          filters: viewPresets[viewPreset],
        }),
      },
    );
    await refreshBase();
  }

  async function deleteView(viewId: number) {
    await requestJson(
      `${API}/api/v1/diagnostics/investigation-views/${viewId}`,
      { method: 'DELETE' },
    );
    await refreshBase();
  }

  return (
    <section className="panel fleetPatternPanel">
      <div className="panelTitleRow">
        <div className="panelTitle">
          <span>FLEET PATTERN INTELLIGENCE</span>
          <h2>Cross-case hotspots, clusters & investigation memory</h2>
        </div>
        <span className="methodBadge">
          DESCRIPTIVE · CURRENT RUN · OBSERVED CONTEXT
        </span>
      </div>

      <p className="muted fleetPatternPolicy">
        Fleet patterns summarize current-run case concentration and observable
        vehicle context. Hotspots, clusters and similarity are investigation
        shortcuts — not failure enrichment, attribution or causal proof.
      </p>

      {error && <div className="diagnosticError">{error}</div>}

      <div className="fleetPatternMetrics">
        <PatternMetric label="Cases" value={overview?.totalCases ?? 0} />
        <PatternMetric
          label="Context linked"
          value={overview?.casesWithTelemetryContext ?? 0}
        />
        <PatternMetric
          label="Clusters"
          value={clusters?.totalClusters ?? 0}
        />
        <PatternMetric
          label="Watchlist"
          value={watchlist?.total ?? 0}
        />
      </div>

      <div className="fleetPatternGrid">
        <div className="fleetPatternCard">
          <div className="fleetPatternCardTitle">
            <Radar size={15} />
            <div>
              <span>HOTSPOT EXPLORER</span>
              <b>Case concentration by dimension</b>
            </div>
          </div>

          <div className="fleetPatternDimensionTabs">
            {dimensions.map(item => (
              <button
                key={item.key}
                className={dimension === item.key ? 'active' : ''}
                onClick={() => setDimension(item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>

          <div className="fleetPatternRows">
            {dimensionRows.slice(0, 8).map(row => (
              <div className="fleetPatternRow" key={row.value}>
                <div>
                  <b>{humanize(row.value)}</b>
                  <span>
                    {row.vehicles} vehicles · {row.highPriorityCases} high
                  </span>
                </div>
                <div>
                  <strong>{row.cases}</strong>
                  <span>{pct(row.averageLatestConfidence)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="fleetPatternCard">
          <div className="fleetPatternCardTitle">
            <Boxes size={15} />
            <div>
              <span>RECURRING PATTERNS</span>
              <b>Hypothesis × firmware × factory clusters</b>
            </div>
          </div>

          <div className="fleetClusterRows">
            {(clusters?.clusters ?? []).slice(0, 8).map(cluster => (
              <button
                key={cluster.clusterKey}
                onClick={() => {
                  const vehicleId = cluster.vehicleIds[0];
                  if (vehicleId) onSelectVehicle(vehicleId);
                }}
              >
                <div>
                  <b>{humanize(cluster.hypothesisClass)}</b>
                  <span>
                    {cluster.firmware} · {cluster.factory}
                  </span>
                  <small>
                    {cluster.pumpRevisions.join(', ') || 'no pump revision'} ·{' '}
                    {cluster.models.join(', ') || 'no model'}
                  </small>
                </div>
                <div>
                  <strong>{cluster.cases}</strong>
                  <span>{cluster.highPriorityCases} high</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="fleetPatternGrid lower">
        <div className="fleetPatternCard">
          <div className="fleetPatternCardTitle">
            <GitCompareArrows size={15} />
            <div>
              <span>CASE SIMILARITY</span>
              <b>
                {selectedVehicleId
                  ? `Cases similar to ${selectedVehicleId}`
                  : 'Select a diagnostic case'}
              </b>
            </div>
            {selectedCaseId && (
              <button
                className={watched ? 'fleetWatchButton watched' : 'fleetWatchButton'}
                onClick={() => void toggleWatchlist()}
              >
                <Star size={13} />
                {watched ? 'Watching' : 'Watch'}
              </button>
            )}
          </div>

          <div className="fleetSimilarityRows">
            {(similar?.similarCases ?? []).map(item => (
              <button
                key={item.caseId}
                onClick={() => onSelectVehicle(item.vehicleId)}
              >
                <div>
                  <b>{item.vehicleId}</b>
                  <span>
                    {humanize(item.hypothesisClass)} · {item.firmware ?? '—'}
                  </span>
                  <small>
                    matches {item.matchedDimensions.map(humanize).join(', ')}
                  </small>
                </div>
                <div>
                  <strong>{pct(item.similarityScore)}</strong>
                  <span>{item.reviewPriority}</span>
                </div>
              </button>
            ))}
            {!selectedCaseId && (
              <div className="fleetPatternEmpty">
                Select a case above to compare its descriptive context.
              </div>
            )}
          </div>
        </div>

        <div className="fleetPatternCard">
          <div className="fleetPatternCardTitle">
            <Bookmark size={15} />
            <div>
              <span>INVESTIGATION MEMORY</span>
              <b>Watchlist & saved views</b>
            </div>
          </div>

          <div className="fleetSavedViewComposer">
            <input
              value={viewName}
              onChange={event => setViewName(event.target.value)}
              placeholder="View name"
              maxLength={96}
            />
            <select
              value={viewPreset}
              onChange={event => {
                const preset = event.target.value as keyof typeof viewPresets;
                setViewPreset(preset);
                setViewName(preset);
              }}
            >
              {Object.keys(viewPresets).map(name => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
            <button onClick={() => void saveView()}>
              <Save size={13} /> Save
            </button>
          </div>

          <div className="fleetSavedViews">
            {(views?.views ?? []).map(view => (
              <div key={view.id}>
                <div>
                  <b>{view.name}</b>
                  <span>{JSON.stringify(view.filters)}</span>
                </div>
                <button onClick={() => void deleteView(view.id)}>
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>

          <div className="fleetWatchlist">
            <span className="fleetPatternSubhead">WATCHED CASES</span>
            {(watchlist?.entries ?? []).slice(0, 6).map(entry => (
              <button
                key={entry.id}
                onClick={() => onSelectVehicle(entry.vehicleId)}
              >
                <Star size={12} />
                <div>
                  <b>{entry.vehicleId}</b>
                  <span>
                    {humanize(entry.case?.hypothesisClass)} ·{' '}
                    {entry.case?.reviewPriority ?? '—'}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function PatternMetric({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className="fleetPatternMetric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
