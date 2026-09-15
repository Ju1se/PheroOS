# PheroOS Interaction Lab

This branch is an experimental interaction research package, not the historical
protocol-core product. The user explicitly authorized this reduced scope in
PheroOS_Interaction_Only_Codex_Goal.md. Old API and conformance preservation rules
remain with the archived releases; they do not require retired modules here.

- Study one current interaction hypothesis at a time. This migration changes no
  prompts, policies, record ordering, rounds, cache behavior or scoring semantics.
- Extract existing concrete utility code before inventing abstractions. Every
  retained module needs a current consumer or a minimum local execution-safety role.
- Keep pure visibility/policy code separate from adapters and ground-truth scoring.
- Default imports, installation, CLI and tests must run without legacy pheroos,
  pheroos-runtime, provider SDKs, network, model loading or credentials.
- Retain real scope/version/access/allowlist checks, bounded state, pre-dispatch
  durable reservations, cancellation, unknown spend and no hidden retry.
- Scope is a trusted-host, serialized, read-only/synthetic research harness. Do not
  claim old authority, Byzantine, hostile-host, multi-tenant or finality guarantees.
- Preserve historical source, configurations and raw receipts unchanged in the
  separately verified archive. Replay is offline migration evidence, not new model
  evidence; never feed retained responses to different prompts.
- No paid calls, credentials, model downloads, system changes, push, merge or
  publication are authorized by this cleanup. Never reset the shared money ledger.
- Keep one small migration report and a short future experiment sketch. No new
  production protocol machinery, public ABI/TCK or biological algorithm this cycle.
- Before delivery run the lean tests, mock CLI, exact recorded-input replay,
  credential-free API dry run, wheel/install boundary checks and archive verification.
  The README must give the actual installed commands.
