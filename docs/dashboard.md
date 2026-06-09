# Dashboard

The dashboard is currently a static frontend served by FastAPI.

## Main Surfaces

- Connect: paste model/API/WRDS credentials and get redacted status.
- OS Capabilities: inspect local capability plugins, permissions, and enabled
  state.
- OS Plan: see inferred task type, required capabilities, missing connections,
  auto-enabled capabilities, and runtime readiness.
- Agent Plugins: choose committee members manually or use AI default/Core/All
  presets.
- Research Trace: inspect OS plan, selected agents, WRDS plan, metric registry,
  data gate, debate transcript, critic findings, final judge, and final output.
- Decision Debugger: inspect why a candidate was committed, why a target was
  blocked, why agents were activated, which Evidence Graph permissions apply,
  and which safety/policing events constrained Writer output.

## Frontend Files

- `static/index.html`
- `static/styles.css`
- `static/app.js`

The design goal is a low-noise AI workspace: one primary compose surface, quiet
connection/setup controls, and trace panels that appear when useful.

## Browser Visual Regression

Dashboard visual coverage lives in:

- `tests/browser/playwright.config.mjs`
- `tests/browser/dashboard.visual.spec.mjs`

Run it with:

```bash
npm install
npx playwright install chromium
npm run test:visual
```

The tests launch the FastAPI app, mock API responses for stable UI states, and
exercise two Chromium projects:

- desktop: `1440x1000`
- mobile: Pixel 7 profile

Covered visual contracts:

- home compose surface is visible, centered, nonblank, and has no horizontal
  overflow;
- setup sheet renders connection controls, capability/agent tabs, and all eight
  committee agent plugins without viewport overflow;
- run trace renders committee scorecard, discussion, Swarm Governance signals,
  agent signal diagnostics, verifier-promotion pills, and the Decision Debugger
  panels;
- Evidence Graph nodes/edges are clickable and open a sanitized drill-down drawer
  for blockers, candidates, output permissions, metrics, and persisted trace
  records.

## Decision Debugger Data Flow

The trace drawer renders Decision Debugger content immediately from `/agents/run`
fields:

- `quorum_trace`
- `stop_signals`
- `agent_allocation_trace`
- `evidence_graph`
- `social_immunity_report`
- `policing_trace`

When a `run_id` is available, the browser also hydrates the panel from the
PheroOS trace-store APIs:

- `GET /runs/{run_id}/trace`
- `GET /platform/swarm/runs/{run_id}/timeline`
- `GET /platform/swarm/runs/{run_id}/why-blocked/formal_valuation`
- `GET /platform/swarm/runs/{run_id}/why-committed`
- `GET /platform/swarm/runs/{run_id}/evidence-graph`
- `GET /platform/swarm/runs/{run_id}/agent-allocation`
- `GET /platform/swarm/runs/{run_id}/tool-events`
- `GET /platform/swarm/runs/{run_id}/permission-events`

`/runs/{run_id}/trace` is the first-class aggregate surface. It accepts
`tenant_id` and combines the redacted `logs/agent_runs.jsonl` audit summary with
SQLite-backed PheroOS trace sections only when the run belongs to that tenant.
If the SQLite trace store has no record yet, the panel keeps the run-response
fallback so the product remains useful during local mock/demo runs.

The supporting PheroOS list endpoints are also scoped by `tenant_id`:
`/platform/swarm/signals`, `/platform/swarm/events`, and
`/platform/swarm/agent-profiles` return only visible JSONL/profile records. Local
legacy records without a tenant are treated as `default`; named tenants must
have matching records before the dashboard can render them.

The Evidence Graph explorer normalizes both `/agents/run` graph sections and
SQLite-backed `{nodes, edges}` payloads. The drawer applies client-side redaction
again before showing payload previews, so a malformed trace fixture cannot expose
API keys, passwords, bearer tokens, or credential fields in the Dashboard.

Screenshots are saved under `output/playwright/visual-regression/`. The tests use
visual-contract assertions rather than brittle full-image golden snapshots, so
they catch layout regressions while staying portable across machines.
