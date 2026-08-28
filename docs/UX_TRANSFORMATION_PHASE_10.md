# Phase 10 — FleetMind UX Transformation

Phase 10 is a single cohesive user-experience transformation phase. It does not split the redesign into independent delivery phases and it does not replace FleetMind's existing diagnostic, closed-loop, model-operations, observability, or multi-asset capabilities.

The goal is to make the existing platform understandable and actionable to an operator who does not know the internal roadmap or service architecture.

## Primary UX questions

Every major screen and selected entity should help answer:

1. Where am I?
2. What am I looking at?
3. Why does it matter?
4. What needs attention?
5. What can I do now?
6. What happens next?
7. What must not be inferred from this evidence?

## Information architecture

The primary operator mental model is:

- Overview
- Fleet
- Diagnostics
- Actions
- Outcomes
- Intelligence
- Platform

Specialist engineering views remain available through Advanced views rather than being removed.

## Scope

The following workstreams are all part of this one Phase 10 implementation:

- Navigation and information architecture
- Command Center / operator overview
- Global search and capability navigation
- Universal entity selection inspector
- Contextual actions
- Workflow guidance and next-step explanations
- Vehicle experience
- Fleet experience
- Diagnostic experience
- Root-cause and evidence experience
- Recommendations and approvals
- Outcomes and effectiveness
- Policy Lab
- Shadow experiments
- Model Ops
- Platform health
- My Work / operator inbox
- Related entity navigation
- Tables, filters and search affordances
- Loading, error and empty states
- Accessibility
- Responsive behavior
- Terminology and interpretation help
- UX consistency and visual polish

## Current implementation foundation

The initial Phase 10 implementation adds the following cross-application UX layer without changing existing backend workflow semantics:

### Quick access and intent-based navigation

A persistent FleetMind quick-access bar exposes user-oriented destinations and a global capability search. Search is intentionally based on operator intent rather than roadmap phase names.

Keyboard shortcut:

- `/` opens FleetMind search.
- `Escape` closes open Phase 10 overlays.

### Screen guide

A `What can I do here?` guide derives the active dashboard page and view from the existing dashboard state and explains:

- the purpose of the current screen,
- the recommended operator action,
- what happens next,
- and the relevant interpretation boundary.

### Simplified Diagnostics navigation

Diagnostics no longer presents every specialist view as an equally weighted tab.

Primary paths:

- Overview
- Investigate
- Cases
- Actions & Outcomes
- Platform

Existing specialist routes remain available from `Advanced views`.

### Contextual selection inspector

High-value selectable rows can open a contextual inspector that explains:

- what was selected,
- why it matters,
- what the operator should do next,
- the interpretation boundary,
- and related navigation actions.

The initial selectors cover operator-queue vehicles, alerts, cohorts, observed failures, and entities carrying FleetMind data attributes. This is intended to expand as additional screens adopt explicit entity data attributes.

### My Work operator inbox

`My Work` aggregates existing operational evidence from Fleet Command, Decision Queue and Outcome Summary APIs, including:

- approval-required recommendations,
- approved/execution-ready recommendations,
- unassigned active queue records,
- overdue review targets,
- worsening observed outcomes,
- and fleet attention counts.

The inbox is informational and navigational. It does not bypass human-control transitions.

### Breadcrumbs

The active dashboard page and view are exposed as breadcrumbs so an operator can understand location and return to the parent area.

## Human-control and truth boundaries

Phase 10 must not change the following system semantics:

- Recommendations remain human-gated.
- Approval is never automatic.
- Execution is never automatic.
- Shadow policy evaluation does not write recommendations, workflows or physical actions.
- Attention is not physical failure probability.
- Correlation is not causality.
- Model confidence is not physical remaining useful life.
- Workflow execution does not confirm physical repair.
- Observed improvement after execution does not prove the workflow caused the improvement.

The UI should make these boundaries easier to understand, not hide them.

## Accessibility requirements

Phase 10 is not complete if accessibility is postponed to a later phase.

Required behavior includes:

- keyboard-operable navigation,
- visible focus indicators,
- semantic buttons and landmarks,
- accessible dialogs and complementary regions,
- useful ARIA labels,
- screen-reader live context where appropriate,
- status communication that does not rely on color alone,
- reduced-motion compatibility,
- responsive behavior,
- and understandable empty/error states.

## Responsive model

Desktop:

- Existing application navigation
- Main content
- Phase 10 quick-access layer
- Contextual inspector / operator drawer when invoked

Tablet:

- Compact navigation
- Main content
- Overlay drawers for context

Mobile:

- Compact quick access
- Main content
- Bottom-oriented work/help/selection surfaces

## Entity interaction rule

The long-term Phase 10 interaction rule is:

- Select an entity to inspect it without losing context.
- Use an explicit action to navigate to a full investigation or workflow.

Entities should progressively adopt explicit attributes such as:

- `data-vehicle-id`
- `data-case-id`
- `data-recommendation-id`

This avoids coupling the inspector to visual text and makes related navigation deterministic.

## Definition of Done

Phase 10 is complete when all major operator-facing areas satisfy the following:

- [ ] Primary navigation is organized around operator intent rather than roadmap phases.
- [ ] Every major entity can be selected or explicitly opened for inspection.
- [ ] Selection explains why the entity matters.
- [ ] Selection shows available actions.
- [ ] Selection explains the next workflow step.
- [ ] Related entities can be reached without losing orientation.
- [ ] Global search supports navigation and important entity discovery.
- [ ] Breadcrumbs identify the current location.
- [ ] My Work aggregates human-required tasks.
- [ ] Vehicle detail connects telemetry, diagnostics, actions, outcomes and history.
- [ ] Recommendation lifecycle is visually understandable.
- [ ] Approval-required and execution-ready states explain their allowed actions.
- [ ] Root-cause evidence distinguishes supporting and contradictory evidence.
- [ ] Outcomes clearly separate observation from causal interpretation.
- [ ] Policy and shadow interfaces explain write/no-write behavior.
- [ ] Model views explain qualification, confidence and drift without overstating physical meaning.
- [ ] Platform views lead with service health/freshness before low-level implementation detail.
- [ ] Tables provide understandable filtering/search affordances where operationally useful.
- [ ] Empty states explain why data is absent and what creates it.
- [ ] Error states provide a recovery action and keep technical details secondary.
- [ ] Loading states communicate useful progress where progress is measurable.
- [ ] Keyboard navigation is supported across Phase 10 controls.
- [ ] Focus states are visible.
- [ ] Dialogs/drawers are labeled and dismissible.
- [ ] Mobile/tablet behavior remains usable.
- [ ] Existing backend APIs and closed-loop human-control semantics remain unchanged.
- [ ] Existing automated tests remain green.
- [ ] Frontend TypeScript/Vite production build passes.

## Validation

At minimum, Phase 10 changes must pass:

```bash
python -m unittest discover -s tests -v
cd web && npm run build
```

and the existing FleetMind CI workflow must remain green before merge.
