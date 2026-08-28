import {
  ArrowRight,
  BrainCircuit,
  ChevronRight,
  CircleHelp,
  Gauge,
  Layers3,
  Search,
  ShieldCheck,
  Sparkles,
  Wrench,
  X,
} from 'lucide-react';
import {
  type ChangeEvent,
  type KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import './FleetMindExperience.css';

type Destination = {
  id: string;
  label: string;
  group: string;
  description: string;
  keywords: string[];
  pageLabel: string;
  viewLabel?: string;
};

type ScreenContext = {
  eyebrow: string;
  title: string;
  explanation: string;
  primaryAction: string;
  next: string;
  truthBoundary?: string;
};

const DESTINATIONS: Destination[] = [
  {
    id: 'overview',
    label: 'Overview',
    group: 'Operate',
    description: 'Fleet health, active attention, emerging issues and recent evidence.',
    keywords: ['home', 'command center', 'health', 'fleet summary'],
    pageLabel: 'Fleet Overview',
    viewLabel: 'Overview',
  },
  {
    id: 'fleet',
    label: 'Fleet',
    group: 'Operate',
    description: 'Review fleet health and identify vehicles that need attention.',
    keywords: ['vehicles', 'fleet health', 'attention', 'critical'],
    pageLabel: 'Fleet Overview',
    viewLabel: 'Fleet Health',
  },
  {
    id: 'diagnostics',
    label: 'Diagnostics',
    group: 'Investigate',
    description: 'Investigate competing hypotheses, cases, evidence and vehicle context.',
    keywords: ['root cause', 'case', 'evidence', 'investigate', 'hypothesis'],
    pageLabel: 'Root Cause',
    viewLabel: 'Overview',
  },
  {
    id: 'actions',
    label: 'Actions',
    group: 'Act',
    description: 'Review recommendations, approvals, execution readiness and workflows.',
    keywords: ['recommendation', 'approval', 'workflow', 'execute', 'closed loop'],
    pageLabel: 'Root Cause',
    viewLabel: 'Fleet Command',
  },
  {
    id: 'outcomes',
    label: 'Outcomes',
    group: 'Learn',
    description: 'Review post-execution observations and effectiveness evidence.',
    keywords: ['outcome', 'effectiveness', 'observation', 'improved', 'worsening'],
    pageLabel: 'Root Cause',
    viewLabel: 'Fleet Command',
  },
  {
    id: 'intelligence',
    label: 'Intelligence',
    group: 'Learn',
    description: 'Inspect predictive models, benchmark evidence and model behavior.',
    keywords: ['model', 'ml', 'prediction', 'benchmark', 'drift', 'policy'],
    pageLabel: 'Predictive ML',
    viewLabel: 'Overview',
  },
  {
    id: 'platform',
    label: 'Platform',
    group: 'Operate',
    description: 'Inspect platform health, observability, model operations and multi-asset services.',
    keywords: ['system health', 'observability', 'deployment', 'prometheus', 'multi asset'],
    pageLabel: 'Root Cause',
    viewLabel: 'Platform',
  },
  {
    id: 'incidents',
    label: 'Incidents',
    group: 'Advanced',
    description: 'Operational anomaly detections and observed failure records.',
    keywords: ['alert', 'incident stream', 'failure'],
    pageLabel: 'Incidents',
    viewLabel: 'Overview',
  },
  {
    id: 'reliability',
    label: 'Reliability',
    group: 'Advanced',
    description: 'Reliability engineering, survival evidence and early-warning analysis.',
    keywords: ['weibull', 'survival', 'early warning'],
    pageLabel: 'Reliability',
    viewLabel: 'Overview',
  },
  {
    id: 'firmware',
    label: 'Firmware',
    group: 'Advanced',
    description: 'Matched-cohort firmware regression and interaction evidence.',
    keywords: ['software', 'firmware regression', 'matched cohort'],
    pageLabel: 'Firmware',
    viewLabel: 'Overview',
  },
];

const PAGE_CONTEXT: Record<string, ScreenContext> = {
  fleet: {
    eyebrow: 'FLEET OVERVIEW',
    title: 'Understand fleet health and decide where to investigate.',
    explanation:
      'This area summarizes the current fleet state from telemetry and observed evidence. Use it to find vehicles or cohorts that deserve attention.',
    primaryAction: 'Select a health or attention signal, then inspect the related evidence before acting.',
    next: 'Move into Diagnostics when a vehicle or pattern needs investigation.',
    truthBoundary:
      'An attention or risk score prioritizes review; it is not a physical failure probability.',
  },
  incidents: {
    eyebrow: 'INCIDENTS',
    title: 'Review active detections without confusing them with observed failures.',
    explanation:
      'This screen keeps anomaly detections and recorded failure outcomes visible together while preserving the distinction between them.',
    primaryAction: 'Open the vehicle or diagnostic evidence behind a detection that needs review.',
    next: 'Use Diagnostics to test competing explanations for the signal.',
    truthBoundary: 'An alert is evidence for attention, not proof that a component has failed.',
  },
  reliability: {
    eyebrow: 'RELIABILITY',
    title: 'Interpret observed component life and early-warning performance.',
    explanation:
      'Reliability views summarize observed fleet-life evidence such as survival behavior, recorded failures and warning lead time.',
    primaryAction: 'Compare cohorts and inspect the evidence supporting any difference.',
    next: 'Use cohort or component views to narrow the population behind a pattern.',
    truthBoundary: 'Descriptive reliability differences do not by themselves establish causality.',
  },
  cohorts: {
    eyebrow: 'COHORTS',
    title: 'Compare populations before drawing conclusions.',
    explanation:
      'Cohort views help you compare revision populations and identify patterns that deserve deeper investigation.',
    primaryAction: 'Select the cohort with the clearest difference and inspect its supporting evidence.',
    next: 'Move to Reliability, Components or Diagnostics for a more specific investigation.',
    truthBoundary: 'Correlation across cohorts is not proof of a causal mechanism.',
  },
  components: {
    eyebrow: 'COMPONENTS',
    title: 'Understand component-level fleet evidence.',
    explanation:
      'This screen organizes observed health and reliability evidence around components and revisions.',
    primaryAction: 'Use the component signal to identify affected vehicles or cohorts.',
    next: 'Open Diagnostics when component evidence warrants vehicle-level investigation.',
  },
  firmware: {
    eyebrow: 'FIRMWARE',
    title: 'Compare software populations with matched evidence.',
    explanation:
      'Firmware analysis compares matched populations and supporting telemetry signals to identify possible regressions or interactions.',
    primaryAction: 'Review the matched cohort and interaction evidence before interpreting a difference.',
    next: 'Investigate affected vehicles or hardware cohorts if the signal remains material.',
    truthBoundary: 'A firmware association does not establish that software caused a physical failure.',
  },
  ml: {
    eyebrow: 'INTELLIGENCE',
    title: 'Inspect predictive evidence, qualification and model behavior.',
    explanation:
      'Model views show prediction behavior, benchmark qualification, calibration and explainability for diagnostic support.',
    primaryAction: 'Check qualification and benchmark evidence before relying on model output.',
    next: 'Use Diagnostics to combine model evidence with vehicle and fleet context.',
    truthBoundary: 'Model confidence or prediction horizon is not confirmed physical remaining useful life.',
  },
  diagnostics: {
    eyebrow: 'DIAGNOSTICS',
    title: 'Investigate evidence, decide what matters, and choose the next human action.',
    explanation:
      'Diagnostics connects hypotheses, cases, vehicle context, fleet patterns, recommendations, outcomes and platform intelligence.',
    primaryAction: 'Start with Overview or Vehicle Investigation; move to Fleet Command only after the evidence is understood.',
    next: 'Recommendations remain human-gated through acknowledgment, approval and explicit execution.',
    truthBoundary: 'Workflow execution records an operational action; it does not confirm a physical repair.',
  },
};

const VIEW_CONTEXT: Record<string, Partial<ScreenContext>> = {
  'fleet-health': {
    title: 'See which parts of the fleet need attention.',
    primaryAction: 'Choose a degraded or critical signal and inspect the evidence behind it.',
  },
  'vehicle-investigation': {
    title: 'Build a vehicle-level understanding from multiple evidence sources.',
    primaryAction: 'Review chronology, competing hypotheses and supporting/contradictory evidence.',
    next: 'Open or review a diagnostic case when the evidence warrants continued investigation.',
  },
  cases: {
    title: 'Track diagnostic investigations as explicit cases.',
    primaryAction: 'Select a case to review its status, evidence and available next actions.',
  },
  'fleet-command': {
    eyebrow: 'ACTIONS & OUTCOMES',
    title: 'Review recommendations, human approvals, execution state and observed outcomes.',
    explanation:
      'Fleet Command is the closed-loop operational workspace. Recommendations do not auto-approve or auto-execute.',
    primaryAction: 'Select the current workflow stage and complete only the human action that is presently allowed.',
    next: 'After execution, wait for sufficient observation data before interpreting an outcome.',
    truthBoundary:
      'Observed improvement after execution does not prove the workflow caused the improvement.',
  },
  platform: {
    eyebrow: 'PLATFORM',
    title: 'Understand whether FleetMind services and evidence pipelines are healthy.',
    explanation:
      'Platform views expose observability, SLO measurement, model operations, deployment and multi-asset capabilities.',
    primaryAction: 'Start with health and freshness indicators, then expand technical details only when something needs investigation.',
    next: 'Use deployment or observability details to troubleshoot a specific platform concern.',
  },
};

function currentDashboardState() {
  const main = document.querySelector<HTMLElement>('main[data-dashboard-page]');
  return {
    page: main?.dataset.dashboardPage ?? 'fleet',
    view: main?.dataset.dashboardView ?? 'overview',
  };
}

function clickButtonByText(selector: string, text: string) {
  const normalized = text.trim().toLowerCase();
  const button = Array.from(
    document.querySelectorAll<HTMLButtonElement>(selector),
  ).find(candidate => candidate.textContent?.trim().toLowerCase() === normalized);

  button?.click();
  return Boolean(button);
}

export function FleetMindExperience() {
  const [guideOpen, setGuideOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [dashboard, setDashboard] = useState(currentDashboardState);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const update = () => setDashboard(currentDashboardState());
    update();

    const observer = new MutationObserver(update);
    observer.observe(document.body, {
      subtree: true,
      attributes: true,
      attributeFilter: ['data-dashboard-page', 'data-dashboard-view'],
    });

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    function onGlobalKeyDown(event: globalThis.KeyboardEvent) {
      if (
        event.key === '/' &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey &&
        !(event.target instanceof HTMLInputElement) &&
        !(event.target instanceof HTMLTextAreaElement)
      ) {
        event.preventDefault();
        setSearchOpen(true);
        window.setTimeout(() => searchInputRef.current?.focus(), 0);
      }

      if (event.key === '?' && event.shiftKey) {
        setGuideOpen(true);
      }

      if (event.key === 'Escape') {
        setGuideOpen(false);
        setSearchOpen(false);
        setQuery('');
      }
    }

    window.addEventListener('keydown', onGlobalKeyDown);
    return () => window.removeEventListener('keydown', onGlobalKeyDown);
  }, []);

  const context = useMemo<ScreenContext>(() => {
    const page = PAGE_CONTEXT[dashboard.page] ?? PAGE_CONTEXT.fleet;
    const view = VIEW_CONTEXT[dashboard.view] ?? {};
    return { ...page, ...view };
  }, [dashboard]);

  const filteredDestinations = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return DESTINATIONS;

    return DESTINATIONS.filter(destination =>
      [
        destination.label,
        destination.group,
        destination.description,
        ...destination.keywords,
      ]
        .join(' ')
        .toLowerCase()
        .includes(normalized),
    );
  }, [query]);

  function navigate(destination: Destination) {
    const pageChanged = clickButtonByText('.sidebar nav button', destination.pageLabel);

    if (destination.viewLabel) {
      window.setTimeout(() => {
        clickButtonByText('[role="tab"].dashboardPageTab', destination.viewLabel!);
      }, pageChanged ? 40 : 0);
    }

    setSearchOpen(false);
    setQuery('');
  }

  function onSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter' && filteredDestinations[0]) {
      navigate(filteredDestinations[0]);
    }
  }

  function onQueryChange(event: ChangeEvent<HTMLInputElement>) {
    setQuery(event.target.value);
  }

  return (
    <>
      <div className="fmExperienceBar" aria-label="FleetMind quick access">
        <button
          type="button"
          className="fmExperienceSearchButton"
          onClick={() => {
            setSearchOpen(true);
            window.setTimeout(() => searchInputRef.current?.focus(), 0);
          }}
          aria-haspopup="dialog"
        >
          <Search size={15} aria-hidden="true" />
          <span>Search FleetMind</span>
          <kbd>/</kbd>
        </button>

        <div className="fmExperienceQuickLinks" aria-label="Primary destinations">
          {DESTINATIONS.filter(destination =>
            ['overview', 'fleet', 'diagnostics', 'actions', 'outcomes', 'platform'].includes(
              destination.id,
            ),
          ).map(destination => (
            <button
              key={destination.id}
              type="button"
              onClick={() => navigate(destination)}
            >
              {destination.label}
            </button>
          ))}
        </div>

        <button
          type="button"
          className="fmExperienceGuideButton"
          onClick={() => setGuideOpen(true)}
          aria-haspopup="dialog"
        >
          <CircleHelp size={15} aria-hidden="true" />
          <span>What can I do here?</span>
        </button>
      </div>

      <button
        type="button"
        className="fmExperienceFloatingHelp"
        onClick={() => setGuideOpen(true)}
        aria-label="Explain this screen and available actions"
      >
        <Sparkles size={16} aria-hidden="true" />
        <span>Explain this screen</span>
      </button>

      {guideOpen && (
        <div
          className="fmExperienceBackdrop"
          role="presentation"
          onMouseDown={event => {
            if (event.currentTarget === event.target) setGuideOpen(false);
          }}
        >
          <aside
            className="fmExperienceGuide"
            role="dialog"
            aria-modal="true"
            aria-labelledby="fm-guide-title"
          >
            <div className="fmExperienceGuideHeader">
              <div>
                <span>{context.eyebrow}</span>
                <h2 id="fm-guide-title">What can I do here?</h2>
              </div>
              <button
                type="button"
                onClick={() => setGuideOpen(false)}
                aria-label="Close screen guide"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>

            <section className="fmExperienceGuideHero">
              <h3>{context.title}</h3>
              <p>{context.explanation}</p>
            </section>

            <section className="fmExperienceGuideStep">
              <div className="fmExperienceStepIcon">
                <Wrench size={16} aria-hidden="true" />
              </div>
              <div>
                <span>What you can do</span>
                <p>{context.primaryAction}</p>
              </div>
            </section>

            <section className="fmExperienceGuideStep">
              <div className="fmExperienceStepIcon">
                <ArrowRight size={16} aria-hidden="true" />
              </div>
              <div>
                <span>What happens next</span>
                <p>{context.next}</p>
              </div>
            </section>

            {context.truthBoundary && (
              <section className="fmExperienceInterpretation">
                <ShieldCheck size={16} aria-hidden="true" />
                <div>
                  <span>Interpretation</span>
                  <p>{context.truthBoundary}</p>
                </div>
              </section>
            )}

            <div className="fmExperienceGuideActions">
              <button type="button" onClick={() => setSearchOpen(true)}>
                <Search size={15} aria-hidden="true" />
                Find another area
              </button>
              <button type="button" onClick={() => setGuideOpen(false)}>
                Continue here
                <ChevronRight size={15} aria-hidden="true" />
              </button>
            </div>
          </aside>
        </div>
      )}

      {searchOpen && (
        <div
          className="fmExperienceSearchBackdrop"
          role="presentation"
          onMouseDown={event => {
            if (event.currentTarget === event.target) {
              setSearchOpen(false);
              setQuery('');
            }
          }}
        >
          <section
            className="fmExperienceSearchDialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="fm-search-title"
          >
            <div className="fmExperienceSearchInputWrap">
              <Search size={18} aria-hidden="true" />
              <label id="fm-search-title" className="srOnly" htmlFor="fm-global-search">
                Search FleetMind destinations and capabilities
              </label>
              <input
                ref={searchInputRef}
                id="fm-global-search"
                value={query}
                onChange={onQueryChange}
                onKeyDown={onSearchKeyDown}
                placeholder="Search FleetMind: approvals, root cause, outcomes, platform..."
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => {
                  setSearchOpen(false);
                  setQuery('');
                }}
                aria-label="Close FleetMind search"
              >
                <X size={17} aria-hidden="true" />
              </button>
            </div>

            <div className="fmExperienceSearchMeta">
              <span>Navigate by intent, not by roadmap phase.</span>
              <span><kbd>Enter</kbd> opens the first result</span>
            </div>

            <div className="fmExperienceSearchResults">
              {filteredDestinations.length === 0 ? (
                <div className="fmExperienceNoResults">
                  <Search size={22} aria-hidden="true" />
                  <strong>No matching area</strong>
                  <span>Try vehicle, diagnostics, approvals, outcomes, model or platform.</span>
                </div>
              ) : (
                filteredDestinations.map(destination => (
                  <button
                    key={destination.id}
                    type="button"
                    className="fmExperienceDestination"
                    onClick={() => navigate(destination)}
                  >
                    <span className="fmExperienceDestinationIcon" aria-hidden="true">
                      {destination.id === 'overview' ? (
                        <Gauge size={17} />
                      ) : destination.id === 'intelligence' ? (
                        <BrainCircuit size={17} />
                      ) : destination.group === 'Advanced' ? (
                        <Layers3 size={17} />
                      ) : (
                        <Wrench size={17} />
                      )}
                    </span>
                    <span className="fmExperienceDestinationText">
                      <span>
                        <strong>{destination.label}</strong>
                        <small>{destination.group}</small>
                      </span>
                      <p>{destination.description}</p>
                    </span>
                    <ChevronRight size={17} aria-hidden="true" />
                  </button>
                ))
              )}
            </div>
          </section>
        </div>
      )}

      <div className="srOnly" aria-live="polite">
        Current FleetMind area: {context.eyebrow}. {context.title}
      </div>
    </>
  );
}
