import { ChevronRight, Home } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import './FleetMindBreadcrumbs.css';

type DashboardState = {
  page: string;
  view: string;
};

const PAGE_LABELS: Record<string, string> = {
  fleet: 'Fleet',
  incidents: 'Incidents',
  reliability: 'Reliability',
  cohorts: 'Cohorts',
  components: 'Components',
  firmware: 'Firmware',
  ml: 'Intelligence',
  diagnostics: 'Diagnostics',
};

const PAGE_BUTTON_LABELS: Record<string, string> = {
  fleet: 'Fleet Overview',
  incidents: 'Incidents',
  reliability: 'Reliability',
  cohorts: 'Cohorts',
  components: 'Components',
  firmware: 'Firmware',
  ml: 'Predictive ML',
  diagnostics: 'Root Cause',
};

const VIEW_LABELS: Record<string, string> = {
  overview: 'Overview',
  'fleet-health': 'Fleet Health',
  'emerging-signal': 'Emerging Signal',
  'incident-stream': 'Incident Stream',
  'cohort-analysis': 'Cohort Analysis',
  'observed-failures': 'Observed Failures',
  'survival-analysis': 'Survival Analysis',
  engineering: 'Engineering Interpretation',
  'cohort-scorecard': 'Cohort Scorecard',
  'early-warning': 'Early Warning',
  'failure-evaluation': 'Failure Evaluation',
  'revision-evidence': 'Revision Evidence',
  'component-health': 'Component Health',
  'matched-cohort': 'Matched Cohort',
  'hardware-software': 'Hardware × Software',
  'firmware-scorecard': 'Firmware Scorecard',
  method: 'Method',
  'interaction-matrix': 'Interaction Matrix',
  benchmark: 'Benchmark',
  'claim-policy': 'Claim Policy',
  'model-selection': 'Model Selection',
  'confusion-matrix': 'Confusion Matrix',
  explainability: 'Explainability',
  calibration: 'Calibration',
  'risk-history': 'Risk History',
  predictions: 'Predictions',
  hypotheses: 'Hypotheses',
  'incident-queue': 'Incident Queue',
  'vehicle-investigation': 'Investigate',
  cases: 'Cases',
  'fleet-patterns': 'Fleet Patterns',
  prognostics: 'Prognostics',
  automation: 'Automation',
  'fleet-decisions': 'Fleet Decisions',
  'vehicle-twin': 'Vehicle Twin',
  planning: 'Planning',
  'fleet-command': 'Actions & Outcomes',
  platform: 'Platform',
  transitions: 'Transitions',
  episodes: 'Episodes',
  events: 'Events',
  replay: 'Replay',
  'model-comparison': 'Model Comparison',
};

function currentDashboardState(): DashboardState {
  const main = document.querySelector<HTMLElement>('main[data-dashboard-page]');
  return {
    page: main?.dataset.dashboardPage ?? 'fleet',
    view: main?.dataset.dashboardView ?? 'overview',
  };
}

function clickButtonByText(selector: string, label: string) {
  const normalized = label.trim().toLowerCase();
  const button = Array.from(
    document.querySelectorAll<HTMLButtonElement>(selector),
  ).find(candidate => candidate.textContent?.trim().toLowerCase() === normalized);
  button?.click();
}

export function FleetMindBreadcrumbs() {
  const [dashboard, setDashboard] = useState(currentDashboardState);

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

  const pageLabel = PAGE_LABELS[dashboard.page] ?? dashboard.page;
  const viewLabel = useMemo(
    () => VIEW_LABELS[dashboard.view] ?? dashboard.view.replaceAll('-', ' '),
    [dashboard.view],
  );

  return (
    <nav className="fmBreadcrumbs" aria-label="Breadcrumb">
      <button
        type="button"
        onClick={() => clickButtonByText('.sidebar nav button', 'Fleet Overview')}
        aria-label="Go to FleetMind overview"
      >
        <Home size={12} aria-hidden="true" />
        <span>FleetMind</span>
      </button>

      <ChevronRight size={12} aria-hidden="true" />

      <button
        type="button"
        onClick={() =>
          clickButtonByText(
            '.sidebar nav button',
            PAGE_BUTTON_LABELS[dashboard.page] ?? 'Fleet Overview',
          )
        }
      >
        {pageLabel}
      </button>

      {dashboard.view !== 'overview' && (
        <>
          <ChevronRight size={12} aria-hidden="true" />
          <span aria-current="page">{viewLabel}</span>
        </>
      )}
    </nav>
  );
}
