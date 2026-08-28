import {
  Activity,
  AlertTriangle,
  BarChart3,
  BrainCircuit,
  CarFront,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Cpu,
  Gauge,
  Layers3,
  Radio,
  ServerCog,
  Sparkles,
  Wrench,
  Zap,
} from 'lucide-react';
import { type ReactNode, useEffect, useMemo, useState } from 'react';

import './FleetMindNavigationRail.css';

type Destination = {
  id: string;
  label: string;
  icon: ReactNode;
  pageLabel: string;
  viewLabel?: string;
  postLabels?: string[];
  description: string;
};

type DashboardState = {
  page: string;
  view: string;
};

const PRIMARY: Destination[] = [
  {
    id: 'overview',
    label: 'Overview',
    icon: <Gauge size={17} />,
    pageLabel: 'Fleet Overview',
    viewLabel: 'Overview',
    description: 'Command summary and fleet health.',
  },
  {
    id: 'fleet',
    label: 'Fleet',
    icon: <CarFront size={17} />,
    pageLabel: 'Fleet Overview',
    viewLabel: 'Fleet Health',
    description: 'Vehicles and health attention.',
  },
  {
    id: 'diagnostics',
    label: 'Diagnostics',
    icon: <Wrench size={17} />,
    pageLabel: 'Root Cause',
    viewLabel: 'Investigate',
    description: 'Vehicle investigation and cases.',
  },
  {
    id: 'actions',
    label: 'Actions',
    icon: <ClipboardCheck size={17} />,
    pageLabel: 'Root Cause',
    viewLabel: 'Actions & Outcomes',
    postLabels: ['Closed Loop', 'Recommendations'],
    description: 'Recommendations, approvals and execution.',
  },
  {
    id: 'outcomes',
    label: 'Outcomes',
    icon: <Activity size={17} />,
    pageLabel: 'Root Cause',
    viewLabel: 'Actions & Outcomes',
    postLabels: ['Closed Loop', 'Outcomes'],
    description: 'Post-execution observations and effectiveness.',
  },
  {
    id: 'intelligence',
    label: 'Intelligence',
    icon: <BrainCircuit size={17} />,
    pageLabel: 'Predictive ML',
    viewLabel: 'Overview',
    description: 'Models, benchmark evidence and prediction behavior.',
  },
  {
    id: 'platform',
    label: 'Platform',
    icon: <ServerCog size={17} />,
    pageLabel: 'Root Cause',
    viewLabel: 'Platform',
    description: 'System health, observability and model operations.',
  },
];

const ADVANCED: Destination[] = [
  {
    id: 'incidents',
    label: 'Incidents',
    icon: <AlertTriangle size={16} />,
    pageLabel: 'Incidents',
    viewLabel: 'Overview',
    description: 'Operational detections and observed outcomes.',
  },
  {
    id: 'reliability',
    label: 'Reliability',
    icon: <BarChart3 size={16} />,
    pageLabel: 'Reliability',
    viewLabel: 'Overview',
    description: 'Survival and early-warning evidence.',
  },
  {
    id: 'cohorts',
    label: 'Cohorts',
    icon: <Layers3 size={16} />,
    pageLabel: 'Cohorts',
    viewLabel: 'Overview',
    description: 'Population and revision comparisons.',
  },
  {
    id: 'components',
    label: 'Components',
    icon: <Cpu size={16} />,
    pageLabel: 'Components',
    viewLabel: 'Overview',
    description: 'Component health evidence.',
  },
  {
    id: 'firmware',
    label: 'Firmware',
    icon: <Zap size={16} />,
    pageLabel: 'Firmware',
    viewLabel: 'Overview',
    description: 'Matched software cohort evidence.',
  },
];

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
  return Boolean(button);
}

function navigate(destination: Destination) {
  const pageChanged = clickButtonByText('.sidebar nav button', destination.pageLabel);

  const openView = () => {
    if (destination.viewLabel) {
      clickButtonByText('[role="tab"].dashboardPageTab', destination.viewLabel);
    }

    if (destination.postLabels?.length) {
      destination.postLabels.forEach((label, index) => {
        window.setTimeout(() => {
          clickButtonByText('.fleetCommandOperations button', label);
        }, 90 + index * 90);
      });
    }
  };

  window.setTimeout(openView, pageChanged ? 45 : 0);
}

function activeDestination(state: DashboardState) {
  if (state.page === 'fleet') {
    return state.view === 'overview' ? 'overview' : 'fleet';
  }
  if (state.page === 'ml') return 'intelligence';
  if (state.page === 'diagnostics') {
    if (state.view === 'fleet-command') return 'actions';
    if (state.view === 'platform') return 'platform';
    return 'diagnostics';
  }
  if (ADVANCED.some(destination => destination.id === state.page)) {
    return state.page;
  }
  return 'overview';
}

export function FleetMindNavigationRail() {
  const [dashboard, setDashboard] = useState(currentDashboardState);
  const [advancedOpen, setAdvancedOpen] = useState(false);

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

  const active = useMemo(() => activeDestination(dashboard), [dashboard]);

  useEffect(() => {
    if (ADVANCED.some(destination => destination.id === active)) {
      setAdvancedOpen(true);
    }
  }, [active]);

  return (
    <aside className="fmNavigationRail" aria-label="FleetMind primary navigation">
      <div className="fmNavigationBrand">
        <div className="fmNavigationBrandMark">FM</div>
        <div>
          <b>FLEETMIND</b>
          <span>OPERATOR CONSOLE</span>
        </div>
      </div>

      <div className="fmNavigationSectionLabel">OPERATE</div>
      <nav className="fmNavigationPrimary" aria-label="Primary FleetMind areas">
        {PRIMARY.map(destination => (
          <button
            key={destination.id}
            type="button"
            className={active === destination.id ? 'active' : ''}
            onClick={() => navigate(destination)}
            title={destination.description}
          >
            <span className="fmNavigationIcon" aria-hidden="true">
              {destination.icon}
            </span>
            <span className="fmNavigationText">
              <strong>{destination.label}</strong>
              <small>{destination.description}</small>
            </span>
            {active === destination.id && (
              <ChevronRight className="fmNavigationActiveArrow" size={13} aria-hidden="true" />
            )}
          </button>
        ))}
      </nav>

      <div className="fmNavigationAdvanced">
        <button
          type="button"
          className="fmNavigationAdvancedToggle"
          aria-expanded={advancedOpen}
          onClick={() => setAdvancedOpen(value => !value)}
        >
          <span>
            <Layers3 size={15} aria-hidden="true" />
            Advanced
          </span>
          <ChevronDown
            size={14}
            aria-hidden="true"
            className={advancedOpen ? 'open' : ''}
          />
        </button>

        {advancedOpen && (
          <nav className="fmNavigationAdvancedList" aria-label="Advanced FleetMind areas">
            {ADVANCED.map(destination => (
              <button
                key={destination.id}
                type="button"
                className={active === destination.id ? 'active' : ''}
                onClick={() => navigate(destination)}
                title={destination.description}
              >
                <span className="fmNavigationIcon" aria-hidden="true">
                  {destination.icon}
                </span>
                <span>{destination.label}</span>
              </button>
            ))}
          </nav>
        )}
      </div>

      <div className="fmNavigationFooter">
        <div>
          <Radio size={13} aria-hidden="true" />
          <span>Existing APIs · live evidence</span>
        </div>
        <p>
          <Sparkles size={12} aria-hidden="true" />
          Select items to see context and next actions.
        </p>
      </div>
    </aside>
  );
}
