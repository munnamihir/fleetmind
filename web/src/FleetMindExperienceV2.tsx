import {
  Activity,
  CarFront,
  CircleHelp,
  ClipboardCheck,
  Command,
  Gauge,
  Inbox,
  Maximize2,
  Minimize2,
  Search,
  SlidersHorizontal,
  Wifi,
  WifiOff,
  Wrench,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import './FleetMindExperienceV2.css';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

type Density = 'comfortable' | 'compact';

type DashboardState = {
  page: string;
  view: string;
};

type MobileDestination = {
  id: string;
  label: string;
  pageLabel: string;
  viewLabel: string;
  icon: React.ReactNode;
};

const PAGE_NAMES: Record<string, string> = {
  fleet: 'Fleet',
  incidents: 'Incidents',
  reliability: 'Reliability',
  cohorts: 'Cohorts',
  components: 'Components',
  firmware: 'Firmware',
  ml: 'Intelligence',
  diagnostics: 'Diagnostics',
};

const AREA_NAMES: Record<string, string> = {
  fleet: 'OPERATE',
  incidents: 'OPERATE',
  reliability: 'ANALYZE',
  cohorts: 'ANALYZE',
  components: 'ANALYZE',
  firmware: 'ANALYZE',
  ml: 'INTELLIGENCE',
  diagnostics: 'INVESTIGATE',
};

const MOBILE_DESTINATIONS: MobileDestination[] = [
  {
    id: 'overview',
    label: 'Overview',
    pageLabel: 'Fleet Overview',
    viewLabel: 'Overview',
    icon: <Gauge size={17} />,
  },
  {
    id: 'fleet',
    label: 'Fleet',
    pageLabel: 'Fleet Overview',
    viewLabel: 'Fleet Health',
    icon: <CarFront size={17} />,
  },
  {
    id: 'diagnostics',
    label: 'Diagnose',
    pageLabel: 'Root Cause',
    viewLabel: 'Investigate',
    icon: <Wrench size={17} />,
  },
  {
    id: 'actions',
    label: 'Actions',
    pageLabel: 'Root Cause',
    viewLabel: 'Actions & Outcomes',
    icon: <ClipboardCheck size={17} />,
  },
];

function currentDashboardState(): DashboardState {
  const main = document.querySelector<HTMLElement>('main[data-dashboard-page]');
  return {
    page: main?.dataset.dashboardPage ?? 'fleet',
    view: main?.dataset.dashboardView ?? 'overview',
  };
}

function humanize(value: string) {
  return value
    .replaceAll('-', ' ')
    .replace(/\b\w/g, character => character.toUpperCase());
}

function clickButtonByText(selector: string, label: string) {
  const normalized = label.trim().toLowerCase();
  const button = Array.from(
    document.querySelectorAll<HTMLButtonElement>(selector),
  ).find(candidate => candidate.textContent?.trim().toLowerCase() === normalized);
  button?.click();
  return Boolean(button);
}

function navigate(destination: MobileDestination) {
  const pageChanged = clickButtonByText('.sidebar nav button', destination.pageLabel);
  window.setTimeout(() => {
    clickButtonByText('[role="tab"].dashboardPageTab', destination.viewLabel);
  }, pageChanged ? 45 : 0);
}

function trigger(selector: string) {
  document.querySelector<HTMLButtonElement>(selector)?.click();
}

function readStoredDensity(): Density {
  const stored = window.localStorage.getItem('fleetmind-density');
  return stored === 'compact' ? 'compact' : 'comfortable';
}

export function FleetMindExperienceV2() {
  const [dashboard, setDashboard] = useState(currentDashboardState);
  const [density, setDensity] = useState<Density>(readStoredDensity);
  const [focusMode, setFocusMode] = useState(false);
  const [apiHealthy, setApiHealthy] = useState<boolean | null>(null);
  const [apiLatency, setApiLatency] = useState<number | null>(null);
  const [now, setNow] = useState(() => new Date());

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
    document.documentElement.dataset.fmDensity = density;
    window.localStorage.setItem('fleetmind-density', density);
  }, [density]);

  useEffect(() => {
    document.documentElement.dataset.fmFocus = focusMode ? 'true' : 'false';
    return () => {
      delete document.documentElement.dataset.fmFocus;
    };
  }, [focusMode]);

  const checkHealth = useCallback(async () => {
    const started = performance.now();
    try {
      const response = await fetch(`${API}/health`, { cache: 'no-store' });
      setApiHealthy(response.ok);
      setApiLatency(Math.max(1, Math.round(performance.now() - started)));
    } catch {
      setApiHealthy(false);
      setApiLatency(null);
    }
  }, []);

  useEffect(() => {
    void checkHealth();
    const timer = window.setInterval(() => void checkHealth(), 15000);
    return () => window.clearInterval(timer);
  }, [checkHealth]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const editable =
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement ||
        (event.target instanceof HTMLElement && event.target.isContentEditable);

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        trigger('.fmExperienceSearchButton');
        return;
      }

      if (editable) return;

      if (event.shiftKey && event.key.toLowerCase() === 'w') {
        event.preventDefault();
        trigger('.fmWorkInboxLauncher');
      }

      if (event.shiftKey && event.key.toLowerCase() === 'f') {
        event.preventDefault();
        setFocusMode(value => !value);
      }
    }

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const activeMobile = useMemo(() => {
    if (dashboard.page === 'fleet') {
      return dashboard.view === 'overview' ? 'overview' : 'fleet';
    }
    if (dashboard.page === 'diagnostics') {
      return dashboard.view === 'fleet-command' ? 'actions' : 'diagnostics';
    }
    return '';
  }, [dashboard]);

  const pageName = PAGE_NAMES[dashboard.page] ?? humanize(dashboard.page);
  const viewName = humanize(dashboard.view);
  const areaName = AREA_NAMES[dashboard.page] ?? 'OPERATE';

  return (
    <>
      <div className="fmV2Ambient" aria-hidden="true" />

      <div className="fmV2CommandBar" aria-label="FleetMind command bar">
        <div className="fmV2Location">
          <span className="fmV2LocationMark" aria-hidden="true">
            <Activity size={15} />
          </span>
          <span className="fmV2LocationCopy">
            <small>{areaName}</small>
            <strong>
              {pageName}
              <i>/</i>
              <span>{viewName}</span>
            </strong>
          </span>
        </div>

        <button
          type="button"
          className="fmV2Search"
          onClick={() => trigger('.fmExperienceSearchButton')}
          aria-label="Open FleetMind command search"
        >
          <Search size={15} aria-hidden="true" />
          <span>Search vehicles, cases, actions, models…</span>
          <kbd>⌘ K</kbd>
        </button>

        <div className="fmV2CommandActions">
          <button
            type="button"
            className={`fmV2Pulse ${apiHealthy === false ? 'offline' : ''}`}
            onClick={() => void checkHealth()}
            title="API connection status. Select to refresh."
          >
            {apiHealthy === false ? (
              <WifiOff size={14} aria-hidden="true" />
            ) : (
              <Wifi size={14} aria-hidden="true" />
            )}
            <span>{apiHealthy === false ? 'API OFFLINE' : apiHealthy == null ? 'CHECKING' : 'API LIVE'}</span>
            {apiLatency != null && <small>{apiLatency}ms</small>}
          </button>

          <button
            type="button"
            className="fmV2IconAction"
            onClick={() => trigger('.fmWorkInboxLauncher')}
            title="My Work · Shift + W"
            aria-label="Open My Work"
          >
            <Inbox size={15} aria-hidden="true" />
          </button>

          <button
            type="button"
            className="fmV2IconAction"
            onClick={() => trigger('.fmExperienceGuideButton')}
            title="Explain this screen"
            aria-label="Explain this screen"
          >
            <CircleHelp size={15} aria-hidden="true" />
          </button>

          <button
            type="button"
            className="fmV2IconAction"
            onClick={() => setDensity(value => (value === 'comfortable' ? 'compact' : 'comfortable'))}
            title={`Density: ${density}`}
            aria-label={`Switch from ${density} density`}
          >
            <SlidersHorizontal size={15} aria-hidden="true" />
          </button>

          <button
            type="button"
            className={`fmV2IconAction ${focusMode ? 'active' : ''}`}
            onClick={() => setFocusMode(value => !value)}
            title="Focus mode · Shift + F"
            aria-pressed={focusMode}
            aria-label="Toggle focus mode"
          >
            {focusMode ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </button>

          <div className="fmV2Clock" title={now.toLocaleString()}>
            <Command size={13} aria-hidden="true" />
            <span>{now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
        </div>
      </div>

      <nav className="fmV2MobileNav" aria-label="FleetMind mobile navigation">
        {MOBILE_DESTINATIONS.map(destination => (
          <button
            key={destination.id}
            type="button"
            className={activeMobile === destination.id ? 'active' : ''}
            onClick={() => navigate(destination)}
          >
            <span aria-hidden="true">{destination.icon}</span>
            <small>{destination.label}</small>
          </button>
        ))}
        <button type="button" onClick={() => trigger('.fmWorkInboxLauncher')}>
          <span aria-hidden="true"><Inbox size={17} /></span>
          <small>My Work</small>
        </button>
      </nav>
    </>
  );
}
