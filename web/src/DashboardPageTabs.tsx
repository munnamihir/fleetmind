import { type KeyboardEvent } from 'react';

import './DashboardPageTabs.css';


export type DashboardPage =
  | 'fleet'
  | 'incidents'
  | 'reliability'
  | 'cohorts'
  | 'components'
  | 'firmware'
  | 'ml'
  | 'diagnostics';

type DashboardTab = {
  id: string;
  label: string;
};

export const PAGE_TABS: Record<DashboardPage, DashboardTab[]> = {
  fleet: [
    { id: 'overview', label: 'Overview' },
    { id: 'fleet-health', label: 'Fleet Health' },
    { id: 'emerging-signal', label: 'Emerging Signal' },
    { id: 'incident-stream', label: 'Incident Stream' },
    { id: 'cohort-analysis', label: 'Cohort Analysis' },
  ],
  incidents: [
    { id: 'overview', label: 'Overview' },
    { id: 'incident-stream', label: 'Incident Stream' },
    { id: 'observed-failures', label: 'Observed Failures' },
  ],
  reliability: [
    { id: 'overview', label: 'Overview' },
    { id: 'survival-analysis', label: 'Survival Analysis' },
    { id: 'engineering', label: 'Engineering Interpretation' },
    { id: 'cohort-scorecard', label: 'Cohort Scorecard' },
    { id: 'early-warning', label: 'Early Warning' },
    { id: 'failure-evaluation', label: 'Failure Evaluation' },
  ],
  cohorts: [
    { id: 'overview', label: 'Overview' },
    { id: 'revision-evidence', label: 'Pump Revision Evidence' },
  ],
  components: [
    { id: 'overview', label: 'Overview' },
    { id: 'component-health', label: 'Component Health' },
  ],
  firmware: [
    { id: 'overview', label: 'Overview' },
    { id: 'matched-cohort', label: 'Matched Cohort' },
    { id: 'hardware-software', label: 'Hardware × Software' },
    { id: 'firmware-scorecard', label: 'Firmware Scorecard' },
    { id: 'method', label: 'Method' },
    { id: 'interaction-matrix', label: 'Interaction Matrix' },
  ],
  ml: [
    { id: 'overview', label: 'Overview' },
    { id: 'benchmark', label: 'Benchmark' },
    { id: 'claim-policy', label: 'Claim Policy' },
    { id: 'model-selection', label: 'Model Selection' },
    { id: 'confusion-matrix', label: 'Confusion Matrix' },
    { id: 'explainability', label: 'Explainability' },
    { id: 'calibration', label: 'Calibration' },
    { id: 'risk-history', label: 'Risk History' },
    { id: 'predictions', label: 'Predictions' },
  ],
  diagnostics: [
    { id: 'overview', label: 'Overview' },
    { id: 'hypotheses', label: 'Hypotheses' },
    { id: 'benchmark', label: 'Benchmark' },
    { id: 'incident-queue', label: 'Incident Queue' },
    { id: 'vehicle-investigation', label: 'Vehicle Investigation' },
    { id: 'cases', label: 'Cases' },
    { id: 'fleet-patterns', label: 'Fleet Patterns' },
    { id: 'prognostics', label: 'Prognostics' },
    { id: 'automation', label: 'Automation' },
    { id: 'fleet-decisions', label: 'Fleet Decisions' },
    { id: 'vehicle-twin', label: 'Vehicle Twin' },
    { id: 'planning', label: 'Planning' },
    { id: 'fleet-command', label: 'Fleet Command' },
    { id: 'transitions', label: 'Transitions' },
    { id: 'episodes', label: 'Episodes' },
    { id: 'events', label: 'Events' },
    { id: 'replay', label: 'Replay' },
    { id: 'model-comparison', label: 'Model Comparison' },
  ],
};

export const DEFAULT_DASHBOARD_VIEW: Record<DashboardPage, string> = {
  fleet: 'overview',
  incidents: 'overview',
  reliability: 'overview',
  cohorts: 'overview',
  components: 'overview',
  firmware: 'overview',
  ml: 'overview',
  diagnostics: 'overview',
};


export function DashboardPageTabs({
  page,
  active,
  onChange,
}: {
  page: DashboardPage;
  active: string;
  onChange: (view: string) => void;
}) {
  const tabs = PAGE_TABS[page];
  const activeIndex = Math.max(
    0,
    tabs.findIndex(tab => tab.id === active),
  );

  function onKeyDown(
    event: KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) {
    let target = index;

    if (event.key === 'ArrowRight') {
      target = (index + 1) % tabs.length;
    } else if (event.key === 'ArrowLeft') {
      target = (index - 1 + tabs.length) % tabs.length;
    } else if (event.key === 'Home') {
      target = 0;
    } else if (event.key === 'End') {
      target = tabs.length - 1;
    } else {
      return;
    }

    event.preventDefault();
    onChange(tabs[target].id);

    const buttons = event.currentTarget
      .parentElement
      ?.querySelectorAll<HTMLButtonElement>('[role="tab"]');

    buttons?.[target]?.focus();
  }

  return (
    <div
      className={`dashboardPageTabs dashboardPageTabs-${page}`}
      role="tablist"
      aria-label={`${page} dashboard views`}
    >
      {tabs.map((tab, index) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={active === tab.id}
          tabIndex={activeIndex === index ? 0 : -1}
          className={
            active === tab.id
              ? 'dashboardPageTab active'
              : 'dashboardPageTab'
          }
          onClick={() => onChange(tab.id)}
          onKeyDown={event => onKeyDown(event, index)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
