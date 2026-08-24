import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Binary,
  ChevronRight,
  Cpu,
  Gauge,
  Radio,
  ShieldCheck,
  Sigma,
  Thermometer,
  TimerReset,
  TrendingDown,
  Wrench,
  Zap,
} from 'lucide-react';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

type Page = 'fleet' | 'reliability' | 'firmware';

type Summary = {
  vehiclesMonitored: number;
  telemetryEvents: number;
  activeAlerts: number;
  criticalAlerts: number;
  observedFailures: number;
  averageRisk: number;
  health: { healthy: number; degraded: number; critical: number };
};

type Alert = {
  id: number;
  createdAt: string;
  vehicleId: string;
  severity: string;
  riskScore: number;
  title: string;
  evidence: string[];
  firmware: string;
  pumpRevision: string;
  factory: string;
};

type Cohort = {
  pumpRevision: string;
  samples: number;
  averageRisk: number;
  averagePumpCurrentA: number;
};

type KaplanMeierPoint = {
  mileage: number;
  survival: number;
  atRisk: number;
  failures: number;
  censored: number;
};

type Weibull = {
  beta: number;
  etaMiles: number;
  b10Miles: number;
  b50Miles: number;
  failureBehavior: string;
  reliability: Record<string, number>;
};

type ReliabilityCohort = {
  pumpRevision: string;
  population: number;
  failures: number;
  censored: number;
  failureRate: number;
  weibull: Weibull | null;
  earlyWarning: {
    failuresEvaluated: number;
    detectedBeforeFailure: number;
    detectionRate: number | null;
    medianLeadMiles: number | null;
    medianLeadSeconds: number | null;
    medianLeadSimulatedDays: number | null;
  };
  kaplanMeier: KaplanMeierPoint[];
};

type FailureRow = {
  vehicleId: string;
  occurredAt: string;
  failureMileage: number;
  component: string;
  failureMode: string;
  faultCode: string;
  model: string;
  factory: string;
  firmware: string;
  pumpRevision: string;
  warning: {
    detectedBeforeFailure: boolean;
    firstWarningAt: string | null;
    warningMileage: number | null;
    leadMiles: number | null;
    leadSeconds: number | null;
    leadSimulatedHours: number | null;
    leadSimulatedDays: number | null;
  };
};


type FirmwareOverviewRow = {
  firmware: string;
  population: number;
  failures: number;
  failureRate: number;
  averageRisk: number;
  nonHealthyRate: number;
  averagePumpCurrentA: number;
};

type FirmwareInteraction = {
  pumpRevision: string;
  targetPopulation: number;
  controlPopulation: number;
  targetFailures: number;
  controlFailures: number;
  targetFailureRate: number;
  controlFailureRate: number;
  riskRatio: number | null;
  riskRatio95CI: [number, number] | null;
  absoluteRiskIncrease: number;
  targetAverageRisk: number;
  controlAverageRisk: number;
  averageRiskDelta: number;
};

type FirmwareRegression = {
  targetFirmware: string;
  controlFirmware: string;
  matching: {
    dimensions: string[];
    matchedStrata: number;
    matchedPopulation: number;
    targetPopulation: number;
    controlPopulation: number;
  };
  outcomes: {
    targetFailures: number;
    controlFailures: number;
    targetFailureRate: number;
    controlFailureRate: number;
    absoluteRiskIncrease: number;
    riskRatio: number | null;
    riskRatio95CI: [number, number] | null;
    mantelHaenszelOddsRatio: number | null;
    cmhChiSquare: number | null;
    pValue: number | null;
  };
  telemetrySignals: {
    targetAverageRisk: number;
    controlAverageRisk: number;
    averageRiskDelta: number;
    targetNonHealthyRate: number;
    controlNonHealthyRate: number;
    nonHealthyRateDelta: number;
    targetPumpCurrentA: number;
    controlPumpCurrentA: number;
    pumpCurrentDeltaA: number;
  };
  classification: string;
  hardwareInteractions: FirmwareInteraction[];
  availableFirmware: string[];
  generatedAt: string;
  interpretation: {
    method: string;
    claimPolicy: string;
    telemetrySignalsAreSupportive: boolean;
  };
};

const emptySummary: Summary = {
  vehiclesMonitored: 0,
  telemetryEvents: 0,
  activeAlerts: 0,
  criticalAlerts: 0,
  observedFailures: 0,
  averageRisk: 0,
  health: { healthy: 0, degraded: 0, critical: 0 },
};

function formatNumber(n: number) {
  return new Intl.NumberFormat('en-US', {
    notation: n > 999999 ? 'compact' : 'standard',
    maximumFractionDigits: 1,
  }).format(n);
}

function formatMiles(n: number | null | undefined) {
  if (n == null) return '—';
  return `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(n)} mi`;
}

function formatPct(n: number | null | undefined, digits = 1) {
  if (n == null) return '—';
  return `${(n * 100).toFixed(digits)}%`;
}

function humanize(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, char => char.toUpperCase());
}

export function App() {
  const [page, setPage] = useState<Page>('fleet');
  const [summary, setSummary] = useState<Summary>(emptySummary);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [cohorts, setCohorts] = useState<Cohort[]>([]);
  const [reliability, setReliability] = useState<ReliabilityCohort[]>([]);
  const [failures, setFailures] = useState<FailureRow[]>([]);
  const [firmwareOverview, setFirmwareOverview] = useState<FirmwareOverviewRow[]>([]);
  const [firmwareRegression, setFirmwareRegression] = useState<FirmwareRegression | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let alive = true;
    async function refresh() {
      try {
        const [s, a, c, r, f, fo, fr] = await Promise.all([
          fetch(`${API}/api/v1/fleet/summary`).then(response => response.json()),
          fetch(`${API}/api/v1/alerts?limit=10`).then(response => response.json()),
          fetch(`${API}/api/v1/cohorts/pump-revisions`).then(response => response.json()),
          fetch(`${API}/api/v1/reliability/pump-revisions`).then(response => response.json()),
          fetch(`${API}/api/v1/reliability/failures?limit=12`).then(response => response.json()),
          fetch(`${API}/api/v1/firmware/overview`).then(response => response.json()),
          fetch(`${API}/api/v1/firmware/regression?target=2026.32.4&control=2026.32.1`).then(response => response.json()),
        ]);
        if (alive) {
          setSummary(s);
          setAlerts(a);
          setCohorts(c);
          setReliability(r);
          setFailures(f);
          setFirmwareOverview(fo);
          setFirmwareRegression(fr);
          setConnected(true);
        }
      } catch {
        if (alive) setConnected(false);
      }
    }
    refresh();
    const id = setInterval(refresh, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const totalHealth = Math.max(
    1,
    summary.health.healthy + summary.health.degraded + summary.health.critical,
  );
  const healthPct = useMemo(
    () => ({
      healthy: (summary.health.healthy / totalHealth) * 100,
      degraded: (summary.health.degraded / totalHealth) * 100,
      critical: (summary.health.critical / totalHealth) * 100,
    }),
    [summary, totalHealth],
  );

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brandMark">FM</div>
          <div>
            <b>FLEETMIND</b>
            <span>RELIABILITY OS</span>
          </div>
        </div>
        <nav>
          <button className={page === 'fleet' ? 'navActive' : ''} onClick={() => setPage('fleet')}>
            <Gauge size={17} /> Fleet Overview
          </button>
          <button><AlertTriangle size={17} /> Incidents</button>
          <button className={page === 'reliability' ? 'navActive' : ''} onClick={() => setPage('reliability')}>
            <Activity size={17} /> Reliability
          </button>
          <button><Binary size={17} /> Cohorts</button>
          <button><Cpu size={17} /> Components</button>
          <button className={page === 'firmware' ? 'navActive' : ''} onClick={() => setPage('firmware')}><Zap size={17} /> Firmware</button>
        </nav>
        <div className="sidebarFoot">
          <Radio size={15} />
          <span>{connected ? 'Telemetry stream online' : 'Waiting for services'}</span>
        </div>
      </aside>

      <main>
        <Header connected={connected} page={page} />
        {page === 'fleet' ? (
          <FleetOverview
            summary={summary}
            healthPct={healthPct}
            alerts={alerts}
            cohorts={cohorts}
          />
        ) : page === 'reliability' ? (
          <ReliabilityDashboard
            reliability={reliability}
            failures={failures}
            observedFailures={summary.observedFailures}
          />
        ) : (
          <FirmwareDashboard
            overview={firmwareOverview}
            regression={firmwareRegression}
          />
        )}
      </main>
    </div>
  );
}

function Header({ connected, page }: { connected: boolean; page: Page }) {
  return (
    <header>
      <div>
        <p className="eyebrow">
          {page === 'fleet' ? 'GLOBAL FLEET INTELLIGENCE' : page === 'reliability' ? 'RELIABILITY SCIENCE / COOLANT PUMP' : 'FIRMWARE REGRESSION LAB / MATCHED COHORTS'}
        </p>
        <h1>
          {page === 'fleet'
            ? 'Machine health, before the fault code.'
            : page === 'reliability'
              ? 'Field reliability, quantified from observed life.'
              : 'Did the software change the failure rate?'}
        </h1>
      </div>
      <div className={`live ${connected ? 'on' : ''}`}>
        <span /> {connected ? 'LIVE' : 'OFFLINE'}
      </div>
    </header>
  );
}

function FleetOverview({
  summary,
  healthPct,
  alerts,
  cohorts,
}: {
  summary: Summary;
  healthPct: { healthy: number; degraded: number; critical: number };
  alerts: Alert[];
  cohorts: Cohort[];
}) {
  return (
    <>
      <section className="metrics">
        <Metric icon={<Radio />} label="Vehicles monitored" value={formatNumber(summary.vehiclesMonitored)} detail="last 15 minutes" />
        <Metric icon={<Activity />} label="Telemetry events" value={formatNumber(summary.telemetryEvents)} detail="persisted observations" />
        <Metric icon={<AlertTriangle />} label="Active alerts" value={formatNumber(summary.activeAlerts)} detail={`${summary.criticalAlerts} critical`} />
        <Metric icon={<ShieldCheck />} label="Average risk" value={`${(summary.averageRisk * 100).toFixed(1)}%`} detail={`${summary.observedFailures} observed failures`} />
      </section>

      <section className="grid">
        <article className="panel healthPanel">
          <PanelTitle kicker="FLEET HEALTH" title="Current vehicle state" />
          <div className="healthNumber">{healthPct.healthy.toFixed(2)}<span>%</span></div>
          <p className="muted">Healthy vehicles across the active simulated fleet.</p>
          <div className="healthBar">
            <span className="healthy" style={{ width: `${healthPct.healthy}%` }} />
            <span className="degraded" style={{ width: `${healthPct.degraded}%` }} />
            <span className="critical" style={{ width: `${healthPct.critical}%` }} />
          </div>
          <div className="legend">
            <span><i className="dot healthyDot" />Healthy <b>{summary.health.healthy}</b></span>
            <span><i className="dot degradedDot" />Degraded <b>{summary.health.degraded}</b></span>
            <span><i className="dot criticalDot" />Critical <b>{summary.health.critical}</b></span>
          </div>
        </article>

        <article className="panel signalPanel">
          <PanelTitle kicker="EMERGING SIGNAL" title="Coolant pump degradation" />
          <div className="signalHero">
            <div className="signalIcon"><Thermometer size={25} /></div>
            <div><span>Primary hypothesis</span><strong>CP-17 bearing friction</strong></div>
            <div className="confidence">91<span>%</span><small>scenario prior</small></div>
          </div>
          <div className="hypothesis">
            Pump current ↑ <b>→</b> Pump RPM ↓ <b>→</b> Coolant efficiency ↓ <b>→</b> Battery temperature ↑
          </div>
          <p className="muted">The online risk engine sees only telemetry. Failure truth is isolated on the evaluation stream.</p>
        </article>
      </section>

      <section className="grid lower">
        <article className="panel alertsPanel">
          <PanelTitle kicker="INCIDENT STREAM" title="Latest anomaly detections" />
          <div className="alertList">
            {alerts.length === 0 && <div className="empty">Waiting for the first degradation signature…</div>}
            {alerts.map(alert => (
              <div className="alertRow" key={alert.id}>
                <div className={`severity ${alert.severity}`} />
                <div className="alertMain">
                  <div><b>{alert.vehicleId}</b><span>{alert.title}</span></div>
                  <small>{alert.factory} · {alert.firmware} · {alert.pumpRevision}</small>
                </div>
                <div className="risk">{Math.round(alert.riskScore * 100)}<span>%</span><small>risk</small></div>
              </div>
            ))}
          </div>
        </article>

        <article className="panel cohortPanel">
          <PanelTitle kicker="COHORT ANALYSIS" title="Component revision signal" />
          <div className="cohortHead"><span>Revision</span><span>Samples</span><span>Avg current</span><span>Risk</span></div>
          {[...cohorts].sort((a, b) => b.averageRisk - a.averageRisk).map(cohort => (
            <div className="cohortRow" key={cohort.pumpRevision}>
              <b>{cohort.pumpRevision}</b>
              <span>{formatNumber(cohort.samples)}</span>
              <span>{cohort.averagePumpCurrentA.toFixed(2)} A</span>
              <strong className={cohort.averageRisk > 0.25 ? 'hot' : ''}>{(cohort.averageRisk * 100).toFixed(1)}%</strong>
            </div>
          ))}
        </article>
      </section>
    </>
  );
}

function ReliabilityDashboard({
  reliability,
  failures,
  observedFailures,
}: {
  reliability: ReliabilityCohort[];
  failures: FailureRow[];
  observedFailures: number;
}) {
  const ranked = [...reliability].sort((a, b) => b.failureRate - a.failureRate);
  const primary = ranked.find(item => item.weibull !== null) ?? ranked[0];
  const evaluatedFailures = reliability.reduce((sum, item) => sum + item.earlyWarning.failuresEvaluated, 0);
  const detectedFailures = reliability.reduce((sum, item) => sum + item.earlyWarning.detectedBeforeFailure, 0);
  const leadMiles = failures
    .filter(item => item.warning.detectedBeforeFailure && item.warning.leadMiles != null)
    .map(item => Number(item.warning.leadMiles));
  const medianLead = median(leadMiles);
  const detectionRate = evaluatedFailures ? detectedFailures / evaluatedFailures : null;

  return (
    <>
      <section className="metrics reliabilityMetrics">
        <Metric icon={<Wrench />} label="Observed failures" value={formatNumber(observedFailures)} detail="private evaluation truth" />
        <Metric icon={<Sigma />} label="Weibull β" value={primary?.weibull ? primary.weibull.beta.toFixed(2) : '—'} detail={primary?.weibull ? `${primary.pumpRevision} · ${humanize(primary.weibull.failureBehavior)}` : 'awaiting enough failures'} />
        <Metric icon={<TrendingDown />} label="B10 life" value={primary?.weibull ? compactMiles(primary.weibull.b10Miles) : '—'} detail={primary?.weibull ? `${primary.pumpRevision} modeled life` : 'minimum 2 failures required'} />
        <Metric icon={<TimerReset />} label="Early-warning rate" value={formatPct(detectionRate)} detail={medianLead == null ? 'no evaluated lead yet' : `${formatMiles(medianLead)} median lead`} />
      </section>

      <section className="reliabilityGrid">
        <article className="panel survivalPanel">
          <div className="panelTitleRow">
            <PanelTitle kicker="SURVIVAL ANALYSIS" title="Coolant pump survival by revision" />
            <span className="methodBadge">Kaplan–Meier · right-censored</span>
          </div>
          <SurvivalChart cohorts={reliability} />
          <div className="curveLegend">
            {reliability.map((cohort, index) => (
              <span key={cohort.pumpRevision}><i className={`curveSwatch curve${index % 4}`} />{cohort.pumpRevision}<b>{cohort.failures} failures</b></span>
            ))}
          </div>
        </article>

        <article className="panel engineeringPanel">
          <PanelTitle kicker="ENGINEERING INTERPRETATION" title="Reliability model readout" />
          {primary?.weibull ? (
            <>
              <div className="revisionHero">
                <div>
                  <span>Highest observed failure rate</span>
                  <strong>{primary.pumpRevision}</strong>
                </div>
                <div className="failureRateBig">{formatPct(primary.failureRate)}<small>observed</small></div>
              </div>
              <div className="parameterGrid">
                <Parameter label="β shape" value={primary.weibull.beta.toFixed(3)} note={humanize(primary.weibull.failureBehavior)} />
                <Parameter label="η characteristic life" value={formatMiles(primary.weibull.etaMiles)} note="63.2% modeled failure point" />
                <Parameter label="B10 life" value={formatMiles(primary.weibull.b10Miles)} note="10% modeled failure point" />
                <Parameter label="B50 life" value={formatMiles(primary.weibull.b50Miles)} note="median modeled lifetime" />
              </div>
              <div className="engineeringNote">
                <ShieldCheck size={16} />
                <p><b>{primary.pumpRevision}</b> currently fits a <b>{humanize(primary.weibull.failureBehavior).toLowerCase()}</b> pattern. The fit includes {primary.censored} right-censored vehicles still operating at their latest observed mileage.</p>
              </div>
            </>
          ) : (
            <div className="modelWaiting">
              <Sigma size={28} />
              <strong>Waiting for a stable Weibull fit</strong>
              <p>FleetMind requires at least two observed failures in a cohort before publishing β, η, B10 or B50.</p>
            </div>
          )}
        </article>
      </section>

      <section className="grid reliabilityLower">
        <article className="panel cohortReliabilityPanel">
          <PanelTitle kicker="COHORT SCORECARD" title="Revision-level reliability" />
          <div className="reliabilityTableHead">
            <span>Revision</span><span>Population</span><span>Failures</span><span>Failure rate</span><span>B10</span><span>β</span><span>Warning rate</span>
          </div>
          {ranked.map(cohort => (
            <div className="reliabilityTableRow" key={cohort.pumpRevision}>
              <b>{cohort.pumpRevision}</b>
              <span>{formatNumber(cohort.population)}</span>
              <span>{cohort.failures}</span>
              <strong className={cohort.failureRate > 0.05 ? 'hot' : ''}>{formatPct(cohort.failureRate)}</strong>
              <span>{cohort.weibull ? compactMiles(cohort.weibull.b10Miles) : '—'}</span>
              <span>{cohort.weibull ? cohort.weibull.beta.toFixed(2) : '—'}</span>
              <span>{formatPct(cohort.earlyWarning.detectionRate)}</span>
            </div>
          ))}
          {ranked.length === 0 && <div className="empty">Waiting for cohort observations…</div>}
        </article>

        <article className="panel warningPanel">
          <PanelTitle kicker="EARLY WARNING" title="Detection before component failure" />
          <div className="warningGauge">
            <div className="warningGaugeNumber">{formatPct(detectionRate, 0)}</div>
            <div>
              <b>{detectedFailures} / {evaluatedFailures}</b>
              <span>failures detected early</span>
            </div>
          </div>
          <div className="warningStats">
            <Parameter label="Median lead" value={formatMiles(medianLead)} note="distance before failure" />
            <Parameter label="Evaluated failures" value={formatNumber(evaluatedFailures)} note="with ground truth" />
          </div>
          <p className="muted">Lead time is measured from the first non-healthy telemetry observation to the private simulated failure event.</p>
        </article>
      </section>

      <section className="panel failurePanel">
        <div className="panelTitleRow">
          <PanelTitle kicker="FAILURE EVALUATION" title="Recent ground-truth component failures" />
          <span className="methodBadge">evaluation stream only</span>
        </div>
        <div className="failureHead">
          <span>Vehicle</span><span>Revision</span><span>Failure mileage</span><span>Firmware</span><span>Early warning</span><span>Lead</span><span />
        </div>
        {failures.map(failure => (
          <div className="failureRow" key={`${failure.vehicleId}-${failure.occurredAt}`}>
            <b>{failure.vehicleId}</b>
            <span>{failure.pumpRevision}</span>
            <span>{formatMiles(failure.failureMileage)}</span>
            <span>{failure.firmware}</span>
            <span className={failure.warning.detectedBeforeFailure ? 'detected' : 'missed'}>{failure.warning.detectedBeforeFailure ? 'Detected' : 'Missed'}</span>
            <span>{formatMiles(failure.warning.leadMiles)}</span>
            <ChevronRight size={15} />
          </div>
        ))}
        {failures.length === 0 && <div className="empty">No failure events yet. The accelerated simulator will populate this table as CP-17 units reach failure.</div>}
      </section>
    </>
  );
}


function FirmwareDashboard({
  overview,
  regression,
}: {
  overview: FirmwareOverviewRow[];
  regression: FirmwareRegression | null;
}) {
  const outcome = regression?.outcomes;
  const signals = regression?.telemetrySignals;
  const interaction = regression?.hardwareInteractions?.[0];
  const status = regression?.classification ?? 'insufficient_data';
  const rr = outcome?.riskRatio;
  const ci = outcome?.riskRatio95CI;
  const p = outcome?.pValue;

  return (
    <>
      <section className="metrics firmwareMetrics">
        <Metric icon={<Zap />} label="Regression state" value={statusLabel(status)} detail={regression ? `${regression.targetFirmware} vs ${regression.controlFirmware}` : 'waiting for matched cohorts'} />
        <Metric icon={<TrendingDown />} label="Failure risk ratio" value={rr == null ? '—' : `${rr.toFixed(2)}×`} detail={ci ? `95% CI ${ci[0].toFixed(2)}–${ci[1].toFixed(2)}` : 'effect estimate pending'} />
        <Metric icon={<Sigma />} label="CMH p-value" value={p == null ? '—' : formatPValue(p)} detail={regression ? `${regression.matching.matchedStrata} matched strata` : 'stratified association test'} />
        <Metric icon={<Thermometer />} label="Risk-score delta" value={signals ? signedPct(signals.averageRiskDelta) : '—'} detail={signals ? `${signals.pumpCurrentDeltaA >= 0 ? '+' : ''}${signals.pumpCurrentDeltaA.toFixed(3)} A pump current` : 'supportive telemetry signal'} />
      </section>

      <section className="firmwareHeroGrid">
        <article className="panel regressionPanel">
          <div className="panelTitleRow">
            <PanelTitle kicker="MATCHED-COHORT ANALYSIS" title="Firmware 2026.32.4 regression test" />
            <span className={`regressionBadge ${status}`}>{statusLabel(status)}</span>
          </div>

          {regression ? (
            <>
              <div className="comparisonStrip">
                <FirmwareArm label="TARGET" firmware={regression.targetFirmware} population={regression.matching.targetPopulation} failures={outcome?.targetFailures ?? 0} rate={outcome?.targetFailureRate ?? 0} />
                <div className="versus">VS</div>
                <FirmwareArm label="CONTROL" firmware={regression.controlFirmware} population={regression.matching.controlPopulation} failures={outcome?.controlFailures ?? 0} rate={outcome?.controlFailureRate ?? 0} />
              </div>

              <div className="effectGrid">
                <Parameter label="Risk ratio" value={rr == null ? '—' : `${rr.toFixed(3)}×`} note={ci ? `95% CI ${ci[0].toFixed(2)}–${ci[1].toFixed(2)}` : 'continuity-corrected when needed'} />
                <Parameter label="Absolute risk increase" value={formatSignedPct(outcome?.absoluteRiskIncrease)} note="target minus matched control" />
                <Parameter label="MH odds ratio" value={outcome?.mantelHaenszelOddsRatio == null ? '—' : `${outcome.mantelHaenszelOddsRatio.toFixed(3)}×`} note="common stratified odds ratio" />
                <Parameter label="CMH significance" value={p == null ? '—' : formatPValue(p)} note={p != null && p < 0.05 ? 'statistically significant' : 'not yet significant'} />
              </div>

              <div className="matchingNote">
                <Binary size={16} />
                <div>
                  <b>{regression.matching.matchedPopulation} vehicles across {regression.matching.matchedStrata} matched strata</b>
                  <span>Coarsened exact matching on component revision, 40k-mile odometer band, and ambient-temperature band; factory/model remain visible for follow-up slicing.</span>
                </div>
              </div>
            </>
          ) : (
            <div className="modelWaiting"><Zap size={28} /><strong>Waiting for firmware comparison</strong><p>The API will populate this panel when both target and control firmware cohorts are present.</p></div>
          )}
        </article>

        <article className="panel interactionPanel">
          <PanelTitle kicker="HARDWARE × SOFTWARE" title="Strongest interaction" />
          {interaction ? (
            <>
              <div className="interactionHero">
                <span>Most affected component revision</span>
                <strong>{interaction.pumpRevision}</strong>
                <small>{formatPct(interaction.targetFailureRate)} target failure rate · {formatPct(interaction.controlFailureRate)} control</small>
              </div>
              <div className="interactionSignal">
                <div><span>Failure-rate lift</span><b>{formatSignedPct(interaction.absoluteRiskIncrease)}</b></div>
                <div><span>Risk-score lift</span><b>{signedPct(interaction.averageRiskDelta)}</b></div>
                <div><span>Risk ratio</span><b>{interaction.riskRatio == null ? '—' : `${interaction.riskRatio.toFixed(2)}×`}</b></div>
              </div>
              <div className="engineeringNote firmwareNote"><ShieldCheck size={16} /><p>This view isolates whether the firmware effect concentrates in a specific hardware revision instead of appearing uniformly across the fleet.</p></div>
            </>
          ) : (
            <div className="modelWaiting"><Cpu size={28} /><strong>No interaction yet</strong><p>FleetMind needs both firmware versions represented within the same component revision.</p></div>
          )}
        </article>
      </section>

      <section className="grid firmwareLower">
        <article className="panel firmwareOverviewPanel">
          <PanelTitle kicker="FIRMWARE SCORECARD" title="Fleet outcomes by software version" />
          <div className="firmwareTableHead">
            <span>Firmware</span><span>Population</span><span>Failures</span><span>Failure rate</span><span>Avg risk</span><span>Non-healthy</span><span>Pump current</span>
          </div>
          {overview.map(row => (
            <div className="firmwareTableRow" key={row.firmware}>
              <b>{row.firmware}</b>
              <span>{row.population}</span>
              <span>{row.failures}</span>
              <strong className={row.failureRate > 0.05 ? 'hot' : ''}>{formatPct(row.failureRate)}</strong>
              <span>{formatPct(row.averageRisk)}</span>
              <span>{formatPct(row.nonHealthyRate)}</span>
              <span>{row.averagePumpCurrentA.toFixed(3)} A</span>
            </div>
          ))}
          {overview.length === 0 && <div className="empty">Waiting for firmware cohorts…</div>}
        </article>

        <article className="panel methodPanel">
          <PanelTitle kicker="METHOD" title="What counts as evidence" />
          <div className="methodStack">
            <MethodStep index="01" title="Coarsened exact matching" text="Compare only vehicles sharing component revision, odometer band and ambient-temperature band to preserve enough events for a 500-vehicle demo fleet." />
            <MethodStep index="02" title="Observed failures" text="Ground-truth component failures are the primary outcome; telemetry risk remains supportive evidence." />
            <MethodStep index="03" title="CMH adjustment" text="Use a Cochran–Mantel–Haenszel test to estimate association across matched strata." />
            <MethodStep index="04" title="Claim threshold" text="Regression labels require ≥30 matched vehicles and ≥2 observed failures before FleetMind will call it." />
          </div>
        </article>
      </section>

      <section className="panel interactionTablePanel">
        <div className="panelTitleRow">
          <PanelTitle kicker="INTERACTION MATRIX" title="Firmware effect by component revision" />
          <span className="methodBadge">target vs control</span>
        </div>
        <div className="interactionTableHead">
          <span>Revision</span><span>Target pop.</span><span>Control pop.</span><span>Target failures</span><span>Control failures</span><span>Risk ratio</span><span>Risk lift</span><span>Risk-score Δ</span>
        </div>
        {regression?.hardwareInteractions.map(row => (
          <div className="interactionTableRow" key={row.pumpRevision}>
            <b>{row.pumpRevision}</b>
            <span>{row.targetPopulation}</span>
            <span>{row.controlPopulation}</span>
            <span>{row.targetFailures}</span>
            <span>{row.controlFailures}</span>
            <span>{row.riskRatio == null ? '—' : `${row.riskRatio.toFixed(2)}×`}</span>
            <strong className={row.absoluteRiskIncrease > 0.02 ? 'hot' : ''}>{formatSignedPct(row.absoluteRiskIncrease)}</strong>
            <span>{signedPct(row.averageRiskDelta)}</span>
          </div>
        ))}
      </section>
    </>
  );
}

function FirmwareArm({ label, firmware, population, failures, rate }: { label: string; firmware: string; population: number; failures: number; rate: number }) {
  return (
    <div className="firmwareArm">
      <span>{label}</span>
      <strong>{firmware}</strong>
      <div><b>{failures}</b> failures / {population} matched vehicles</div>
      <small>{formatPct(rate)} observed failure rate</small>
    </div>
  );
}

function MethodStep({ index, title, text }: { index: string; title: string; text: string }) {
  return <div className="methodStep"><span>{index}</span><div><b>{title}</b><p>{text}</p></div></div>;
}

function statusLabel(value: string) {
  return humanize(value).replace('Critical Regression', 'Critical');
}

function formatPValue(value: number) {
  if (value < 0.001) return '<0.001';
  return value.toFixed(3);
}

function formatSignedPct(value: number | null | undefined) {
  if (value == null) return '—';
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)} pp`;
}

function signedPct(value: number | null | undefined) {
  if (value == null) return '—';
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`;
}

function SurvivalChart({ cohorts }: { cohorts: ReliabilityCohort[] }) {
  const width = 820;
  const height = 330;
  const left = 54;
  const right = 24;
  const top = 20;
  const bottom = 42;
  const allMileage = cohorts.flatMap(cohort => cohort.kaplanMeier.map(point => point.mileage));
  const maxMileage = Math.max(100000, ...allMileage, 1);
  const x = (mileage: number) => left + (mileage / maxMileage) * (width - left - right);
  const y = (survival: number) => top + (1 - survival) * (height - top - bottom);
  const xTicks = [0, 0.25, 0.5, 0.75, 1].map(fraction => Math.round(maxMileage * fraction));
  const yTicks = [1, 0.8, 0.6, 0.4, 0.2, 0];

  return (
    <div className="chartWrap">
      <svg className="survivalChart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Kaplan-Meier coolant pump survival curves by component revision">
        {yTicks.map(tick => (
          <g key={tick}>
            <line x1={left} y1={y(tick)} x2={width - right} y2={y(tick)} className="chartGrid" />
            <text x={left - 10} y={y(tick) + 4} className="axisLabel" textAnchor="end">{tick.toFixed(1)}</text>
          </g>
        ))}
        {xTicks.map(tick => (
          <g key={tick}>
            <line x1={x(tick)} y1={top} x2={x(tick)} y2={height - bottom} className="chartGrid vertical" />
            <text x={x(tick)} y={height - 16} className="axisLabel" textAnchor="middle">{compactMiles(tick)}</text>
          </g>
        ))}
        <text x={16} y={height / 2} className="axisTitle" textAnchor="middle" transform={`rotate(-90 16 ${height / 2})`}>SURVIVAL PROBABILITY</text>
        <text x={width / 2} y={height - 1} className="axisTitle" textAnchor="middle">ODOMETER MILEAGE</text>

        {cohorts.map((cohort, index) => {
          const path = stepPath(cohort.kaplanMeier, x, y);
          return path ? <path key={cohort.pumpRevision} d={path} className={`survivalLine curveStroke${index % 4}`} /> : null;
        })}
      </svg>
    </div>
  );
}

function stepPath(
  points: KaplanMeierPoint[],
  x: (value: number) => number,
  y: (value: number) => number,
) {
  if (!points.length) return '';
  let path = `M ${x(points[0].mileage)} ${y(points[0].survival)}`;
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1];
    const current = points[index];
    path += ` L ${x(current.mileage)} ${y(previous.survival)} L ${x(current.mileage)} ${y(current.survival)}`;
  }
  return path;
}

function median(values: number[]) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function compactMiles(value: number) {
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 100000 ? 0 : 1)}K`;
  return `${Math.round(value)}`;
}

function Parameter({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="parameter">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

function Metric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string; detail: string }) {
  return <article className="metric"><div className="metricIcon">{icon}</div><div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></article>;
}

function PanelTitle({ kicker, title }: { kicker: string; title: string }) {
  return <div className="panelTitle"><span>{kicker}</span><h2>{title}</h2></div>;
}
