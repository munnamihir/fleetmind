import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Binary,
  Cpu,
  Gauge,
  Radio,
  ShieldCheck,
  Thermometer,
  Zap,
} from 'lucide-react';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

type Summary = {
  vehiclesMonitored: number;
  telemetryEvents: number;
  activeAlerts: number;
  criticalAlerts: number;
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

const emptySummary: Summary = {
  vehiclesMonitored: 0,
  telemetryEvents: 0,
  activeAlerts: 0,
  criticalAlerts: 0,
  averageRisk: 0,
  health: { healthy: 0, degraded: 0, critical: 0 },
};

function formatNumber(n: number) {
  return new Intl.NumberFormat('en-US', { notation: n > 999999 ? 'compact' : 'standard', maximumFractionDigits: 1 }).format(n);
}

export function App() {
  const [summary, setSummary] = useState<Summary>(emptySummary);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [cohorts, setCohorts] = useState<Cohort[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let alive = true;
    async function refresh() {
      try {
        const [s, a, c] = await Promise.all([
          fetch(`${API}/api/v1/fleet/summary`).then(r => r.json()),
          fetch(`${API}/api/v1/alerts?limit=10`).then(r => r.json()),
          fetch(`${API}/api/v1/cohorts/pump-revisions`).then(r => r.json()),
        ]);
        if (alive) {
          setSummary(s);
          setAlerts(a);
          setCohorts(c);
          setConnected(true);
        }
      } catch {
        if (alive) setConnected(false);
      }
    }
    refresh();
    const id = setInterval(refresh, 2500);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const totalHealth = Math.max(1, summary.health.healthy + summary.health.degraded + summary.health.critical);
  const healthPct = useMemo(() => ({
    healthy: summary.health.healthy / totalHealth * 100,
    degraded: summary.health.degraded / totalHealth * 100,
    critical: summary.health.critical / totalHealth * 100,
  }), [summary, totalHealth]);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><div className="brandMark">FM</div><div><b>FLEETMIND</b><span>RELIABILITY OS</span></div></div>
        <nav>
          <button className="navActive"><Gauge size={17}/> Fleet Overview</button>
          <button><AlertTriangle size={17}/> Incidents</button>
          <button><Activity size={17}/> Reliability</button>
          <button><Binary size={17}/> Cohorts</button>
          <button><Cpu size={17}/> Components</button>
          <button><Zap size={17}/> Firmware</button>
        </nav>
        <div className="sidebarFoot"><Radio size={15}/><span>{connected ? 'Telemetry stream online' : 'Waiting for services'}</span></div>
      </aside>

      <main>
        <header>
          <div><p className="eyebrow">GLOBAL FLEET INTELLIGENCE</p><h1>Machine health, before the fault code.</h1></div>
          <div className={`live ${connected ? 'on' : ''}`}><span/> {connected ? 'LIVE' : 'OFFLINE'}</div>
        </header>

        <section className="metrics">
          <Metric icon={<Radio/>} label="Vehicles monitored" value={formatNumber(summary.vehiclesMonitored)} detail="last 15 minutes" />
          <Metric icon={<Activity/>} label="Telemetry events" value={formatNumber(summary.telemetryEvents)} detail="processed by FleetMind" />
          <Metric icon={<AlertTriangle/>} label="Active alerts" value={formatNumber(summary.activeAlerts)} detail={`${summary.criticalAlerts} critical`} />
          <Metric icon={<ShieldCheck/>} label="Average risk" value={`${(summary.averageRisk * 100).toFixed(1)}%`} detail="fleet-wide model score" />
        </section>

        <section className="grid">
          <article className="panel healthPanel">
            <PanelTitle kicker="FLEET HEALTH" title="Current vehicle state" />
            <div className="healthNumber">{healthPct.healthy.toFixed(2)}<span>%</span></div>
            <p className="muted">Healthy vehicles across the active simulated fleet.</p>
            <div className="healthBar">
              <span className="healthy" style={{width: `${healthPct.healthy}%`}} />
              <span className="degraded" style={{width: `${healthPct.degraded}%`}} />
              <span className="critical" style={{width: `${healthPct.critical}%`}} />
            </div>
            <div className="legend">
              <span><i className="dot healthyDot"/>Healthy <b>{summary.health.healthy}</b></span>
              <span><i className="dot degradedDot"/>Degraded <b>{summary.health.degraded}</b></span>
              <span><i className="dot criticalDot"/>Critical <b>{summary.health.critical}</b></span>
            </div>
          </article>

          <article className="panel signalPanel">
            <PanelTitle kicker="EMERGING SIGNAL" title="Coolant pump degradation" />
            <div className="signalHero">
              <div className="signalIcon"><Thermometer size={25}/></div>
              <div><span>Primary hypothesis</span><strong>CP-17 bearing friction</strong></div>
              <div className="confidence">91<span>%</span><small>confidence</small></div>
            </div>
            <div className="hypothesis">
              Pump current ↑ <b>→</b> Pump RPM ↓ <b>→</b> Coolant efficiency ↓ <b>→</b> Battery temperature ↑
            </div>
            <p className="muted">This is inferred from telemetry. The simulator never sends a failure label.</p>
          </article>
        </section>

        <section className="grid lower">
          <article className="panel alertsPanel">
            <PanelTitle kicker="INCIDENT STREAM" title="Latest anomaly detections" />
            <div className="alertList">
              {alerts.length === 0 && <div className="empty">Waiting for the first degradation signature…</div>}
              {alerts.map(a => (
                <div className="alertRow" key={a.id}>
                  <div className={`severity ${a.severity}`} />
                  <div className="alertMain">
                    <div><b>{a.vehicleId}</b><span>{a.title}</span></div>
                    <small>{a.factory} · {a.firmware} · {a.pumpRevision}</small>
                  </div>
                  <div className="risk">{Math.round(a.riskScore * 100)}<span>%</span><small>risk</small></div>
                </div>
              ))}
            </div>
          </article>

          <article className="panel cohortPanel">
            <PanelTitle kicker="COHORT ANALYSIS" title="Component revision signal" />
            <div className="cohortHead"><span>Revision</span><span>Samples</span><span>Avg current</span><span>Risk</span></div>
            {[...cohorts].sort((a,b) => b.averageRisk-a.averageRisk).map(c => (
              <div className="cohortRow" key={c.pumpRevision}>
                <b>{c.pumpRevision}</b>
                <span>{formatNumber(c.samples)}</span>
                <span>{c.averagePumpCurrentA.toFixed(2)} A</span>
                <strong className={c.averageRisk > .25 ? 'hot' : ''}>{(c.averageRisk*100).toFixed(1)}%</strong>
              </div>
            ))}
          </article>
        </section>
      </main>
    </div>
  );
}

function Metric({icon, label, value, detail}:{icon: React.ReactNode; label:string; value:string; detail:string}) {
  return <article className="metric"><div className="metricIcon">{icon}</div><div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></article>;
}

function PanelTitle({kicker,title}:{kicker:string;title:string}) {
  return <div className="panelTitle"><span>{kicker}</span><h2>{title}</h2></div>;
}
