import { useEffect, useMemo, useState } from 'react';
import {
  Activity, Binary, Boxes, GitCompareArrows, GitFork,
  Layers3, Link2, Save, ScanLine, ShieldCheck, Waypoints,
} from 'lucide-react';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

type TwinList = {
  vehicleId:string; topClass:string; topConfidence:number; decisionState:string;
  attentionScore:number; workloadUnits:number; caseId:number|null; episodeId:number|null;
  maintenancePlanState:string|null; automationStatus:string|null; coverageGaps:string[];
  activeLayerCount:number;
};
type Summary = { totalTwins:number; twinsWithEpisodes:number; twinsWithCases:number; twinsWithMaintenancePlans:number; persistedTwinSnapshots:number; };
type Detail = any;
type Timeline = { items:Array<{id:string;layer:string;title:string;detail:string|null;timestamp:string;mileage:number|null}> };
type Graph = { nodes:Array<{id:string;layer:string;label:string|null;present:boolean}>; edges:Array<{from:string;to:string;relation:string}> };
type Evidence = { counts:Record<string,number> };
type Snapshots = { total:number; snapshots:Array<{id:number;createdAt:string;actor:string;label:string|null;stateHash:string}> };
type Compare = { comparisons:Array<{sameHypothesisClass:boolean;sameDecisionState:boolean;attentionScoreDelta:number;workloadUnitsDelta:number}> };
type Props = { selectedVehicleId:string|null; onSelectVehicle:(id:string)=>void; runId?:number };

function humanize(value:string|null|undefined){return value?value.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase()):'—'}
function pct(v:number|null|undefined){return v==null?'—':`${(v*100).toFixed(1)}%`}
function miles(v:number|null|undefined){return v==null?'—':`${v.toLocaleString(undefined,{maximumFractionDigits:0})} mi`}
async function json<T>(url:string,init?:RequestInit):Promise<T>{const r=await fetch(url,init);if(!r.ok)throw new Error(`${r.status}: ${await r.text()}`);return r.json() as Promise<T>}

export function VehicleOperationalTwin({selectedVehicleId,onSelectVehicle,runId}:Props){
  const [summary,setSummary]=useState<Summary|null>(null);
  const [twins,setTwins]=useState<TwinList[]>([]);
  const [selected,setSelected]=useState<string|null>(null);
  const [detail,setDetail]=useState<Detail|null>(null);
  const [timeline,setTimeline]=useState<Timeline|null>(null);
  const [graph,setGraph]=useState<Graph|null>(null);
  const [evidence,setEvidence]=useState<Evidence|null>(null);
  const [snapshots,setSnapshots]=useState<Snapshots|null>(null);
  const [compareId,setCompareId]=useState('');
  const [comparison,setComparison]=useState<Compare|null>(null);
  const [label,setLabel]=useState('');
  const [error,setError]=useState<string|null>(null);

  async function refreshFleet(){
    const [s,t]=await Promise.all([
      json<Summary>(`${API}/api/v1/diagnostics/twins/summary`),
      json<{twins:TwinList[]}>(`${API}/api/v1/diagnostics/twins?limit=80`),
    ]);
    setSummary(s); setTwins(t.twins);
    setSelected(cur=>cur&&t.twins.some(x=>x.vehicleId===cur)?cur:(selectedVehicleId&&t.twins.some(x=>x.vehicleId===selectedVehicleId)?selectedVehicleId:t.twins[0]?.vehicleId??null));
  }
  async function refreshVehicle(id:string){
    const [d,t,g,e,s]=await Promise.all([
      json<Detail>(`${API}/api/v1/diagnostics/twins/${encodeURIComponent(id)}`),
      json<Timeline>(`${API}/api/v1/diagnostics/twins/${encodeURIComponent(id)}/timeline?limit=120`),
      json<Graph>(`${API}/api/v1/diagnostics/twins/${encodeURIComponent(id)}/graph`),
      json<Evidence>(`${API}/api/v1/diagnostics/twins/${encodeURIComponent(id)}/evidence`),
      json<Snapshots>(`${API}/api/v1/diagnostics/twins/${encodeURIComponent(id)}/snapshots?limit=8`),
    ]);
    setDetail(d); setTimeline(t); setGraph(g); setEvidence(e); setSnapshots(s);
  }

  useEffect(()=>{let alive=true;let timer:ReturnType<typeof setTimeout>|undefined;const cycle=async()=>{try{await refreshFleet();if(alive)setError(null)}catch(e){if(alive)setError(e instanceof Error?e.message:'Twin API unavailable')}finally{if(alive)timer=setTimeout(cycle,15000)}};void cycle();return()=>{alive=false;if(timer)clearTimeout(timer)}},[runId]);
  useEffect(()=>{if(selectedVehicleId&&twins.some(x=>x.vehicleId===selectedVehicleId))setSelected(selectedVehicleId)},[selectedVehicleId,twins]);
  useEffect(()=>{if(!selected)return;setComparison(null);void refreshVehicle(selected).catch(e=>setError(e instanceof Error?e.message:'Twin unavailable'))},[selected,runId]);

  const compareOptions=useMemo(()=>twins.filter(x=>x.vehicleId!==selected).slice(0,50),[twins,selected]);
  async function saveSnapshot(){if(!selected)return;await json(`${API}/api/v1/diagnostics/twins/${encodeURIComponent(selected)}/snapshots`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({actor:'dashboard_operator',label:label.trim()||null})});setLabel('');await refreshVehicle(selected)}
  async function compare(){if(!selected||!compareId)return;setComparison(await json<Compare>(`${API}/api/v1/diagnostics/twins/compare?vehicle_ids=${encodeURIComponent(`${selected},${compareId}`)}`))}

  return <section className="panel vehicleTwinPanel">
    <div className="panelTitleRow"><div className="panelTitle"><span>PHASE 7.1 · VEHICLE OPERATIONAL DIGITAL TWIN</span><h2>One longitudinal operational state for each vehicle</h2></div><span className="methodBadge">OPERATIONAL TWIN · NOT PHYSICS TWIN</span></div>
    <p className="muted vehicleTwinPolicy">The twin unifies current-run model, diagnostic, case, prognostic, maintenance, automation, coverage and fleet-decision evidence. It does not expose private failure truth and does not prove physical component condition, remaining useful life or causality.</p>
    {error&&<div className="diagnosticError">{error}</div>}

    <div className="vehicleTwinMetrics">
      <Metric label="Operational twins" value={summary?.totalTwins??0} detail="current run population"/>
      <Metric label="With episodes" value={summary?.twinsWithEpisodes??0} detail="temporal diagnostic layer"/>
      <Metric label="With cases" value={summary?.twinsWithCases??0} detail="operational workflow layer"/>
      <Metric label="With maintenance" value={summary?.twinsWithMaintenancePlans??0} detail="persisted plan state"/>
      <Metric label="Twin checkpoints" value={summary?.persistedTwinSnapshots??0} detail="idempotent state snapshots"/>
    </div>

    <div className="vehicleTwinLayout">
      <article className="vehicleTwinCard"><Title icon={<ScanLine size={15}/>} over="TWIN POPULATION" title="Highest current operator-attention records"/><div className="vehicleTwinRows">{twins.slice(0,32).map(r=><button key={r.vehicleId} className={selected===r.vehicleId?'selected':''} onClick={()=>{setSelected(r.vehicleId);onSelectVehicle(r.vehicleId)}}><div><b>{r.vehicleId}</b><span>{humanize(r.topClass)} · {humanize(r.decisionState)}</span><small>{r.activeLayerCount}/8 layers · {r.coverageGaps.length} gaps</small></div><strong>{r.attentionScore?.toFixed(1)??'—'}</strong></button>)}</div></article>

      <article className="vehicleTwinCard"><Title icon={<Layers3 size={15}/>} over="CANONICAL TWIN STATE" title={detail?.vehicleId??'Select a vehicle'}/>{detail&&<>
        <div className="vehicleTwinIdentity"><Fact k="Model" v={detail.vehicleContext.model}/><Fact k="Factory" v={detail.vehicleContext.factory}/><Fact k="Firmware" v={detail.vehicleContext.firmware}/><Fact k="Pump rev." v={detail.vehicleContext.pumpRevision}/><Fact k="Mileage" v={miles(detail.vehicleContext.currentMileage)}/></div>
        <div className="vehicleTwinLayerGrid">
          <Layer icon={<Binary size={13}/>} label="MODEL" primary={humanize(detail.modelState.topClass)} secondary={`${pct(detail.modelState.topConfidence)} · ${miles(detail.modelState.anchorMileage)}`}/>
          <Layer icon={<Activity size={13}/>} label="DIAGNOSTIC" primary={humanize(detail.diagnosticState.episodeState)} secondary={detail.diagnosticState.episodeId?`Episode #${detail.diagnosticState.episodeId} · ${detail.diagnosticState.eventCount} events`:'No diagnostic episode'}/>
          <Layer icon={<Boxes size={13}/>} label="CASE" primary={humanize(detail.caseState.status)} secondary={detail.caseState.caseId?`Case #${detail.caseState.caseId} · ${humanize(detail.caseState.reviewPriority)}`:'No case'}/>
          <Layer icon={<Waypoints size={13}/>} label="PROGNOSTIC" primary={humanize(detail.prognosticState.maintenanceTier)} secondary={detail.prognosticState.priorityScore==null?'No prognostic case state':`Priority ${detail.prognosticState.priorityScore.toFixed(1)} · ${humanize(detail.prognosticState.recommendedReviewWindow)}`}/>
          <Layer icon={<ShieldCheck size={13}/>} label="MAINTENANCE" primary={humanize(detail.maintenanceState.state)} secondary={detail.maintenanceState.planId?`Plan #${detail.maintenanceState.planId} · ${detail.maintenanceState.owner||'unowned'}`:'No maintenance plan'}/>
          <Layer icon={<GitFork size={13}/>} label="AUTOMATION" primary={humanize(detail.automationState.currentStatus)} secondary={`${detail.automationState.actionIds.length} action(s)`}/>
          <Layer icon={<Layers3 size={13}/>} label="FLEET DECISION" primary={humanize(detail.fleetDecisionState.decisionState)} secondary={`Attention ${detail.fleetDecisionState.attentionScore.toFixed(1)} · ${detail.fleetDecisionState.workloadUnits.toFixed(2)} load`}/>
          <Layer icon={<Link2 size={13}/>} label="COVERAGE" primary={`${detail.coverageState.coverageGapCount} current gap(s)`} secondary={detail.coverageState.coverageGaps.map(humanize).join(' · ')||'No current coverage gap'}/>
        </div>
        <div className="vehicleTwinPresence"><span>Active operational layers</span><b>{detail.layerPresence.activeLayerCount}/{detail.layerPresence.availableLayerCount}</b><div>{detail.layerPresence.activeLayers.map((x:string)=><span key={x}>{humanize(x)}</span>)}</div><small>Layer presence is descriptive, not a physical-health or data-quality score.</small></div>
      </>}</article>
    </div>

    <div className="vehicleTwinLowerGrid">
      <article className="vehicleTwinCard"><Title icon={<Waypoints size={15}/>} over="LONGITUDINAL TWIN TIMELINE" title="Merged model and workflow chronology"/><div className="vehicleTwinTimeline">{(timeline?.items??[]).slice(-22).reverse().map(i=><div key={i.id}><span className="twinTimelineDot"/><div><b>{i.title}</b><span>{humanize(i.layer)} · {i.mileage==null?'workflow time':miles(i.mileage)}</span><small>{new Date(i.timestamp).toLocaleString()} · {i.detail||'—'}</small></div></div>)}</div></article>
      <article className="vehicleTwinCard"><Title icon={<GitFork size={15}/>} over="STATE LINEAGE GRAPH" title="Evidence-to-workflow relationships"/><div className="vehicleTwinGraph">{(graph?.nodes??[]).map(n=><div className={n.present?'present':'absent'} key={n.id}><span>{humanize(n.layer)}</span><b>{humanize(n.label)}</b></div>)}</div><div className="vehicleTwinEdges">{(graph?.edges??[]).map(e=><span key={`${e.from}-${e.to}`}>{humanize(e.from)} <b>→</b> {humanize(e.to)}<small>{humanize(e.relation)}</small></span>)}</div><p className="muted twinGraphPolicy">This is data/workflow lineage, not a causal component graph.</p></article>
    </div>

    <div className="vehicleTwinLowerGrid">
      <article className="vehicleTwinCard"><Title icon={<ShieldCheck size={15}/>} over="EVIDENCE INVENTORY" title="What the operational twin is actually grounded in"/><div className="vehicleTwinEvidenceGrid">{Object.entries(evidence?.counts??{}).map(([k,v])=><div key={k}><span>{humanize(k)}</span><b>{Number(v).toLocaleString()}</b></div>)}</div><div className="vehicleTwinTruthBoundary"><ShieldCheck size={14}/><span>Private failure truth excluded · failure markers not exposed · observed signals are not causal attribution.</span></div></article>
      <article className="vehicleTwinCard"><Title icon={<Save size={15}/>} over="TWIN CHECKPOINTS" title="Idempotent current-state snapshots"/><div className="vehicleTwinSnapshotControls"><input value={label} onChange={e=>setLabel(e.target.value)} placeholder="Optional checkpoint label"/><button onClick={()=>void saveSnapshot()}><Save size={13}/>Save twin checkpoint</button></div><div className="vehicleTwinSnapshotRows">{(snapshots?.snapshots??[]).map(s=><div key={s.id}><b>{s.label||`Twin snapshot ${s.id}`}</b><span>{s.actor} · {new Date(s.createdAt).toLocaleString()}</span><small>{s.stateHash.slice(0,16)}…</small></div>)}</div>
        <div className="vehicleTwinCompare"><Title icon={<GitCompareArrows size={14}/>} over="COMPARE OPERATIONAL TWINS" title="Deterministic state differencing"/><div className="vehicleTwinCompareControls"><select value={compareId} onChange={e=>setCompareId(e.target.value)}><option value="">Select comparison vehicle</option>{compareOptions.map(r=><option key={r.vehicleId} value={r.vehicleId}>{r.vehicleId} · {humanize(r.topClass)}</option>)}</select><button disabled={!compareId} onClick={()=>void compare()}>Compare</button></div>{comparison?.comparisons[0]&&<div className="vehicleTwinCompareResult"><Fact k="Same hypothesis" v={comparison.comparisons[0].sameHypothesisClass?'YES':'NO'}/><Fact k="Same decision" v={comparison.comparisons[0].sameDecisionState?'YES':'NO'}/><Fact k="Attention Δ" v={comparison.comparisons[0].attentionScoreDelta.toFixed(1)}/><Fact k="Load Δ" v={comparison.comparisons[0].workloadUnitsDelta.toFixed(2)}/></div>}</div>
      </article>
    </div>
    <div className="vehicleTwinFooter"><Activity size={14}/><span>Operational twin state is a synchronized view of current-run evidence and workflow records. It is intentionally narrower than a physical, behavioral or physics-based digital twin.</span></div>
  </section>
}

function Metric({label,value,detail}:{label:string;value:number;detail:string}){return <div className="vehicleTwinMetric"><span>{label}</span><strong>{value.toLocaleString()}</strong><small>{detail}</small></div>}
function Title({icon,over,title}:{icon:React.ReactNode;over:string;title:string}){return <div className="vehicleTwinCardTitle">{icon}<div><span>{over}</span><b>{title}</b></div></div>}
function Fact({k,v}:{k:string;v:any}){return <div><span>{k}</span><b>{v??'—'}</b></div>}
function Layer({icon,label,primary,secondary}:{icon:React.ReactNode;label:string;primary:string;secondary:string}){return <div className="vehicleTwinLayer"><div>{icon}<span>{label}</span></div><b>{primary}</b><small>{secondary}</small></div>}
