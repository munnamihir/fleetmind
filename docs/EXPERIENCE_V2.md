# FleetMind Experience V2

FleetMind Experience V2 is a product-wide UI layer that upgrades the operator console without changing the underlying diagnostic, recommendation, approval, execution, outcome, or platform semantics.

## Product principles

Every screen should make these questions easy to answer:

1. Where am I?
2. What is happening?
3. Why does it matter?
4. What can I do now?
5. What happens next?
6. What does the evidence *not* prove?

## Command surface

The top command bar provides:

- current operational area, page, and view
- command search
- API health and measured request latency
- My Work
- screen explanation
- density control
- focus mode
- local time

### Keyboard shortcuts

- `Cmd/Ctrl + K` — command search
- `Shift + W` — My Work
- `Shift + F` — focus mode
- `/` — existing FleetMind search shortcut
- `Esc` — close active search/help/work/context surfaces

## Density

Comfortable is the default. Compact reduces card padding, metric height, and row height for dense operational review. The preference is local to the browser and does not affect backend behavior.

## Focus mode

Focus mode removes the navigation rail and legacy hidden sidebar from layout flow and allows the current workspace to use the full viewport. It does not change the selected page, active run, or workflow state.

## Mobile experience

At mobile width, FleetMind exposes a bottom navigation surface for:

- Overview
- Fleet
- Diagnose
- Actions
- My Work

The command bar remains available for search and current workspace context.

## Design system

Experience V2 introduces shared tokens for:

- layered backgrounds
- surface hierarchy
- borders
- text hierarchy
- semantic attention states
- radius
- elevation
- focus states

Existing panels, metrics, tables, drawers, command search, My Work, selection inspector, and empty states inherit the same visual language.

## Accessibility

- keyboard-first command access
- visible focus states
- semantic buttons and navigation
- accessible labels for command actions
- non-color-only status text
- reduced-motion support
- responsive layout behavior

## Truth boundaries

Experience V2 does not change FleetMind's interpretation boundaries:

- attention is not physical failure probability
- correlation is not causality
- model confidence is not physical RUL
- workflow execution is not proof of physical repair
- post-execution improvement is not proof that maintenance caused the improvement
- human approval and explicit execution remain mandatory

## Reliability behavior

My Work resolves Fleet Command first and pins the outcome-summary request to the same diagnostic `run_id`. This prevents outcome reads from attempting to infer a different active run after simulator or application restarts.

## Validation

Run before merge:

```bash
PYTHONPATH="$PWD/services/common:$PWD/services/ml" \
python -m unittest discover -s tests -v

cd web
npm install
npm run build

cd ..
docker compose config >/dev/null && echo "Compose config OK"
docker compose up -d --build web
```

Then verify at `http://localhost:5173`:

- command bar renders without collision
- `Cmd/Ctrl + K` opens search
- My Work opens from the command bar
- focus mode expands the workspace
- density changes persist across refresh
- API status recovers after API restart
- desktop, tablet, and mobile layouts remain usable
- selection inspector remains available on selectable entities
- no unpinned outcome-summary 503 appears during normal My Work refresh
