import {
  ArrowRight,
  CircleDot,
  ExternalLink,
  SearchCheck,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useEffect, useState } from 'react';

import './FleetMindSelectionInspector.css';

type InspectorAction = {
  label: string;
  pageLabel: string;
  viewLabel?: string;
};

type InspectorSelection = {
  kind: string;
  title: string;
  subtitle: string;
  details: Array<{ label: string; value: string }>;
  why: string;
  next: string;
  interpretation?: string;
  actions: InspectorAction[];
};

const SELECTABLE = [
  '.fleetOpsVehicleMini',
  '.alertRow',
  '.cohortRow',
  '.failureRow',
  '.fleetOpsCohortRow',
  '[data-vehicle-id]',
  '[data-case-id]',
  '[data-recommendation-id]',
].join(',');

function text(element: Element | null | undefined) {
  return element?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
}

function clickButtonByText(selector: string, label: string) {
  const normalized = label.trim().toLowerCase();
  const button = Array.from(
    document.querySelectorAll<HTMLButtonElement>(selector),
  ).find(candidate => candidate.textContent?.trim().toLowerCase() === normalized);

  button?.click();
  return Boolean(button);
}

function navigate(action: InspectorAction) {
  const changed = clickButtonByText('.sidebar nav button', action.pageLabel);
  if (action.viewLabel) {
    window.setTimeout(() => {
      clickButtonByText('[role="tab"].dashboardPageTab', action.viewLabel!);
    }, changed ? 40 : 0);
  }
}

function selectionFromElement(element: Element): InspectorSelection | null {
  if (element.matches('.fleetOpsVehicleMini')) {
    const vehicleId = text(element.querySelector('b')) || 'Selected vehicle';
    const classification = text(element.querySelector('span')) || 'Vehicle attention';
    const attention = text(element.querySelector('strong')) || '—';

    return {
      kind: 'Vehicle',
      title: vehicleId,
      subtitle: classification,
      details: [
        { label: 'Attention score', value: attention },
        { label: 'Source', value: 'Fleet Command queue' },
      ],
      why:
        'This vehicle appears in an operator queue because current diagnostic evidence warrants review. The queue helps prioritize attention; it does not confirm a physical failure.',
      next:
        'Open the vehicle investigation to review chronology, hypotheses and supporting evidence before choosing an operational action.',
      interpretation:
        'Attention priority is an operational ranking, not a physical failure probability.',
      actions: [
        {
          label: 'Investigate vehicle',
          pageLabel: 'Root Cause',
          viewLabel: 'Investigate',
        },
        {
          label: 'Review actions',
          pageLabel: 'Root Cause',
          viewLabel: 'Actions & Outcomes',
        },
      ],
    };
  }

  if (element.matches('.alertRow')) {
    const vehicleId = text(element.querySelector('.alertMain b')) || 'Selected alert';
    const alertTitle = text(element.querySelector('.alertMain span')) || 'Anomaly detection';
    const context = text(element.querySelector('.alertMain small')) || 'Current fleet evidence';
    const risk = text(element.querySelector('.risk')) || '—';

    return {
      kind: 'Attention signal',
      title: vehicleId,
      subtitle: alertTitle,
      details: [
        { label: 'Context', value: context },
        { label: 'Displayed attention', value: risk },
      ],
      why:
        'FleetMind surfaced this signal because current telemetry crossed an operational attention threshold.',
      next:
        'Review the vehicle-level diagnostic evidence and look for supporting and contradictory signals before escalating.',
      interpretation:
        'An alert score prioritizes review. It is not proof that the vehicle or component has failed.',
      actions: [
        {
          label: 'Review diagnostics',
          pageLabel: 'Root Cause',
          viewLabel: 'Investigate',
        },
        {
          label: 'Open incidents',
          pageLabel: 'Incidents',
          viewLabel: 'Incident Stream',
        },
      ],
    };
  }

  if (element.matches('.cohortRow, .fleetOpsCohortRow')) {
    const label = text(element.querySelector('b')) || 'Selected cohort';
    const values = Array.from(element.querySelectorAll('span, strong'))
      .map(node => text(node))
      .filter(Boolean)
      .slice(0, 4);

    return {
      kind: 'Cohort',
      title: label,
      subtitle: 'Population-level evidence',
      details: values.map((value, index) => ({
        label: index === 0 ? 'Population context' : `Evidence ${index + 1}`,
        value,
      })),
      why:
        'This cohort groups comparable fleet observations so you can see whether a pattern is concentrated in a particular population.',
      next:
        'Use the cohort difference to narrow investigation, then inspect vehicle or diagnostic evidence before making a causal interpretation.',
      interpretation:
        'A cohort difference is descriptive evidence. Correlation across a population does not establish causality.',
      actions: [
        {
          label: 'Compare cohorts',
          pageLabel: 'Cohorts',
          viewLabel: 'Overview',
        },
        {
          label: 'Investigate diagnostics',
          pageLabel: 'Root Cause',
          viewLabel: 'Overview',
        },
      ],
    };
  }

  if (element.matches('.failureRow')) {
    const values = Array.from(element.querySelectorAll('b, span, strong'))
      .map(node => text(node))
      .filter(Boolean);

    return {
      kind: 'Observed outcome',
      title: values[0] ?? 'Recorded failure',
      subtitle: values[1] ?? 'Observed component outcome',
      details: values.slice(2, 6).map((value, index) => ({
        label: `Recorded evidence ${index + 1}`,
        value,
      })),
      why:
        'This row represents a recorded observed outcome and can be used to evaluate reliability and early-warning behavior.',
      next:
        'Compare the observed outcome with earlier warnings and diagnostic evidence to understand what was known before the event.',
      actions: [
        {
          label: 'Open reliability',
          pageLabel: 'Reliability',
          viewLabel: 'Failure Evaluation',
        },
      ],
    };
  }

  const vehicleId = element.getAttribute('data-vehicle-id');
  const caseId = element.getAttribute('data-case-id');
  const recommendationId = element.getAttribute('data-recommendation-id');
  const entityId = vehicleId ?? caseId ?? recommendationId;

  if (entityId) {
    const kind = vehicleId ? 'Vehicle' : caseId ? 'Diagnostic case' : 'Recommendation';
    return {
      kind,
      title: entityId,
      subtitle: 'FleetMind entity',
      details: [],
      why: 'This entity is connected to FleetMind diagnostic and operational evidence.',
      next: 'Open the related workspace to review its evidence, current state and available human actions.',
      actions: [
        {
          label: 'Open diagnostics',
          pageLabel: 'Root Cause',
          viewLabel: vehicleId ? 'Investigate' : caseId ? 'Cases' : 'Actions & Outcomes',
        },
      ],
    };
  }

  return null;
}

export function FleetMindSelectionInspector() {
  const [selection, setSelection] = useState<InspectorSelection | null>(null);

  useEffect(() => {
    function onClick(event: MouseEvent) {
      const target = event.target;
      if (!(target instanceof Element)) return;

      const selected = target.closest(SELECTABLE);
      if (!selected) return;

      const nextSelection = selectionFromElement(selected);
      if (nextSelection) setSelection(nextSelection);
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setSelection(null);
    }

    document.addEventListener('click', onClick, true);
    window.addEventListener('keydown', onKeyDown);

    return () => {
      document.removeEventListener('click', onClick, true);
      window.removeEventListener('keydown', onKeyDown);
    };
  }, []);

  if (!selection) return null;

  return (
    <aside
      className="fmSelectionInspector"
      role="complementary"
      aria-label={`Selected ${selection.kind}: ${selection.title}`}
    >
      <div className="fmSelectionInspectorHead">
        <div>
          <span>{selection.kind}</span>
          <h2>{selection.title}</h2>
          <p>{selection.subtitle}</p>
        </div>
        <button
          type="button"
          onClick={() => setSelection(null)}
          aria-label="Close selected item inspector"
        >
          <X size={17} aria-hidden="true" />
        </button>
      </div>

      {selection.details.length > 0 && (
        <div className="fmSelectionDetails">
          {selection.details.map(detail => (
            <div key={`${detail.label}-${detail.value}`}>
              <span>{detail.label}</span>
              <strong>{detail.value}</strong>
            </div>
          ))}
        </div>
      )}

      <section className="fmSelectionSection">
        <SearchCheck size={16} aria-hidden="true" />
        <div>
          <span>Why does this matter?</span>
          <p>{selection.why}</p>
        </div>
      </section>

      <section className="fmSelectionSection">
        <CircleDot size={16} aria-hidden="true" />
        <div>
          <span>What should I do next?</span>
          <p>{selection.next}</p>
        </div>
      </section>

      {selection.interpretation && (
        <section className="fmSelectionInterpretation">
          <ShieldCheck size={15} aria-hidden="true" />
          <div>
            <span>Interpretation</span>
            <p>{selection.interpretation}</p>
          </div>
        </section>
      )}

      <div className="fmSelectionActions" aria-label="Available actions">
        {selection.actions.map((action, index) => (
          <button
            key={`${action.pageLabel}-${action.viewLabel ?? ''}`}
            type="button"
            className={index === 0 ? 'primary' : ''}
            onClick={() => navigate(action)}
          >
            {action.label}
            {index === 0 ? (
              <ArrowRight size={15} aria-hidden="true" />
            ) : (
              <ExternalLink size={14} aria-hidden="true" />
            )}
          </button>
        ))}
      </div>
    </aside>
  );
}
