import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  CalendarClock,
  Gauge,
  History,
  LineChart,
  Save,
  Wrench,
} from 'lucide-react';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

type Summary = {
  runId: number;
  totalCases: number;
  eligibleTrajectories: number;
  escalatingTrajectories: number;
  experimentalHorizonsAvailable: number;
  plannedCases: number;
  byMaintenanceTier: Array<{ tier: string; cases: number }>;
  interpretationPolicy: string;
};

type Plan = {
  id: number;
  caseId: number;
  vehicleId: string;
  state: string;
  owner: string | null;
  targetMileage: number | null;
  note: string | null;
};

type QueueItem = {
  caseId: number;
  episodeId: number;
  vehicleId: string;
  hypothesisClass: string;
  caseStatus: string;
  reviewPriority: string;
  episodeState: string;
  watchlisted: boolean;
  trajectoryEligible: boolean;
  trajectoryPointCount: number;
  fit: {
    points: number;
    startMileage: number;
    latestMileage: number;
    latestConfidence: number;
    slopePer1kMiles: number;
    slopeStdErrorPer1kMiles: number;
    rSquared: number;
    observedSpanMiles: number;
  } | null;
  experimentalHorizon: {
    estimatedMilesToThreshold: number | null;
    lowerBandMiles: number | null;
    upperBandMiles: number | null;
    withinExperimentalWindow: boolean;
    thresholdAlreadyReached: boolean;
  } | null;
  priorityScore: number;
  maintenanceTier: string;
  recommendedReviewWindow: string;
  maintenancePlan: Plan | null;
};

type QueueResponse = {
  totalMatched: number;
  queue: QueueItem[];
  interpretationPolicy: string;
};

type PrognosticDetail = {
  targetHypothesisConfidence: number;
  prognostic: QueueItem & {
    trajectory: Array<{
      timestamp: string;
      mileage: number;
      confidence: number;
    }>;
  };
  interpretationPolicy: string;
};

type Backtest = {
  evaluatedCases: number;
  predictedCrossings: number;
  observedFutureCrossings: number;
  pairedCrossings: number;
  medianAbsoluteErrorMiles: number | null;
  meanAbsoluteErrorMiles: number | null;
  within2500Miles: number | null;
  byClass: Array<{
    hypothesisClass: string;
    evaluatedCases: number;
    pairedCrossings: number;
    medianAbsoluteErrorMiles: number | null;
  }>;
  interpretationPolicy: string;
};

type PlanDetail = {
  plan: Plan | null;
  activities: Array<{
    id: number;
    activityType: string;
    actor: string;
    fromValue: string | null;
    toValue: string | null;
    note: string | null;
    createdAt: string;
  }>;
};

type Props = {
  selectedVehicleId: string | null;
  onSelectVehicle: (vehicleId: string) => void;
  runId?: number;
};

const planStates = [
  'REVIEW',
  'PLANNED',
  'SCHEDULED',
  'DEFERRED',
  'COMPLETED',
];

function humanize(value: string | null | undefined) {
  if (!value) return '—';
  return value.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function pct(value: number | null | undefined) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`;
}

function miles(value: number | null | undefined) {
  if (value == null) return '—';
  return `${Math.round(value).toLocaleString()} mi`;
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

export function PrognosticMaintenanceIntelligence({
  selectedVehicleId,
  onSelectVehicle,
  runId,
}: Props) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [queue, setQueue] = useState<QueueResponse | null>(null);
  const [backtest, setBacktest] = useState<Backtest | null>(null);
  const [detail, setDetail] = useState<PrognosticDetail | null>(null);
  const [planDetail, setPlanDetail] = useState<PlanDetail | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);
  const [planState, setPlanState] = useState('REVIEW');
  const [owner, setOwner] = useState('');
  const [targetMileage, setTargetMileage] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);

  async function refreshBase() {
    const [nextSummary, nextQueue, nextBacktest] = await Promise.all([
      requestJson<Summary>(
        `${API}/api/v1/diagnostics/prognostics/summary`,
      ),
      requestJson<QueueResponse>(
        `${API}/api/v1/diagnostics/prognostics/queue?limit=50`,
      ),
      requestJson<Backtest>(
        `${API}/api/v1/diagnostics/prognostics/backtest`,
      ),
    ]);
    setSummary(nextSummary);
    setQueue(nextQueue);
    setBacktest(nextBacktest);

    setSelectedCaseId(current => {
      if (
        current &&
        nextQueue.queue.some(item => item.caseId === current)
      ) {
        return current;
      }
      const selected = nextQueue.queue.find(
        item => item.vehicleId === selectedVehicleId,
      );
      return selected?.caseId ?? nextQueue.queue[0]?.caseId ?? null;
    });
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
              : 'Prognostic API unavailable',
          );
        }
      } finally {
        if (alive) timer = setTimeout(cycle, 12000);
      }
    };

    void cycle();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [runId, selectedVehicleId]);

  useEffect(() => {
    if (!selectedCaseId) {
      setDetail(null);
      setPlanDetail(null);
      return;
    }

    let alive = true;
    Promise.all([
      requestJson<PrognosticDetail>(
        `${API}/api/v1/diagnostics/prognostics/cases/${selectedCaseId}`,
      ),
      requestJson<PlanDetail>(
        `${API}/api/v1/diagnostics/maintenance/plans/${selectedCaseId}`,
      ),
    ])
      .then(([nextDetail, nextPlan]) => {
        if (!alive) return;
        setDetail(nextDetail);
        setPlanDetail(nextPlan);
        const plan = nextPlan.plan;
        setPlanState(plan?.state ?? 'REVIEW');
        setOwner(plan?.owner ?? '');
        setTargetMileage(
          plan?.targetMileage != null
            ? String(plan.targetMileage)
            : '',
        );
        setNote('');
      })
      .catch(detailError => {
        if (alive) {
          setError(
            detailError instanceof Error
              ? detailError.message
              : 'Prognostic detail unavailable',
          );
        }
      });

    return () => {
      alive = false;
    };
  }, [selectedCaseId, runId]);

  useEffect(() => {
    if (!selectedVehicleId || !queue?.queue.length) return;
    const match = queue.queue.find(
      item => item.vehicleId === selectedVehicleId,
    );
    if (match) setSelectedCaseId(match.caseId);
  }, [selectedVehicleId, queue]);

  const tierMap = useMemo(
    () =>
      new Map(
        (summary?.byMaintenanceTier ?? []).map(
          item => [item.tier, item.cases],
        ),
      ),
    [summary],
  );

  async function savePlan() {
    if (!selectedCaseId) return;

    const next = await requestJson<{
      plan: Plan;
      activities: PlanDetail['activities'];
    }>(
      `${API}/api/v1/diagnostics/maintenance/plans/${selectedCaseId}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          state: planState,
          owner: owner.trim() || null,
          clear_owner: !owner.trim(),
          target_mileage: targetMileage
            ? Number(targetMileage)
            : null,
          clear_target_mileage: !targetMileage,
          note: note.trim() || null,
          actor: 'dashboard_operator',
        }),
      },
    );

    setPlanDetail({
      plan: next.plan,
      activities: next.activities,
    });
    setNote('');
    await refreshBase();
  }

  const selected = detail?.prognostic ?? null;

  return (
    <section className="panel prognosticPanel">
      <div className="panelTitleRow">
        <div className="panelTitle">
          <span>PROGNOSTICS & MAINTENANCE INTELLIGENCE</span>
          <h2>Run-frozen trajectories, experimental horizons & service planning</h2>
        </div>
        <span className="methodBadge">
          REPLAY-ONLY · NO FAILURE TRUTH · NOT PHYSICAL RUL
        </span>
      </div>

      <p className="muted prognosticPolicy">
        Horizons extrapolate model-hypothesis confidence toward a configured
        model threshold. They are experimental investigation signals, not
        physical remaining useful life, failure-time estimates, calibrated
        failure risk, attribution or causal proof.
      </p>

      {error && <div className="diagnosticError">{error}</div>}

      <div className="prognosticMetrics">
        <Metric
          label="Eligible trajectories"
          value={summary?.eligibleTrajectories ?? 0}
          detail={`${summary?.totalCases ?? 0} cases`}
        />
        <Metric
          label="Escalating"
          value={summary?.escalatingTrajectories ?? 0}
          detail="positive fitted slope"
        />
        <Metric
          label="Experimental horizons"
          value={summary?.experimentalHorizonsAvailable ?? 0}
          detail="threshold estimate available"
        />
        <Metric
          label="Planned"
          value={summary?.plannedCases ?? 0}
          detail="operator maintenance plans"
        />
      </div>

      <div className="prognosticTierStrip">
        {['URGENT_REVIEW', 'PLAN_SERVICE', 'MONITOR', 'ROUTINE_REVIEW'].map(
          tier => (
            <div key={tier}>
              <span>{humanize(tier)}</span>
              <strong>{tierMap.get(tier) ?? 0}</strong>
            </div>
          ),
        )}
      </div>

      <div className="prognosticGrid">
        <div className="prognosticCard">
          <div className="prognosticCardTitle">
            <Wrench size={15} />
            <div>
              <span>MAINTENANCE PRIORITY QUEUE</span>
              <b>Deterministic operational review ordering</b>
            </div>
          </div>

          <div className="prognosticQueue">
            {(queue?.queue ?? []).slice(0, 18).map(item => (
              <button
                key={item.caseId}
                className={
                  selectedCaseId === item.caseId ? 'selected' : ''
                }
                onClick={() => {
                  setSelectedCaseId(item.caseId);
                  onSelectVehicle(item.vehicleId);
                }}
              >
                <div>
                  <b>{item.vehicleId}</b>
                  <span>
                    {humanize(item.hypothesisClass)} ·{' '}
                    {humanize(item.maintenanceTier)}
                  </span>
                  <small>
                    {humanize(item.recommendedReviewWindow)} ·{' '}
                    {item.trajectoryPointCount} replay points
                  </small>
                </div>
                <div>
                  <strong>{item.priorityScore.toFixed(1)}</strong>
                  <span>{pct(item.fit?.latestConfidence)}</span>
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="prognosticCard">
          <div className="prognosticCardTitle">
            <LineChart size={15} />
            <div>
              <span>HYPOTHESIS TRAJECTORY</span>
              <b>
                {selected
                  ? `${selected.vehicleId} · ${humanize(
                      selected.hypothesisClass,
                    )}`
                  : 'Select a queue item'}
              </b>
            </div>
          </div>

          {selected ? (
            <>
              <TrajectoryChart
                points={selected.trajectory}
                threshold={detail?.targetHypothesisConfidence ?? 0.95}
              />

              <div className="prognosticStatGrid">
                <Stat
                  label="Latest confidence"
                  value={pct(selected.fit?.latestConfidence)}
                />
                <Stat
                  label="Slope / 1k mi"
                  value={
                    selected.fit
                      ? selected.fit.slopePer1kMiles.toFixed(4)
                      : '—'
                  }
                />
                <Stat
                  label="Fit R²"
                  value={
                    selected.fit
                      ? selected.fit.rSquared.toFixed(3)
                      : '—'
                  }
                />
                <Stat
                  label="Observed span"
                  value={miles(selected.fit?.observedSpanMiles)}
                />
              </div>

              <div className="prognosticHorizon">
                <div>
                  <span>Experimental miles to 95% model confidence</span>
                  <strong>
                    {miles(
                      selected.experimentalHorizon
                        ?.estimatedMilesToThreshold,
                    )}
                  </strong>
                </div>
                <div>
                  <span>Uncalibrated fit band</span>
                  <b>
                    {miles(
                      selected.experimentalHorizon?.lowerBandMiles,
                    )}{' '}
                    –{' '}
                    {miles(
                      selected.experimentalHorizon?.upperBandMiles,
                    )}
                  </b>
                </div>
              </div>
            </>
          ) : (
            <div className="prognosticEmpty">
              Select a maintenance queue item.
            </div>
          )}
        </div>
      </div>

      <div className="prognosticGrid lower">
        <div className="prognosticCard">
          <div className="prognosticCardTitle">
            <History size={15} />
            <div>
              <span>THRESHOLD-HORIZON BACKTEST</span>
              <b>Earlier replay fit vs later model-threshold crossing</b>
            </div>
          </div>

          <div className="prognosticBacktestHero">
            <div>
              <span>Evaluated cases</span>
              <strong>{backtest?.evaluatedCases ?? 0}</strong>
            </div>
            <div>
              <span>Paired crossings</span>
              <strong>{backtest?.pairedCrossings ?? 0}</strong>
            </div>
            <div>
              <span>Median abs. error</span>
              <strong>{miles(backtest?.medianAbsoluteErrorMiles)}</strong>
            </div>
            <div>
              <span>Within 2,500 mi</span>
              <strong>{pct(backtest?.within2500Miles)}</strong>
            </div>
          </div>

          <div className="prognosticBacktestRows">
            {(backtest?.byClass ?? []).map(row => (
              <div key={row.hypothesisClass}>
                <b>{humanize(row.hypothesisClass)}</b>
                <span>{row.evaluatedCases} evaluated</span>
                <span>{row.pairedCrossings} paired</span>
                <strong>
                  {miles(row.medianAbsoluteErrorMiles)}
                </strong>
              </div>
            ))}
          </div>

          <p className="muted prognosticFootnote">
            Backtest target is a future crossing of the same model-confidence
            threshold — never a hidden physical failure marker.
          </p>
        </div>

        <div className="prognosticCard">
          <div className="prognosticCardTitle">
            <CalendarClock size={15} />
            <div>
              <span>SERVICE PLANNING</span>
              <b>Operator-owned maintenance workflow</b>
            </div>
          </div>

          {selectedCaseId ? (
            <>
              <div className="maintenanceComposer">
                <label>
                  <span>State</span>
                  <select
                    value={planState}
                    onChange={event => setPlanState(event.target.value)}
                  >
                    {planStates.map(state => (
                      <option key={state} value={state}>
                        {humanize(state)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Owner</span>
                  <input
                    value={owner}
                    onChange={event => setOwner(event.target.value)}
                    placeholder="operator / service team"
                  />
                </label>
                <label>
                  <span>Target mileage</span>
                  <input
                    type="number"
                    min="0"
                    value={targetMileage}
                    onChange={event =>
                      setTargetMileage(event.target.value)
                    }
                    placeholder="optional"
                  />
                </label>
                <label className="wide">
                  <span>Planning note</span>
                  <textarea
                    value={note}
                    onChange={event => setNote(event.target.value)}
                    placeholder="Operational note; do not state unverified physical failure conclusions."
                    maxLength={2000}
                  />
                </label>
                <button onClick={() => void savePlan()}>
                  <Save size={13} />
                  Save maintenance plan
                </button>
              </div>

              <div className="maintenancePlanSnapshot">
                <Gauge size={14} />
                <div>
                  <span>Current plan</span>
                  <b>
                    {humanize(planDetail?.plan?.state ?? 'not created')}
                  </b>
                </div>
                <div>
                  <span>Owner</span>
                  <b>{planDetail?.plan?.owner ?? '—'}</b>
                </div>
                <div>
                  <span>Target</span>
                  <b>{miles(planDetail?.plan?.targetMileage)}</b>
                </div>
              </div>

              <div className="maintenanceActivity">
                {(planDetail?.activities ?? []).slice(0, 8).map(item => (
                  <div key={item.id}>
                    <Activity size={11} />
                    <div>
                      <b>{humanize(item.activityType)}</b>
                      <span>
                        {item.actor}
                        {item.fromValue || item.toValue
                          ? ` · ${item.fromValue ?? '—'} → ${
                              item.toValue ?? '—'
                            }`
                          : ''}
                      </span>
                      {item.note && <small>{item.note}</small>}
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="prognosticEmpty">
              Select a case to create a maintenance plan.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: number;
  detail: string;
}) {
  return (
    <div className="prognosticMetric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function Stat({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div>
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

function TrajectoryChart({
  points,
  threshold,
}: {
  points: Array<{ mileage: number; confidence: number }>;
  threshold: number;
}) {
  if (points.length < 2) {
    return <div className="prognosticEmpty">Insufficient trajectory.</div>;
  }

  const width = 620;
  const height = 190;
  const pad = 22;
  const minMileage = points[0].mileage;
  const maxMileage = points[points.length - 1].mileage;
  const span = Math.max(1, maxMileage - minMileage);

  const chartPoints = points.map(point => {
    const x =
      pad +
      ((point.mileage - minMileage) / span) * (width - pad * 2);
    const y =
      height -
      pad -
      Math.max(0, Math.min(1, point.confidence)) *
        (height - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const thresholdY =
    height -
    pad -
    threshold * (height - pad * 2);

  return (
    <svg
      className="prognosticChart"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Model hypothesis confidence trajectory across replay mileage"
    >
      <line
        x1={pad}
        x2={width - pad}
        y1={thresholdY}
        y2={thresholdY}
        className="prognosticThreshold"
      />
      <polyline
        points={chartPoints.join(' ')}
        className="prognosticLine"
      />
      {chartPoints.map((point, index) => {
        const [cx, cy] = point.split(',');
        return (
          <circle
            key={`${point}-${index}`}
            cx={cx}
            cy={cy}
            r="2.3"
            className="prognosticPoint"
          />
        );
      })}
    </svg>
  );
}
