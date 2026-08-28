# Phase 10 UX Validation Checklist

Use this checklist before moving the Phase 10 FleetMind UX Transformation PR out of draft.

## Automated gates

- [ ] `python -m unittest discover -s tests -v`
- [ ] `cd web && npm run build`
- [ ] `docker compose config >/dev/null`
- [ ] FleetMind CI is green

## Desktop UX

- [ ] FleetMind quick-access bar is visible without covering page content.
- [ ] `/` opens FleetMind search.
- [ ] Search Enter key opens the first result.
- [ ] Escape closes search, My Work, selection inspector and screen guide.
- [ ] Primary destinations navigate to the expected existing FleetMind page/view.
- [ ] Breadcrumbs update when the dashboard page/view changes.
- [ ] `What can I do here?` reflects the active page/view.
- [ ] Diagnostics shows Overview, Investigate, Cases, Actions & Outcomes and Platform as primary paths.
- [ ] Specialist diagnostic routes remain reachable from Advanced views.

## Selection UX

- [ ] Clicking an alert opens the contextual inspector.
- [ ] Clicking a Fleet Command vehicle mini-row opens the contextual inspector.
- [ ] Clicking a cohort row opens the contextual inspector.
- [ ] Clicking an observed failure row opens the contextual inspector.
- [ ] Inspector explains why the selected item matters.
- [ ] Inspector explains the next recommended operator step.
- [ ] Inspector displays the relevant interpretation boundary.
- [ ] Inspector actions navigate to the expected existing FleetMind area.

## My Work

- [ ] My Work loads Fleet Command summary.
- [ ] My Work loads Decision Queue summary.
- [ ] My Work loads Outcome Summary.
- [ ] Approval-required count is displayed.
- [ ] Execution-ready count is displayed.
- [ ] Unassigned-active count is displayed.
- [ ] Overdue-review count is displayed.
- [ ] Worsening-outcome count is displayed.
- [ ] My Work remains informational/navigation-only and does not mutate lifecycle state.

## Accessibility

- [ ] Search is keyboard operable.
- [ ] Guide, My Work and inspector have accessible names.
- [ ] Close controls have explicit labels.
- [ ] Visible focus indicators are present.
- [ ] Status meaning is not communicated by color alone.
- [ ] Reduced-motion preference does not depend on animated transitions.
- [ ] Screen-reader live text identifies the active FleetMind area.

## Responsive behavior

- [ ] 1440px desktop layout is usable.
- [ ] 1024px compact sidebar layout is usable.
- [ ] 768px tablet layout is usable.
- [ ] 390px mobile layout keeps search/work/help reachable.
- [ ] Drawers do not overflow the viewport.

## Truth-boundary verification

- [ ] Attention is described as prioritization, not physical failure probability.
- [ ] Cohort differences are not described as causal proof.
- [ ] Model horizon/confidence is not described as physical RUL.
- [ ] Workflow execution is not described as physical repair.
- [ ] Outcome improvement is not described as proof that maintenance caused the improvement.
- [ ] Human approval and explicit execution remain mandatory.
