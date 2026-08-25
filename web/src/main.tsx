import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
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
