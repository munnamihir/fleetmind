import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import { FleetMindBreadcrumbs } from './FleetMindBreadcrumbs';
import { FleetMindDemoBannerPortal } from './FleetMindDemoBannerPortal';
import { FleetMindExperience } from './FleetMindExperience';
import { FleetMindExperienceV2 } from './FleetMindExperienceV2';
import { FleetMindNavigationRail } from './FleetMindNavigationRail';
import { FleetMindPublicDemoExperience } from './FleetMindPublicDemo';
import { FleetMindSelectionInspector } from './FleetMindSelectionInspector';
import { FleetMindWorkInbox } from './FleetMindWorkInbox';
import './styles.css';
import './FleetMindExperienceV2Responsive.css';
import './DashboardPageTabsFlowFix.css';
import './FleetMindColdStart.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <FleetMindNavigationRail />
    <FleetMindExperience />
    <FleetMindExperienceV2 />
    <FleetMindPublicDemoExperience />
    <FleetMindDemoBannerPortal />
    <FleetMindBreadcrumbs />
    <FleetMindWorkInbox />
    <FleetMindSelectionInspector />
    <App />
  </React.StrictMode>,
);

const splash = document.getElementById('fleetmind-splash');

if (splash) {
  const reducedMotion = window.matchMedia(
    '(prefers-reduced-motion: reduce)',
  ).matches;

  const minimumVisibleMs = reducedMotion ? 100 : 1850;
  const fadeDurationMs = reducedMotion ? 110 : 540;

  window.setTimeout(() => {
    window.requestAnimationFrame(() => {
      splash.classList.add('fleetmind-splash--leaving');

      window.setTimeout(() => {
        splash.remove();
      }, fadeDurationMs);
    });
  }, minimumVisibleMs);
}
