import {
  ArrowLeft,
  ArrowRight,
  Clock3,
  Database,
  GitBranch,
  Play,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react';
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';

import './FleetMindPublicDemo.css';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
const ENTERED_KEY = 'fleetmind-public-demo-entered';
const START_STORY_EVENT = 'fleetmind:start-demo-story';
const OPEN_LANDING_EVENT = 'fleetmind:open-demo-landing';

type DiagnosticStatus = {
  status: string;
  runId?: number;
  experimentId?: string | null;
  lineage?: string;
  champion?: string | null;
  createdAt?: string;
};

type DiagnosticIncident = {
  vehicleId: string;
  topClass: string;
  topConfidence: number;
};

type StoryStep = {
  eyebrow: string;
  title: string;
  body: string;
  pageLabel: string;
  viewLabel: string;
  scrollTarget: string;
  nestedButtons?: string[];
};

const STORY_STEPS: StoryStep[] = [
  {
    eyebrow: '1 · VEHICLE EVIDENCE',
    title: 'Start with one synthetic vehicle, not a conclusion.',
    body: 'Inspect the selected high-confidence incident, its observed telemetry signals and the mileage where the diagnostic hypothesis was formed. The evidence is observable context, not hidden failure truth.',
    pageLabel: 'Root Cause',
    viewLabel: 'Investigate',
    scrollTarget: '.vehicleInvestigationPanel',
  },
  {
    eyebrow: '2 · COMPETING HYPOTHESES',
    title: 'Rank the explanation, then keep the alternatives visible.',
    body: 'FleetMind presents a primary model hypothesis alongside competing classes and confidence values. Confidence is model belief from synthetic telemetry; it is not physical failure probability or causal proof.',
    pageLabel: 'Root Cause',
    viewLabel: 'Investigate',
    scrollTarget: '.hypothesisRank',
  },
  {
    eyebrow: '3 · INVESTIGATION CASE',
    title: 'Turn the episode into auditable human work.',
    body: 'The same selected vehicle flows into Case Intelligence, where status, priority, assignment and notes organize review. Workflow metadata stays separate from physical-condition claims.',
    pageLabel: 'Root Cause',
    viewLabel: 'Cases',
    scrollTarget: '.diagnosticCasePanel',
  },
  {
    eyebrow: '4 · HUMAN-GOVERNED ACTION',
    title: 'Review a persisted recommendation before anything can execute.',
    body: 'Closed Loop shows deterministic recommendations and their lifecycle. FleetMind never treats recommendation generation as approval, and execution state is not presented as physical repair.',
    pageLabel: 'Root Cause',
    viewLabel: 'Actions & Outcomes',
    nestedButtons: ['Closed Loop', 'Recommendations'],
    scrollTarget: '.fleetOpsWorkspace',
  },
  {
    eyebrow: '5 · OBSERVED OUTCOME',
    title: 'Close the loop with evidence, not a victory claim.',
    body: 'Outcome evaluation reports what changed after workflow execution while preserving the boundary that observed improvement does not prove the maintenance action caused it.',
    pageLabel: 'Root Cause',
    viewLabel: 'Actions & Outcomes',
    nestedButtons: ['Closed Loop', 'Outcomes'],
    scrollTarget: '.fleetOpsWorkspace',
  },
];

async function fetchJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal, cache: 'no-store' });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

function clickButtonByText(selector: string, label: string) {
  const normalized = label.trim().toLowerCase();
  const button = Array.from(
    document.querySelectorAll<HTMLButtonElement>(selector),
  ).find(candidate => candidate.textContent?.trim().toLowerCase() === normalized);
  button?.click();
  return Boolean(button);
}

function navigateTo(step: StoryStep) {
  const pageChanged = clickButtonByText('.sidebar nav button', step.pageLabel);

  window.setTimeout(() => {
    const primaryChanged = clickButtonByText(
      '[role="tab"].dashboardPageTab',
      step.viewLabel,
    );

    if (!primaryChanged) {
      clickButtonByText('.dashboardPageTabsMoreMenu button', step.viewLabel);
    }

    if (step.nestedButtons?.length) {
      window.setTimeout(() => {
        step.nestedButtons?.forEach((label, index) => {
          window.setTimeout(() => {
            clickButtonByText(
              index === 0 ? '.fleetOpsTabs button' : '.fleetOpsWorkspace button',
              label,
            );
          }, index * 120);
        });
      }, 240);
    }

    window.setTimeout(() => {
      document.querySelector<HTMLElement>(step.scrollTarget)?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }, step.nestedButtons?.length ? 650 : 360);
  }, pageChanged ? 80 : 0);
}

function formatRefresh(value?: string) {
  if (!value) return 'Waiting for refresh metadata';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function useDemoStatus() {
  const [status, setStatus] = useState<DiagnosticStatus | null>(null);
  const [error, setError] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setStatus(await fetchJson<DiagnosticStatus>(`${API}/api/v1/diagnostics/status`));
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 60000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  return { status, error };
}

export function FleetMindDemoBanner() {
  const { status, error } = useDemoStatus();

  return (
    <section className="fmDemoBanner" aria-label="Synthetic demo provenance">
      <div className="fmDemoIdentity">
        <span className="fmDemoBadge"><Sparkles size={12} /> SYNTHETIC DEMO</span>
        <span>Scheduled batch data · not live vehicle telemetry</span>
      </div>

      <div className="fmDemoProvenance">
        <span title="Diagnostic run creation time from the scheduled demo refresh">
          <Clock3 size={12} />
          <b>Last refresh</b>
          {error ? 'metadata unavailable' : formatRefresh(status?.createdAt)}
        </span>
        <span><Database size={12} /><b>Experiment</b>{status?.experimentId ?? '—'}</span>
        <span><GitBranch size={12} /><b>Run</b>{status?.runId ?? '—'}</span>
        <span className="fmDemoLineage"><b>Lineage</b>{status?.lineage ?? '—'}</span>
      </div>

      <div className="fmDemoBannerActions">
        <button
          type="button"
          onClick={() => window.dispatchEvent(new Event(OPEN_LANDING_EVENT))}
        >
          About demo
        </button>
        <button
          type="button"
          className="primary"
          onClick={() => window.dispatchEvent(new Event(START_STORY_EVENT))}
        >
          <Play size={12} /> Guided demo
        </button>
      </div>
    </section>
  );
}

export function FleetMindPublicDemoExperience() {
  const { status } = useDemoStatus();
  const [landingOpen, setLandingOpen] = useState(
    () => window.sessionStorage.getItem(ENTERED_KEY) !== 'true',
  );
  const [storyActive, setStoryActive] = useState(false);
  const [storyIndex, setStoryIndex] = useState(0);
  const [storyVehicleId, setStoryVehicleId] = useState<string | null>(null);

  const currentStep = STORY_STEPS[storyIndex];

  const closeLanding = useCallback(() => {
    window.sessionStorage.setItem(ENTERED_KEY, 'true');
    setLandingOpen(false);
  }, []);

  const startStory = useCallback(() => {
    closeLanding();
    setStoryIndex(0);
    setStoryActive(true);
  }, [closeLanding]);

  useEffect(() => {
    const openLanding = () => setLandingOpen(true);
    const beginStory = () => startStory();
    window.addEventListener(OPEN_LANDING_EVENT, openLanding);
    window.addEventListener(START_STORY_EVENT, beginStory);
    return () => {
      window.removeEventListener(OPEN_LANDING_EVENT, openLanding);
      window.removeEventListener(START_STORY_EVENT, beginStory);
    };
  }, [startStory]);

  useEffect(() => {
    if (!storyActive) return;
    const controller = new AbortController();
    fetchJson<DiagnosticIncident[]>(
      `${API}/api/v1/diagnostics/incidents?limit=1&min_confidence=0.70`,
      controller.signal,
    )
      .then(rows => setStoryVehicleId(rows[0]?.vehicleId ?? null))
      .catch(() => setStoryVehicleId(null));
    return () => controller.abort();
  }, [storyActive, status?.runId]);

  useEffect(() => {
    if (!storyActive) return;
    navigateTo(currentStep);
  }, [currentStep, storyActive]);

  const progress = useMemo(
    () => `${storyIndex + 1} / ${STORY_STEPS.length}`,
    [storyIndex],
  );

  return (
    <>
      {landingOpen && (
        <div className="fmDemoLanding" role="dialog" aria-modal="true" aria-labelledby="fm-demo-title">
          <div className="fmDemoLandingGlow" aria-hidden="true" />
          <div className="fmDemoLandingShell">
            <header className="fmDemoLandingTop">
              <div className="fmDemoLandingBrand">
                <span>FM</span>
                <div><b>FLEETMIND</b><small>PUBLIC RESEARCH DEMO</small></div>
              </div>
              <span className="fmDemoBadge"><Sparkles size={12} /> SYNTHETIC DEMO</span>
            </header>

            <div className="fmDemoLandingHero">
              <div>
                <p>RELIABILITY INTELLIGENCE · EVIDENCE-FIRST OPERATIONS</p>
                <h1 id="fm-demo-title">From fleet signal to human-governed outcome.</h1>
                <span>
                  FleetMind is a synthetic reliability operating-system demo for exploring telemetry evidence,
                  competing diagnostic hypotheses, auditable cases and closed-loop workflow without claiming
                  autonomous repair or physical failure certainty.
                </span>
                <div className="fmDemoLandingCtas">
                  <button type="button" className="primary" onClick={startStory}>
                    <Play size={15} /> Take the guided demo
                  </button>
                  <button type="button" onClick={closeLanding}>
                    Enter command center <ArrowRight size={15} />
                  </button>
                </div>
              </div>

              <aside className="fmDemoLandingProof">
                <span>CURRENT DEMO PROVENANCE</span>
                <dl>
                  <div><dt>Dataset</dt><dd>Deterministic synthetic fleet</dd></div>
                  <div><dt>Refresh</dt><dd>{formatRefresh(status?.createdAt)}</dd></div>
                  <div><dt>Experiment</dt><dd>{status?.experimentId ?? 'loading…'}</dd></div>
                  <div><dt>Diagnostic run</dt><dd>{status?.runId ?? '—'}</dd></div>
                  <div><dt>Lineage</dt><dd>{status?.lineage ?? '—'}</dd></div>
                </dl>
              </aside>
            </div>

            <div className="fmDemoLandingPrinciples">
              <article><ShieldCheck size={17} /><b>Evidence before claims</b><span>Telemetry context and model confidence stay distinct from causal proof and physical-risk probability.</span></article>
              <article><GitBranch size={17} /><b>Auditable workflow</b><span>Cases, recommendations, approvals and outcomes remain explicit persisted stages.</span></article>
              <article><Database size={17} /><b>Free scheduled demo</b><span>GitHub Actions refreshes a bounded synthetic dataset into Neon; visitors do not depend on a local machine or Docker.</span></article>
            </div>
          </div>
        </div>
      )}

      {storyActive && !landingOpen && (
        <aside className="fmDemoStory" aria-live="polite">
          <div className="fmDemoStoryHead">
            <span>{currentStep.eyebrow}</span>
            <button type="button" onClick={() => setStoryActive(false)} aria-label="Close guided demo"><X size={15} /></button>
          </div>
          <h2>{currentStep.title}</h2>
          <p>{currentStep.body}</p>
          <div className="fmDemoStoryVehicle">
            <span>Story vehicle</span>
            <b>{storyVehicleId ?? 'current top incident'}</b>
            <small>synthetic · run {status?.runId ?? '—'}</small>
          </div>
          <div className="fmDemoStoryFooter">
            <span>{progress}</span>
            <div>
              <button
                type="button"
                disabled={storyIndex === 0}
                onClick={() => setStoryIndex(index => Math.max(0, index - 1))}
              >
                <ArrowLeft size={14} /> Back
              </button>
              {storyIndex < STORY_STEPS.length - 1 ? (
                <button
                  type="button"
                  className="primary"
                  onClick={() => setStoryIndex(index => Math.min(STORY_STEPS.length - 1, index + 1))}
                >
                  Next <ArrowRight size={14} />
                </button>
              ) : (
                <button type="button" className="primary" onClick={() => setStoryActive(false)}>
                  Finish
                </button>
              )}
            </div>
          </div>
        </aside>
      )}
    </>
  );
}
