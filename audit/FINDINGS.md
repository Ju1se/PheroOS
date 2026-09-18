# PheroOS Codebase Audit v2 — Read-only diagnostic

**Scope declared by the auditor (the brief left it a placeholder; addendum §C requires it stated).**

| | |
|---|---|
| **Audited** | `runner/` (packaged as `pheroos_interaction.runner`, 19 modules, 6,390 LOC) · `src/pheroos_interaction/` (packaged as `pheroos_interaction`, 6 modules, 1,203 LOC) · `tests/interaction/` (26 files, 10,587 LOC — audited for §C evidence, not as a defect target) |
| **Excluded** | `.venv/` · `research-data/` · `experiments/` · `*.egg-info/` · `__pycache__/` · `examples/` and `docs/` (read as *evidence* for §A/§J/§K, never audited as code) · `.github/` (read only where §F traced CI inputs) |
| **Basis for exclusion** | the two packaged source roots in `pyproject.toml [tool.setuptools] packages` are the executable surface; everything else is fixture, prose, or environment |
| **Languages** | Python only (`requires-python >=3.12`) |

---

## 1. Summary

This is a small, unusually disciplined codebase — zero TODO/FIXME markers, zero assertion-free tests, 1,016 passing tests against 7,593 source lines, and an explicit written invariant for nearly every design choice — built on a foundation that is not under version control. Seven of the eight orchestration modules, carrying 52.3% of the repository's cyclomatic complexity, are untracked, which means the newest and most complex half of the system has no history, no blame, no review record, and does not exist in any checkout: the packaged console script raises `ModuleNotFoundError` on its own orchestration subcommands `[executed]`. The most serious technical defect is that offline replay — the artifact the whole four-layer design exists to produce — verifies the internal consistency of authority records but never re-derives the allocation decision, so a fully-consistent forged ledger in which the expensive worker claims every task under a policy that mathematically cannot produce that allocation replays `PASS` with zero failures `[executed]`, directly contradicting the documented promise that "every tampered record must FAIL with a named check rather than pass silently". Eight of the twelve declared invariants hold cleanly, including the ones most at risk of drift (no self-certification, no mechanism leakage, no experiment branches, no workforce inference). **The thing most likely to hurt in six months is the untracked layer**: it makes every git-based measurement in this audit blind to half the system, it will silently lose the design rationale for the code that has the least of it written down, and it is one `rm -rf` or one fresh clone away from being gone.

---

## 2. Audit conditions

| | |
|---|---|
| **Commit audited** | `e664d2e9d1790f40eef0b15b25f23155ea9294a6` (2026-09-16 21:15:13 -0700) **plus uncommitted working-tree state** — see below; this is *not* a state anyone can return to from git alone |
| **Tracked modifications** | 11 files, +460/−105 (`git diff --stat HEAD`) — verbatim in `audit/raw/01-audited-state.txt` |
| **Untracked** | 18 entries incl. 7 `runner/*.py` modules, 9 test files, `docs/`, `examples/` — verbatim `git status --porcelain` in `audit/raw/01-audited-state.txt` |
| **Exact state fixed by** | SHA-256 manifest of all 70 audited files: `audit/raw/02-manifest-before.txt`, manifest digest `5733e930b2cae90e7d2430365ea8d896ac3c57402e1100ee0abdbc25314e3b41` |
| **READ-ONLY ASSERTION** | Manifest recomputed after all work (`audit/raw/03-manifest-after.txt`) — **byte-identical, digest `5733e930…` unchanged**. Also verified mid-flight while 8 sub-agents were running. The working tree was not modified. |
| **Backup taken before any work** | `/tmp/audit-backup-1789706920.tar.gz` (1.2 MB), path recorded in `audit/raw/00-backup-path.txt` |
| **Network** | **YES** — `pypi.org/simple/` returned HTTP 200 |
| **Symlinks** | **ZERO** in every audited path and in every `/tmp` copy (`audit/raw/00-symlinks.txt`). `runner/` is a real directory mapped to `pheroos_interaction.runner` by setuptools `package-dir`, not a link. No path inside any copy resolves outside it, so no destructive check could write through a link, and LOC / duplication / import-graph metrics are not double-counted. |

**Tools.** Installed in an isolated venv at `/tmp/audit-venv`, never in the project environment: ruff 0.16.8, pylint 4.0.8, radon 6.0.1, vulture 2.16, bandit 1.9.4, pip-audit 2.10.1, semgrep 1.177.0, grimp 3.17 (library), mutmut 3.x, pytest.
**Unavailable:** `gitleaks`, `trufflehog`, `osv-scanner`, `jscpd`, `pydeps`, `import-linter` — each reported NOT RUN in §10, never substituted by reading.

**Temporary copies created, and deletion confirmed.**

| Copy | Purpose | Deleted |
|---|---|---|
| `/tmp/audit-src` | read-only tree snapshot | ✅ confirmed below |
| `/tmp/audit-mut` | executed invariant probes (L-1, L-4, forgery) | ✅ |
| `/tmp/audit-c2` + `/tmp/audit-c2-venv` | §C.2 stub mutation (layout-faithful, editable install) | ✅ |
| `/tmp/audit-c1` | §C.1 mutmut attempt | ✅ (deleted at the point of the NOT RUN ruling) |
| `/tmp/audit-venv`, `/tmp/audit-tools`, `/tmp/audit-npm` | toolchain + audit scripts | ✅ |
| 8 sub-agent copies (`/tmp/verify-*`, per-agent dirs) | each agent created and deleted its own; none shared | ✅ per agent report |

**Delegation.** Per addendum §E, the mechanical sections §A, §B.1, §D, §E, §F, §G, §H, §I were delegated to 8 parallel sub-agents, each given the evidence taxonomy, the §A layering evidence order and the §J answer constraint **verbatim**. §L (all invariants), §B.2, §C including the selection and reading of §C.2, §J and §K were performed by the lead auditor. 23 agents ran (8 measurement, 15 adversarial verifiers), 0 errors. 62 sub-agent findings were produced; every critical/high one was sent to a verifier instructed to refute it, and **all 15 reproduced the cited command exactly**. **4 were refuted — 2 of them as not-a-finding — and are excluded below and listed under Withdrawn; 11 had their severity corrected; 7 tag upgrades were caught and reverted.** Sub-agent tags are reproduced as given and never upgraded. Where merging two facts produced a new conclusion, it is tagged `[inferred]` and attributed to the lead auditor.

**Auditor-caused state (disclosure).** Two findings below (F-24 doc test-count drift, F-23 stale `orchestration_tasks_v1` doc references) were introduced earlier in this same session by the assistant's own prior work, before the audit began. They are reported because they are true of the audited state, not concealed because of their origin.

---

## 3. Invariant results (§L) — Layer 1, checked first

| Invariant | Result | Locators |
|---|---|---|
| **L-1** Canonical agent representation | **VIOLATED (1)** | `runner/contracts.py:401-403` — `eligible_agents()` dispatches on key presence, not declared format. `[executed]` a v1 spec writes canonicalized rows into the **v2-named** table (`audit/raw/11-v1-writes-v2-table.txt`) → **F-03** |
| **L-2** No hidden schema fallback | **VIOLATED (1)** | `runner/contracts.py:403` — `list(task["agents"]) if "agents" in task else [task["agent"]]` is an inlined default, not gated at a version boundary → **F-03** |
| **L-3** Version-aware replay | **VIOLATED (2)** | (a) `runner/audit.py:62-73` selects the reader by **table name**, not by the format recorded in `orchestration_v1.spec`; (b) table-version suffixes are inconsistent — tasks are `_v2` while artifacts/accounting/decisions/orchestration remain `_v1` → **F-05** |
| **L-4** Frozen means frozen | **VIOLATED (2)** | (a) `runner/runtime.py:117` `ledger_index = len(snapshot()["calls"])` is a **live ledger read** feeding the response draw, which is never persisted → **F-04**; (b) `runner/session.py:15`/`provider.py` `adapter_elapsed_ns` is inside the digested receipt bytes → **F-19** |
| **L-5** Availability is not execution | **HOLDS** | `runner/runtime_policies.py:244-258` separates `runtime_policies` from `platform_capabilities`; `runner/runtime.py:653` sources `active_decisions` from `len(snapshot["platform"]["decisions"])` — ledger-derived, not hard-coded. *(But see §9: the same discipline was not applied to the allocation/lease arm names.)* |
| **L-6** No self-certification | **HOLDS** | `[measured]` 0 AST sites read the actor from a model-supplied binding (`audit/raw/10-invariants-ast.json`). `runner/audit.py:188-192` recovers it from permission owner or claim event. |
| **L-7** Declared authority only | **HOLDS** | `runner/runtime_policies.py:268-276` host takes `pick_fifo`, no price; `runner/platform.py:424` refuses publication at/above abstention loss |
| **L-8** No workforce inference | **HOLDS** | `[measured]` 0 economics sites in the orchestration runtime modules. All 8 hits are in `src/pheroos_interaction/commitment.py` + `runner/worker.py:104`, where `latency_cost` is the **commitment** parameter — a different quantity (see §7) |
| **L-9** No mechanism leakage | **HOLDS** | `[measured]` by AST, not string search: 0 mechanism imports and 0 concrete policy instantiations in `runner/runtime.py`. *(§A notes a second import path exists via `worker.py`, so the property is not checkable by import graph alone — F-31)* |
| **L-10** Experimental identity inert | **HOLDS** | `[measured]` 0 experiment/test-mode/arm branches in any audited module |
| **L-11** Replayability | **VIOLATED (2)** | (a) draw generated, never persisted → **F-04**; (b) `runner/session.py:39` `clock` defaults to `time.time` and gates lease expiry at `:128,:141,:173` → **F-14**. *(A third candidate — `worker.waiting_rule` reading the live clock — was **refuted on verification**: it is the documented and tested contract, `docs/orchestration-architecture.md:379-382`. See §5 Withdrawn.)* |
| **L-12** Observation is not ontology | **see §9** | 3 overclaims, 2 correct-by-construction cases noted |

**Eight of twelve hold.** The four violations concentrate in one place: *the system can prove what a call contained, and cannot prove who was entitled to make it or why that agent was chosen.*

---

## 4. Metrics table

| Measurable | Value | Command |
|---|---|---|
| Source lines / SLOC / modules | 7,593 physical lines · **5,617 SLOC** · 25 modules (`runner/` 6,390/19, `src/` 1,203/6) | `wc -l` → `audit/raw/26-loc.txt`; `radon raw -s` → `audit/raw/A-radon-raw.txt` |
| Test LOC / files | 10,587 / 26 (test:source ≈ 1.4:1) | same |
| Import cycles | **0** — 25 modules, 58 edges, 0 mutual imports, 0 non-trivial SCCs (the graph is a DAG) | `grimp.build_graph('pheroos_interaction')` + Tarjan SCC → `audit/raw/A-grimp-graph.txt` |
| Declared-layering violations | **0** — rule 1 (`src/pheroos_interaction/*` never imports `runner.*`): 0 across 6×19 module pairs; rule 2 (runtime reaches colony only via the adapter): 0 direct imports | `grimp find_illegal_dependencies_for_layers` → `audit/raw/A-grimp-contracts.txt` |
| Modules unreachable from every CLI entry point | **1** — `runner/colony.py`, 286 LOC, zero call sites outside tests | `audit/raw/27-reachability.txt` |
| Duplicate sets (literal) | 8 reported, of which **6 have DRIFTED** apart | pylint `duplicate-code` + normalized-AST hashing → `audit/raw/B1-*` |
| Durable tables with >1 writing module | **4 of 17** (`work` has 3: session, platform, evidence) | `audit/raw/25-write-authority.txt` |
| Canonical-serialization definitions | **6 sites, 3 distinct return types** | `audit/raw/25-*`, F-16 |
| Test count | **1,016 collected** / 572 test functions | `pytest -q` in `/tmp/audit-c2` |
| Unit : integration | **472 : 100** (criterion stated in `audit/raw/24-test-quality.txt`) | AST pass |
| Mocks per test file | **2.12**; top ratio 0.27 (`test_inspection_runner.py`) | AST pass |
| Tests with no assertion | **0** — 5 candidates all delegate to `assert_detected` (4 assertions) | verified individually, `audit/raw/24-*` |
| Tests asserting only on mock call counts | **0** — 3 candidates were false positives (`snapshot()['call_count']` is a ledger field) | verified individually |
| Surviving mutants % | **NOT RUN** — 233 mutants generated, **0 executed** | §10 |
| **Stub mutation (§C.2, executed)** | 8 stubs, baseline 1,016 green | `audit/raw/21-stub-mutation.txt` |
| Complexity outliers | 56 of 452 blocks CC>10; **18 blocks CC>20**; worst `replay_run` CC 68 | `radon cc -s -n C` → `audit/raw/G-radon-cc.txt` |
| Maintainability floor | `runner/contracts.py` **MI 0.00** (next worst `session.py` 3.92) | `radon mi -s` |
| Files > 800 lines | **1** (`runner/runtime.py`, 889) | `wc -l` |
| Error-masking sites | 4 designed boundaries, **3 discard the exception message** | `audit/raw/D-*` |
| Logging statements in production code | **0** | `audit/raw/D-*` |
| Missing timeouts | 0 unbounded; 1 per-read-not-per-request (F-22) | `audit/raw/D-*` |
| Secrets found | **0** by bandit + documented regex sweep; `gitleaks`/`trufflehog` NOT RUN | `audit/raw/E-*` |
| Declared deps / undeclared imports / unused deps | 0 runtime deps declared; **0 undeclared third-party imports** (stdlib-only claim verified, not repeated) | `audit/raw/F-*` |
| Lockfile | **none exists** | `audit/raw/F-*` |
| Vulnerable deps | **0 known** in the build requirement and dev extra. pip-audit returns `{"dependencies": [], "fixes": []}` because `setuptools>=84` resolves to a version with no advisories — **not** because it is skipped: a positive control (`setuptools==65.5.0`, `jinja2==3.1.2`) does report vulnerabilities | `pip-audit -r <file>` → `audit/raw/F-*`, refutation in `audit/raw/V-*` |
| Churn coverage | **NOT RUN for 54.2% of files / 52.3% of complexity** (untracked) | `audit/raw/H-*` |
| Measured reverts | **1** (1,485 lines, 10 files, 13h lifespan); explicit `git revert`: **0** | `audit/raw/H-churn-reverts.txt` |
| Probable re-fixes | **0** | `audit/raw/H-*` |
| Nondeterminism sites | 4 (draw, default clock, `adapter_elapsed_ns`, per-row `created` stamps) + 8 unordered SELECTs | `audit/raw/I-*` |
| TODO / FIXME / HACK / XXX | **0** across all of `runner/`, `src/` and `tests/` | `grep -rnE 'TODO\|FIXME\|HACK\|XXX'` |

### §C.2 Controlled stub mutation — executed, not reasoned

Isolated copy `/tmp/audit-c2` with its own editable install; baseline **1,016 passed**; each stub applied by AST body-replacement, full suite run, file restored, baseline reconfirmed green after every case.

| # | Stub | Result | Detected by |
|---|---|---|---|
| S1 | `workflow_spec` → `return value` (no validation at all) | 140 failed, 111 errors | broad |
| S2 | `conforms` → `return True` (schema never enforced) | 128 failed, 30 errors | broad |
| S3 | **`RuntimePolicies.select_work` → always FIFO head (policy ignored)** | **9 failed, 1,007 passed** | only 2 files |
| S4 | `validate_schema` → `return schema` | 83 failed, 30 errors | broad |
| S5 | `eligible_agents` → `.get()` form | **1,016 passed — SURVIVED** | none (likely equivalent mutant: `task_spec` forbids an empty `agents`) |
| S6 | **`Runtime._require_executable` → no-op (v1/v2 gate removed)** | **1 failed** | 1 test |
| S7 | `audit` `check()` → always OK (the auditor neutered) | 20 failed | tamper tests |
| S8 | **`worker_order` → `sorted(...)`** | **3 failed** | 1 file only |

---

## 5. Findings

Ordered by cost of not fixing. §L violations first. **36 reported of 74 total** (62 sub-agent + 12 lead). Two entries, **F-11 and F-13, were withdrawn after adversarial verification**; their numbers are deliberately left as gaps so the Withdrawn table at the end of this section remains traceable. 34 findings stand (62 sub-agent + 12 lead); the remainder are low-severity §E/§F/§G items retained verbatim in `audit/raw/40-subagent-findings.txt`.

### F-01 · The orchestration layer is untracked: half the system is outside version control
Severity: **critical** — Layer 1 — Category: L (state of record) — Evidence: `[measured]` + `[executed]`
Locator: `runner/{anthropic,audit,contracts,orchestration,runtime,runtime_policies,tools}.py`, `tests/interaction/test_{anthropic,e4_shared_capacity,orchestration_audit,orchestration_authority,orchestration_colony,orchestration_hardening,orchestration_recovery,orchestration_workflow,tools}.py`, `docs/`, `examples/`
Command: `git status --porcelain` (verbatim → `audit/raw/01-audited-state.txt`); `git log --oneline -- runner/runtime.py` → 0 commits
**What is true:** 16 source/test files plus `docs/` and `examples/` are untracked. `git log` returns **0 commits** for each of the 7 orchestration modules. They carry 3,934 source LOC and **52.3% of the repository's cyclomatic complexity**. `[executed]` They are absent from `git archive HEAD`, so the installed console script raises `ModuleNotFoundError` on `orchestrate`, `orchestrate-resume` and `orchestrate-replay` (F-10), and CI references six input files that exist in no checkout (F-09). No `.gitignore` entry covers them — `git check-ignore` returns nothing — so this is omission, not policy.
**Why it matters:** Three specific, already-realised consequences, not a hypothetical. (1) §H churn is NOT RUN for 54.2% of files. (2) §J rationale for these units can only reach DOCUMENTED via in-file prose, never via commit message or blame — and they are the units with the least prose (F-27). (3) L-3 and L-4 cannot be verified *as versioned properties* for code that has no version. A fresh clone does not contain the system.
**Fix shape:** Commit the layer, or add a deliberate `.gitignore` entry with a written reason. Then re-run §H and §J.
Cost: **S** — Risk of fixing: none to the code; the risk is in the decision the commit forces about what is ready to be a record.

### F-02 · A fully-consistent forged allocation replays PASS
Severity: **critical** — Layer 1 — Category: L-4 / L-6 / L-11 — Evidence: `[executed]`
Locator: `runner/audit.py:205-431` (`replay_run`); the 19 check families it emits contain no allocation check
Command: `audit/raw/14-complete-forgery.txt` (and the partial-forgery control in `13-forged-claimant-replays-pass.txt`)
**What is true:** Cell B declares the `response` arm, under which the expensive worker defers on every task (p = 6561/397186 ≈ 0.0165 against three draws of 0.78, 0.61, 0.73). Rewriting the recorded ledger so `expensive` claims all three tasks — updating permission owner, the `claimed` event **and** the recorded binding agent consistently — yields `replay_run` → **`PASS`, failures: (none)**. A *partial* forgery (omitting the binding) is caught by `binding_rebuild`, so the detection surface ends exactly at internal consistency. Because both workers must declare the identical model config (an experimental-validity requirement), the rebuilt request is agent-independent and the substitution is invisible.
**Why it matters:** `tests/interaction/test_orchestration_audit.py:4-5` states the contract in the codebase's own words: *"every tampered record must FAIL with a named check rather than pass silently."* This is a class of tamper that passes silently. `README.md:169` states the governing principle as *"PheroOS admits and records execution"* — the ledger records *that* an eligible agent executed, never *that the declared policy chose it*. For a governance runtime whose entire purpose is offline attestability, the allocation decision — the thing the L2 colony layer exists to make — is the one decision replay cannot check.
**Fix shape:** Persist the allocation decision as a durable row at the moment it is made (chosen `(agent, work)`, the derived policy arguments, the draw, the ledger index), and add a replay check that re-derives the decision from the frozen spec and compares. Recording deferrals as well would close F-04 in the same change.
Cost: **M** — Risk of fixing: new durable rows change the ledger schema and every existing recorded run's digest; needs a version bump, which the repo already has machinery for.

### F-03 · `eligible_agents` is an inlined schema fallback, and a v1 spec writes into the v2-named table
Severity: **high** — Layer 1 — Category: L-1 / L-2 — Evidence: `[executed]`
Locator: `runner/contracts.py:401-403`; consequence at `runner/orchestration.py:62,86,625,671,677`
Command: `audit/raw/11-v1-writes-v2-table.txt`; AST scan `audit/raw/10-invariants-ast.json`
**What is true:** `eligible_agents()` is `list(task["agents"]) if "agents" in task else [task["agent"]]` — it dispatches on **key presence**, not on the declared format, and it is called from 11 live sites including the durable write path. `[executed]` `OrchestrationSession.create()` accepts a `orchestration-workflow-v1` spec and **succeeds**, writing `agents=["producer"]` rows into `orchestration_tasks_v2` while `orchestration_v1.spec` still records `format: orchestration-workflow-v1`. The execution refusal added at `runtime.py:102` fires only at `run`/`step`, i.e. *after* the durable rows exist.
**Why it matters:** The table-name version stops identifying the semantics of its contents, which is precisely the property the v2 rename was introduced to establish. It also leaves an orphan ledger: durable rows written, execution refused. And L-2's rule exists because an inlined default cannot be audited at a boundary — this one cannot.
**Fix shape:** Move the refusal to `OrchestrationSession.create`, so a v1 spec never reaches a durable write; and gate `eligible_agents` on the spec format explicitly rather than on key presence.
Cost: **S** — Risk of fixing: `create` is used by tests that build v1 specs directly; those would need updating (two already were migrated to v2 during this session).

### F-04 · The allocation draw is generated and never persisted, and replay never checks allocation
Severity: **high** — Layer 1 — Category: L-4 / L-11 — Evidence: `[executed]` (lead) + `[measured]` (§I, independently)
Locator: `runner/runtime_policies.py:114-121` (`draw`), `runner/runtime.py:117` (`ledger_index`)
Command: `audit/raw/12-allocation-not-replayable.txt`
**What is true:** The draw is derived from seed, spec digest, agent, work id and `len(session.snapshot()["calls"])` — the last of which is a **live ledger read**, not a frozen input. `[executed]` Scanning every value of every row of every table of a completed cell-B ledger: the tokens `draw`, `ledger_index`, `defer`, `deferred`, `cheaper_workers` and `threshold` are **absent**; only `exponent` appears, and only because the frozen spec is stored. No deferral event type exists. §I reached the same conclusion independently from the other direction.
**Why it matters:** This is the mechanism behind F-02. An auditor cannot re-derive what the policy decided, so "the response arm ran" is unfalsifiable from the record. It also means the L2 layer's actual behaviour — how often the expensive worker deferred, under what backlog — is unmeasurable retrospectively, which blocks any quantitative use of the four-cell design.
**Fix shape:** Persist the decision inputs alongside the decision (see F-02). Deferrals need a row too, or the denominator is unknowable.
Cost: **M** — Risk of fixing: same schema-version concern as F-02.

### F-05 · Replay version-gates by table name, not by the recorded spec format; table suffixes are inconsistent
Severity: **medium** — Layer 1 — Category: L-3 — Evidence: `[read]` + `[measured]`
Locator: `runner/audit.py:36` (`TASK_TABLES`), `:62-73` (the probe); `runner/orchestration.py:74-78` (the five `CREATE TABLE`s)
Command: `grep -n "CREATE TABLE orchestration" runner/orchestration.py`
**What is true:** `[measured]` One ledger creates `orchestration_v1`, `orchestration_tasks_v2`, `orchestration_artifacts_v1`, `orchestration_accounting_v1`, `orchestration_decisions_v1` — one table at v2, four at v1, describing the same generation of the schema. `[read]` `ReplayLedger` chooses its reader by trying `orchestration_tasks_v2` then `orchestration_tasks_v1`, i.e. by table name; the authoritative version statement — `orchestration_v1.spec["format"]` — is never consulted for that decision.
**Why it matters:** Combined with F-03 (a v1 spec can produce a v2-named table), the gate can select the wrong reader for a ledger whose recorded format says otherwise. Today the normalization happens at write time so the read stays consistent, which is why this is medium and not high — but the two signals are already capable of disagreeing.
**Fix shape:** Gate on `orchestration_v1.spec["format"]` and treat the table probe as a fallback that must agree with it. Separately, decide whether the four `_v1` suffixes are still accurate.
Cost: **S** — Risk of fixing: low; the v1 read path has no real artifact to regress against (F-32).

### F-06 · The v1/v2 execution gate is held by exactly one test
Severity: **high** — Layer 2 — Category: C — Evidence: `[executed]`
Locator: `runner/runtime.py:102-115` (`_require_executable`), called at `:354` and `:657`
Command: stub S6 in `audit/raw/21-stub-mutation.txt`
**What is true:** Replacing `_require_executable` with a no-op leaves **1,015 of 1,016 tests passing**. The single failure is `test_orchestration_audit.py::test_a_v1_workflow_validates_and_audits_but_the_runtime_refuses_to_execute_it`.
**Why it matters:** The entire L-3 boundary — "v1 is auditable, v2 is executable" — rests on one assertion. Deleting or skipping that test removes the invariant from CI without any other signal.
**Fix shape:** Add coverage at the other boundary (`create`, per F-03) and for `resume_run`, so the gate is held by tests at each entry point rather than one.
Cost: **S** — Risk of fixing: none.

### F-07 · The allocation policy can be replaced by FIFO and 1,007 of 1,016 tests still pass
Severity: **high** — Layer 2 — Category: C — Evidence: `[executed]`
Locator: `runner/runtime_policies.py:260-266` (`select_work`)
Command: stub S3 in `audit/raw/21-stub-mutation.txt`; per-file breakdown re-run separately
**What is true:** Stubbing `select_work` to always return the FIFO head — i.e. deleting the colony L2 layer's effect entirely — fails **9 tests in exactly 2 files** (`test_e4_shared_capacity.py` 5, `test_orchestration_colony.py` 4). Stubbing `worker_order` to `sorted(...)` fails **3 tests in exactly 1 file** (`test_e4_shared_capacity.py`).
**Why it matters:** Allocation correctness and worker-enumeration order — both load-bearing for the system's central claim and for experimental validity — are guarded by one and two files respectively. Deleting `test_e4_shared_capacity.py` would silently remove the worker-order invariant from the suite. This compounds F-02: neither the tests nor the replay would notice a broken allocation.
**Fix shape:** Add allocation assertions to the workflow/authority suites so the guarantee is not co-located with the experiment fixture that happens to exercise it.
Cost: **S** — Risk of fixing: none.

### F-08 · `replay_run` is a 227-line function at CC 68 with a path where a receipt is never digest-verified
Severity: **high** — Layer 2 — Category: G — Evidence: `[read]`, upgraded to `[executed]` by the verifier, who built a working forgery
Locator: `runner/audit.py:205-431`; the skip at `:314-316`
Command: `/tmp/audit-venv/bin/radon cc -s -n C runner src` → `audit/raw/G-radon-cc.txt`
**What is true:** `[measured]` CC 68, rank F — highest in the repository and 3.4× the next-worst non-agent-loop block; 227 lines, the longest function in scope by 46 lines; seven sequential validation phases sharing one body and one mutable failure list. `[read]` A whole class of receipt (`response_rejected`) traverses the decision loop without its digest being verified.
**Why it matters:** This is the function that produces the offline verdict — the artifact the four-layer design exists to make checkable. It is simultaneously the most complex and the least decomposable code in the repository, and F-02 is a defect of exactly the kind its density hides.
**Fix shape:** Split into one function per ledger table, each returning its own `(checks, failures)`.
Cost: **L** — Risk of fixing: **high** if done as one change; it is the verification oracle. Split behind the existing tamper tests, one table at a time.

### F-09 · CI depends on six input files that exist in no checkout
Severity: **high** (verifier confirmed; originally raised as part of a critical) — Layer 2 — Category: F — Evidence: `[executed]`
Locator: `.github/workflows/interaction.yml`
Command: agent re-ran in its own isolated `git archive HEAD` extraction → `audit/raw/F-*`
**What is true:** The workflow references six input files that are untracked and therefore absent from any clone or archive.
**Why it matters:** CI is green locally and cannot be green from a clean checkout. The signal everyone trusts is measuring a state only this machine has.
**Fix shape:** Resolved by F-01.
Cost: **S** — Risk of fixing: none beyond F-01.

### F-10 · The installed console script raises `ModuleNotFoundError` on its orchestration subcommands
Severity: **high** (verifier corrected from critical: the severity argument's load-bearing part was refuted) — Layer 2 — Category: F — Evidence: `[executed]`
Locator: `pyproject.toml [project.scripts]` → `pheroos_interaction.runner.cli:main`; `runner/cli.py:40,44`
**What is true:** `orchestrate`, `orchestrate-resume` and `orchestrate-replay` lazily import `.runtime` / `.audit`, which are untracked; installing from a clean checkout yields `ModuleNotFoundError` at subcommand dispatch.
**Why it matters:** The packaged artifact does not contain the feature the README leads with. Lazy imports mean this surfaces at invocation, not install.
**Fix shape:** Resolved by F-01.
Cost: **S** — Risk of fixing: none beyond F-01.

### F-12 · No lockfile exists; CI resolves five unpinned packages from PyPI on every run
Severity: **medium** (verifier corrected from high) — Layer 2 — Category: F — Evidence: `[executed]`
Locator: repo root (absence); `.github/workflows/interaction.yml`
**What is true:** No lockfile anywhere. `pytest>=8` already resolves across a major-version boundary to 9.1.1 with no upper bound; `setuptools>=84` is satisfied by exactly one PyPI release.
**Why it matters:** For a project whose central claim is byte-exact replay, the toolchain that produces and verifies the records is itself not reproducible.
**Fix shape:** Pin CI inputs with a lockfile or a constraints file.
Cost: **S** — Risk of fixing: low.

### F-14 · The default clock is `time.time`, and it gates lease expiry which gates allocation
Severity: **medium** — Layer 1 — Category: L-11 — Evidence: `[measured]`
Locator: `runner/session.py:39`; consumed at `:128`, `:141`, `:173`; `runner/platform.py:183`
**What is true:** `self.clock = clock or time.time`. Lease expiry is evaluated against it, and `ready_work` projects expired leases — which is the input to allocation. Tests inject a fake clock; production does not.
**Why it matters:** The deterministic boundary the system claims covers requests and decisions, but the *readiness* of work is wall-clock dependent. Today nothing in the shipped workflows stalls long enough to expire, which is why this is medium — and also why the L3 lease factor is inert (F-20).
**Fix shape:** Make the clock an explicit, recorded run input rather than a default.
Cost: **M** — Risk of fixing: the clock is threaded through three layers.

### F-15 · `runner/contracts.py` has maintainability index 0.00 and is the trust boundary for untrusted JSON
Severity: **high** — Layer 2 — Category: G — Evidence: `[measured]` (verifier corrected "seven" → **six** blocks over CC 20)
Locator: `runner/contracts.py:507-576` (`workflow_spec`, CC 56), `:111-173` (`validate_schema`, CC 40), `:176-225` (`conforms`, CC 30), `:328-359` (`_policy`, CC 25), `:406-452` (`task_spec`, CC 23), `:614-661` (`parse_proposal`, CC 21)
Command: `/tmp/audit-venv/bin/radon mi -s runner src` → `audit/raw/G-radon-mi.txt`
**What is true:** MI **0.00** — the floor; no other file reaches it (next worst `session.py` at 3.92). 674 lines holding six of the repository's 18 blocks above CC 20.
**Why it matters:** Every one of these sits between untrusted input (a spec file, a model response) and state the rest of the system trusts absolutely. A missed branch here does not crash — it admits something malformed as valid. Stubs S1/S2/S4 confirm the tests do cover this densely (140/128/83 failures), so the risk is future modification, not current behaviour.
**Fix shape:** Extract `workflow_spec`'s cross-entity consistency rules into a table of named predicates, each keeping its exact `ContractError`.
Cost: **L** — Risk of fixing: moderate; mechanical, and every rule keeps its message.

### F-16 · Canonical serialization is defined six times, with three different return types
Severity: **medium** — Layer 2 — Category: B.2 (lead auditor) — Evidence: `[measured]`
Locator: `runner/contracts.py:42` (str), `runner/session.py:15` (str), `runner/inspection.py:25` (**bytes**), `runner/provider.py:19-34` (round-trip object), `runner/driver.py:10` (round-trip object), `src/pheroos_interaction/sequential.py:577` (inlined)
Command: `grep -rn "sort_keys=True" runner/ src/`
**What is true:** Six independent definitions of "canonical JSON", all using `sort_keys=True, separators=(",",":"), allow_nan=False`, returning `str`, `bytes` and parsed objects respectively. Digests are computed from more than one of them.
**Why it matters:** Every digest, every logical operation key and every replay comparison in this system depends on these agreeing. They agree today by coincidence of identical arguments, and nothing enforces it — a change to one is a silent, ledger-wide digest change that no test names as its subject.
**Fix shape:** One definition; the byte/str variants become thin wrappers over it.
Cost: **M** — Risk of fixing: any accidental behaviour change invalidates every recorded digest, so it must be paired with a digest-stability test over a frozen fixture.

### F-17 · The `work` table has three writing modules; `calls`, `run` and `events` have two
Severity: **medium** — Layer 2 — Category: B.2 (lead auditor) — Evidence: `[measured]`
Locator: `runner/session.py`, `runner/platform.py`, `runner/evidence.py` (see `audit/raw/25-write-authority.txt`)
Command: SQL-verb scan over `runner/*.py`
**What is true:** 4 of 17 durable tables have more than one writing module. `work` — which holds `status`, `owner`, `epoch`, `expires`, i.e. lifecycle **and** authority — is written by `session.py`, `platform.py` and `evidence.py`. `platform.py` reaches it as a mixin over `Session`; `evidence.py` is `CoordinationSession(Session)`, a **sibling** subsystem, so its writes are parallel implementations rather than inherited ones.
**Why it matters:** Multiple readers are unremarkable; multiple modules entitled to mutate lifecycle and authority state are the pattern that produces divergence nobody notices, because each is locally correct.
**Fix shape:** None proposed — see §7, where the specific divergence is put to the maintainer as a question rather than asserted as a defect.
Cost: — Risk of fixing: —
*Note: a related §B.1 claim — that `CoordinationSession.dispatch` copies `Session.dispatch` rather than overriding a hook — was **refuted** by the verifier, which found the explicit justification at `runner/evidence.py:284-285`. That is a domain distinction and is correctly excluded.*

### F-18 · `run_colony` is a fork of `run_worker`, with a hand-maintained parity comment and the parity already broken
Severity: **medium** (verifier corrected from high) — Layer 2 — Category: B.1 — Evidence: `[measured]`
Locator: `runner/colony.py:106-286` (CC 64, 181 lines) and `runner/worker.py:108-218` (CC 43, 111 lines); parity comment at `runner/colony.py:211`
Command: pylint `duplicate-code` + AST span pass → `audit/raw/B1-*`, `audit/raw/G-radon-cc.txt`
**What is true:** 53 lines identical or rename-only across the two loops. They are the 2nd and 5th most complex blocks in the repository. Their required agreement is stated in a comment, and the agent reports the parity is **already broken**.
**Why it matters:** Two large single-body loops required to agree, with a comment as the specification and one test covering one aspect, is a configuration in which drift is found in production. `[measured]` `runner/colony.py` is additionally the only module unreachable from any CLI entry point (`audit/raw/27-reachability.txt`), with zero call sites outside `test_colony.py` — so the fork that drifted is the one nothing ships.
**Fix shape:** Extract the shared step (claim, plan, drive, classify, publish/reject, renew) into one function both call.
Cost: **L** — Risk of fixing: moderate-to-high; these loops own lease lifetime and reservation release.

### F-19 · `adapter_elapsed_ns` sits inside the digested receipt bytes, defeating idempotent re-receive
Severity: **medium** — Layer 2 — Category: I / L-4 — Evidence: `[executed]`
Locator: `runner/provider.py`, receipt digest path; `audit/raw/I-exec-receipt-digest-nondeterminism.txt`
**What is true:** A timing measurement is included in the bytes that are digested to identify a receipt, so the same logical receipt digests differently on each run.
**Why it matters:** Receipt digests are how the system recognises an already-settled call. A digest that moves with elapsed time defeats the idempotency the ledger relies on for crash recovery.
**Fix shape:** Exclude timing from the digested payload; keep it as adjacent metadata.
Cost: **S** — Risk of fixing: changes recorded digests; version-bump territory.

### F-20 · The L3 lease factor is declared but inert: nothing in the shipped workflows can expire
Severity: **medium** — Layer 3 — Category: K / experimental validity — Evidence: `[executed]`
Locator: `runner/runtime.py:361` (release in `finally`), `runner/platform.py:183`; `audit/raw/23-lease-ttl-applied.txt`
**What is true:** Fixed TTL 60 vs evaporation TTL 120 — the arms genuinely differ. But every step releases its lease in a `finally`, the run is serial and sub-second, and `[executed]` after completion every `work` row has `expires = NULL`: the granted TTL is never persisted at all. Cells A≡C and B≡D byte-for-byte.
**Why it matters:** The lease dimension of the 2×2 carries no observable effect and cannot be analysed as it stands, and no record of which TTL was in force survives in the ledger. The repository already states this honestly in `test_e4_shared_capacity.py` and `AGENTS.md`; it is reported here because it bounds what the design can currently measure.
**Fix shape:** Either report E4 as a one-factor design, or build a fixture in which a lease can actually expire.
Cost: **M** — Risk of fixing: none to production code.

### F-21 · Three of four designed error boundaries discard the exception message
Severity: **medium** (verifier corrected from high; also caught a tag upgrade) — Layer 2 — Category: D — Evidence: `[executed]`
Locator: see `audit/raw/D-*`
**What is true:** 93 distinct `StateError` failures collapse into the single token `"StateError"` at three of the four designed boundaries.
**Why it matters:** For an agent runtime, the distinguishing information in a refusal *is* the observability. Collapsing 93 refusal reasons to one token means a production failure cannot be diagnosed from the record.
**Fix shape:** Preserve the message at the boundary; the classification can stay.
Cost: **S** — Risk of fixing: messages become part of persisted outcome text — bound them (see F-25).

### F-22 · No logging exists anywhere in production code
Severity: **medium** — Layer 2 — Category: D — Evidence: `[measured]`
Locator: `runner/`, `src/pheroos_interaction/` (absence)
**What is true:** Zero logging statements. The three silent `pass` handlers therefore leave no trace in any channel.
**Why it matters:** Combined with F-21, a swallowed failure is unrecoverable after the fact. The ledger records decisions, not the runtime's own faults.
**Fix shape:** Structured logging at the four designed boundaries only.
Cost: **S** — Risk: low.

### F-23 · `AGENTS.md` and the architecture doc name a capability table the code never creates
Severity: **medium** — Layer 2 — Category: A / K — Evidence: `[measured]`
Locator: `AGENTS.md:88`, `docs/orchestration-architecture.md:50`, `:100` (`:321` is a correct historical reference)
Command: `grep -rn "orchestration_tasks_v1" AGENTS.md docs/`; `grep -n "CREATE TABLE orchestration" runner/orchestration.py`
**What is true:** Three doc sites name `orchestration_tasks_v1` as the live capability table. The code creates only `orchestration_tasks_v2`; no code path creates `orchestration_tasks_v1`. `AGENTS.md:88` is inside the statement of the governing authority rule.
**Why it matters:** The authority rule points at a table that does not exist, so a reader verifying the central claim against the schema finds nothing. **Disclosure: introduced by the assistant earlier in this session when the table was renamed.**
**Fix shape:** Update the three references.
Cost: **S** — Risk: none.

### F-24 · The verification report's test counts are hand-written and two of eight have drifted
Severity: **low** — Layer 3 — Category: K — Evidence: `[measured]`
Locator: `docs/orchestration-verification.md:84` and the surrounding table
Command: `audit/raw/31-doc-count-drift.txt`
**What is true:** `test_orchestration_audit.py` claimed 43, actual 48; `test_orchestration_colony.py` claimed 35, actual 39. The other six match.
**Why it matters:** A verification report whose counts are not derived from the suite presents a stale number in the grammar of a measurement. **Disclosure: both drifts were caused by the assistant adding tests earlier in this session.**
**Fix shape:** Generate the table, or drop the counts.
Cost: **S** — Risk: none.

### F-25 · Provider-controlled `error.type` is interpolated unbounded into the persisted outcome
Severity: **medium** — Layer 2 — Category: E — Evidence: `[measured]`
Locator: `runner/anthropic.py`; persisted via the per-task `reason` in `outcome.json`
**What is true:** A field controlled by the remote service is interpolated without a length bound into an exception that becomes an unbounded per-task reason in the durable outcome record.
**Why it matters:** Every other text field in this system is byte-bounded by contract. This one is not, and it is the one an external party controls.
**Fix shape:** Bound it like every sibling field.
Cost: **S** — Risk: none.

### F-26 · `_open_within` does not reject `..`; confinement lives in a different module than the docstring promising it
Severity: **medium** — Layer 2 — Category: E — Evidence: `[measured]`
Locator: `runner/tools.py`; confinement in the calling module
**What is true:** The function whose docstring promises path confinement does not itself reject `..`; the check lives elsewhere. `O_NOFOLLOW` is applied to every path component **except the root handle it starts from** (a separate low finding).
**Why it matters:** Not currently exploitable — fixtures are declared and the caller checks — but the guarantee is asserted in one place and implemented in another, which is how such a guarantee gets lost in a refactor.
**Fix shape:** Move the check into the function that promises it, or correct the docstring.
Cost: **S** — Risk: low.

### F-27 · Five of the twelve most load-bearing units have no docstring, four of them in the most-depended-upon module
Severity: **medium** — Layer 3 — Category: J — Evidence: `[measured]`
Locator: `runner/session.py:433` (`snapshot`, 350 inbound calls), `:152` (`claim`, 161), `:201` (`reserve`, 47), `:274` (`receive`, 38); `runner/contracts.py:42` (`wire`, 65)
Command: `audit/raw/20-loadbearing.txt`, `audit/raw/32-rationale-docstrings.txt`
**What is true:** These five have zero docstring. `session.py` is tracked but has only 4 commits, and §H established `[measured]` that its birth commit is a flattened squash, so blame attributes all 394 original lines to a commit message about replacing a protocol tree.
**Why it matters:** The repository's documentation discipline is otherwise exceptional; the gap sits precisely on the primitives everything else is built from, where neither prose nor commit history can answer "why this shape".
**Fix shape:** None mechanical — see §8, where these are posed as questions.
Cost: **S** — Risk: none.

### F-28 · `runner/runtime.py` is the only file over 800 lines, MI 5.88, with `_outcome` at CC 31
Severity: **medium** — Layer 2 — Category: G — Evidence: `[measured]`
Locator: `runner/runtime.py:1-889`; `:690-751` (`_outcome`, CC 31), `:412-468` (`_infer`, CC 17), `:195-234` (`_conversation`, CC 17)
**What is true:** 889 lines, 8 blocks above CC 10. `_outcome` decides how a run ends — the value everything downstream, including the replay verifier, is checked against.
**Fix shape:** Split along the section banners the file already carries.
Cost: **M** — Risk: low-to-moderate; import-level movement.

### F-29 · `admit_children` accepts `lease_seconds`, validates it nowhere, uses it nowhere
Severity: **medium** — Layer 2 — Category: G — Evidence: `[measured]`
Locator: `runner/orchestration.py:572-631` (signature at `:572`)
Command: `ruff --select ARG` (ARG002) and pylint W0613, independently
**What is true:** Every other `lease_seconds` parameter in the repository is both `_duration`-validated and threaded; this one is neither.
**Why it matters:** A caller passing `lease_seconds=300` silently gets whatever the decomposition path applies, with no error.
**Fix shape:** Thread it, or delete the parameter.
Cost: **S** — Risk: low; deleting is the safer branch.

### F-30 · Transport configuration is read from the environment and never recorded in the frozen run record
Severity: **medium** — Layer 2 — Category: I — Evidence: `[measured]`
Locator: `runner/runtime.py` `build_transports` (`PHEROOS_PROVIDER`, `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`)
**What is true:** The endpoint and enablement that determine where model calls went are environment-resolved and absent from `frozen.json`. An empty `ANTHROPIC_BASE_URL` silently resolves to the production API endpoint (separate low finding).
**Why it matters:** The frozen record is meant to fix run identity; the destination of every external call is outside it.
**Fix shape:** Record the resolved base URL and provider enablement (never the key) in `frozen.json`.
Cost: **S** — Risk: changes the frozen digest.

### F-31 · The "only door to L1–L3" property cannot be checked by import graph
Severity: **low** — Layer 2 — Category: A / L-9 — Evidence: `[measured]`
Locator: `runner/runtime.py` → `runner/worker.py` → colony mechanism
**What is true:** `runtime.py` imports `_release` from `worker.py`, which itself reaches a colony mechanism, so a second import path exists. The AST check for L-9 (no mechanism imports, no concrete policy instantiation **in `runtime.py`**) still passes.
**Why it matters:** The invariant holds as written but is not enforceable by the graph-level check a reader would reach for. The existing `ast`-based test asserts the stronger property directly, which is why this is low.
**Fix shape:** State the property as "no direct import and no concrete instantiation", which is what is actually tested.
Cost: **S** — Risk: none.

### F-32 · The v1 compatibility read path has no v1 artifact and is tested against a fabricated schema
Severity: **low** — Layer 2 — Category: A — Evidence: `[measured]`
Locator: `runner/audit.py:36,62-73`; `tests/interaction/test_orchestration_audit.py::test_replay_reads_the_previous_durable_task_schema`
**What is true:** No `orchestration_tasks_v1` ledger exists anywhere in the repository — the table was never released under that name. The compatibility reader is exercised only against a v1 shape the test synthesises by downgrading a v2 ledger. The test says so in its own docstring.
**Why it matters:** The path is speculative compatibility surface. It is honestly labelled, so this is low — but it is code carrying a maintenance cost for a artifact that has never existed.
**Fix shape:** Decide whether any v1 ledger will ever be read; if not, delete the path and the table probe.
Cost: **S** — Risk: low.

### F-33 · Strict-JSON file readers are triplicated with a 16× drift in the byte bound
Severity: **medium** — Layer 2 — Category: B.1 — Evidence: `[measured]`
Locator: see `audit/raw/B1-*`
**What is true:** Three copies of the strict JSON file-reading helper, one of which inlines the parser, with byte bounds differing by a factor of 16.
**Why it matters:** A drifted duplicate is worse than a duplicate: the same input is accepted by one entry point and rejected by another, and neither is wrong locally.
**Fix shape:** One reader, one bound, passed as an argument where it genuinely differs.
Cost: **M** — Risk: changing a bound changes what is accepted; pick each deliberately.

### F-34 · `_text` bounds in bytes in three copies and in characters in the fourth
Severity: **medium** — Layer 2 — Category: B.1 — Evidence: `[measured]`
Locator: see `audit/raw/B1-*`
**What is true:** The same validator exists four times; three bound by encoded bytes, one by character count, so the same non-ASCII string is accepted by one and rejected by another. Related: `_nonnegative` has two copies **inside the same package** with different return contracts (one returns the value, one returns `None`), and `_wire` returns `bytes` in one module and `str` in another with `_save`/`_digest` compensating differently in each.
**Why it matters:** These are the drifted duplicates, the category the brief singles out as worse. All sit on validation paths.
**Fix shape:** One definition per validator; make the byte/char choice explicit at each call site.
Cost: **M** — Risk: changes acceptance at some boundary; needs a test per call site.

### F-35 · `sequential.shared_map` is a 17-line byte-identical copy of `inspection._shared_map`
Severity: **low** (verifier corrected from high; a tag upgrade was also reverted) — Layer 2 — Category: B.1 — Evidence: `[measured]`
Locator: `src/pheroos_interaction/sequential.py` and `src/pheroos_interaction/inspection.py`
**What is true:** Byte-identical, in a module that **already imports** the other file's shared vocabulary.
**Why it matters:** Still identical today, so the cost is entirely future: two copies with no signal that they must agree, in the pure-policy layer whose determinism the rest of the system assumes.
**Fix shape:** Import it.
Cost: **S** — Risk: very low.

### F-36 · Eight multi-row `SELECT`s have no `ORDER BY`, and their scan order determines the durable event sequence
Severity: **low** — Layer 2 — Category: I / L-11 — Evidence: `[measured]`
Locator: `audit/raw/I-ast-sql-select-ordering.txt`
**What is true:** Eight multi-row selects rely on SQLite's scan order, which is not contractually stable across versions or query plans, and the resulting order determines the sequence of durable events written.
**Why it matters:** Event order is part of the replayable record. This is low because SQLite's actual behaviour is stable in practice for these queries and the agent measured the query plans, but it is an unstated dependency.
**Fix shape:** Add explicit `ORDER BY rowid`.
Cost: **S** — Risk: none.

### F-37 · The base ledger's cross-layer interface is 23 private helpers, one of which is the canonical digest serializer
Severity: **medium** — Layer 2 — Category: A — Evidence: `[measured]`
Locator: `runner/session.py` — `_wire` (`:15`), `_duration`, `_integer`, `_id`; imported across module boundaries by `platform.py`, `orchestration.py`, `runtime.py`, `colony.py`, `worker.py`, `evidence.py`, `audit.py`
Command: AST pass collecting `ImportFrom` nodes whose imported names start with `_` → `audit/raw/A-private-cross-imports.txt`
**What is true:** `[measured]` 40 private symbols are imported across module boundaries in 21 statements; **23 of them come from `runner/session.py`, whose only module-level *public* name is `Session`.** One of them, `_wire`, is a canonical digest serializer (see F-16). 7 imports are function-local (deferred), including the identical `from .platform import _loss` inside `_plan()` in **both** `worker.py:28` and `colony.py:73`.
**Why it matters:** The real interface of the most-depended-upon module is its private surface, so the leading underscore no longer signals "internal" and gives no protection against a change rippling through six modules. It also means the module's public API understates its actual contract, which is part of why five of its units have no rationale recorded (F-27).
**Fix shape:** Promote the genuinely shared helpers (`_wire` above all) to a named internal module with a stated contract; leave the rest private.
Cost: **M** — Risk of fixing: mechanical renames, but `_wire` is digest-critical — pair with the digest-stability test from F-16.

### F-38 · `provider.py`'s only public export has no production consumer; three layers import the module for a generic JSON helper
Severity: **low** — Layer 2 — Category: A / G — Evidence: `[measured]`
Locator: `runner/provider.py:37` (`ProviderDriver`); importers `runner/runtime.py:37`, `runner/worker.py:14`, `runner/colony.py:38`
Command: repo-wide `grep -rn 'ProviderDriver'` over `*.py`, `*.md`, `*.json` → `audit/raw/A-import-statements.txt`
**What is true:** `[measured]` `ProviderDriver` has **zero** references in any `runner/` or `src/` module. Its only references are `README.md:128`, a docstring mention at `runner/worker.py:114`, and `tests/interaction/test_provider_worker.py`. All 14 cross-module references into `provider.py` are to the private `_freeze`.
**Why it matters:** Three layers depend on the provider-adapter module solely to reach a generic JSON helper, so the dependency edge misrepresents the architecture: the graph says "these layers use the provider adapter" and they do not. The README advertises a class production does not use.
**Fix shape:** Move `_freeze` to a neutral home (see F-16/F-37) and let the `provider.py` edges disappear; then decide whether `ProviderDriver` is still wanted.
Cost: **S** — Risk of fixing: low.

### Withdrawn on verification — claims that did not survive an adversarial check

Reported here rather than deleted, because a refuted claim is an audit result. All four reproduced their cited command exactly; what failed was the conclusion drawn from the observation.

| Claim (as raised) | Verdict | Why it is not a finding |
|---|---|---|
| **F-11** `pip-audit` reports the build dependency clean while auditing zero packages, so the only vulnerability check is a false negative | **not a finding** | Observations reproduce (`{"dependencies": [], "fixes": []}`), but the causal claim is false. A positive control in the same session — `setuptools==65.5.0` and `jinja2==3.1.2` — *does* report vulnerabilities. `setuptools>=84` resolves to a version with no advisories; nothing is skipped. The original finding's `command:` field was also not runnable (`-r` takes a file, not a requirement string). |
| **F-13** `waiting_rule` clocks a commitment decision on the live wall clock while documenting itself as ledger-clocked | **not a finding** | The behaviour reproduces exactly (verifier varied only the injected clock over four byte-identical ledgers: elapsed ticks 0/1/3/150 → wait/wait/publish/publish). But it is the **explicitly documented and explicitly tested contract**: `docs/orchestration-architecture.md:379-382` gives the formula verbatim, `runner/worker.py:68-70` names `now` separately from the ledger stamp, and `tests/interaction/test_orchestration_*` covers it. A documented domain distinction, per the brief's "not a finding" rule. |
| Replay's `readable_artifacts` ignores its `agent` argument, so offline audit applies none of the live authorization checks | **refuted**, downgraded to low | `pylint W0613` reproduces, but the authorization conclusion does not follow; the tag had been upgraded from `[inferred]` and was reverted. |
| `CoordinationSession.dispatch` copies `Session.dispatch` verbatim instead of overriding the hook built for it | **refuted**, downgraded to low | Explicitly justified at `runner/evidence.py:284-285`: the tool/arguments check must happen "at the same durable boundary that checks cancellation and current source access". A domain distinction. This correction also reshaped the lead auditor's §B.2 conclusion — see F-17. |


---

## 6. Top 5

1. **F-01 — the orchestration layer is untracked.** It is the root cause of F-09 and F-10, it makes §H blind to 54.2% of files and §J unable to use git for the code with the least written rationale, and it is the only finding where the artifact can be *lost* rather than merely wrong. Everything else in this report is recoverable from the code; this one is about whether the code exists anywhere else.
2. **F-02 — a forged allocation replays PASS.** The only finding that falsifies a promise the codebase makes in its own words. For a governance runtime, an attestation surface with an unstated hole is worse than no attestation, because the `PASS` will be cited.
3. **F-04 — the allocation draw is never persisted.** The mechanism behind F-02, and independently the reason the L2 layer's behaviour cannot be measured after the fact. Fixing it fixes F-02 and unblocks any quantitative use of the four-cell design.
4. **F-07 + F-06 — the central guarantees are each held by one or two test files.** The allocation policy can be deleted and 1,007 of 1,016 tests still pass. This is why F-02 survived to be found by an audit rather than by CI, and it is cheap to fix.
5. **F-15 + F-08 — the two functions that decide what is valid and what is verified are the two least maintainable in the repository.** MI 0.00 and CC 68. They are where the next correctness defect will be introduced, and where it will be hardest to see.

These beat the rest because the remainder — duplication drift, complexity, unused parameters, doc staleness — are *costs*, while these five are *the system being unable to substantiate its own central claims*.

---

## 7. Needs human judgment

Framed as questions. Nothing here is asserted as a defect.

1. **The parallel lease release differs on `epoch`.** `runner/session.py:145` writes `UPDATE work SET status=?,owner=NULL,expires=NULL` while `runner/evidence.py:279` writes the same plus `epoch=epoch+1`. The contexts differ (lease-expiry recovery vs source-update invalidation). The adjacent override is explicitly justified at `evidence.py:284-285`, but that comment does not address the epoch. **Is the epoch advance a deliberate difference between the two invalidation paths, or did one path acquire it and the other not?**
2. **`latency_cost` denotes two different quantities.** It is a commitment parameter in `src/pheroos_interaction/commitment.py:141` and an allocation parameter in the capacity model. The L-8 check excused the commitment hits on exactly that basis. **Should these share a name?**
3. **Is `runner/colony.py` canonical, superseded, or a reference implementation?** `[measured]` It is the only module unreachable from any CLI entry point, has no call site outside `test_colony.py`, and is a drifted fork of `run_worker` (F-18) — yet the README leads with the colony control layer. **Which of the two loops is the one that ships?**
4. **`orchestration_tasks_v2` alongside four `_v1` tables.** **Is the `_v1` suffix on artifacts/accounting/decisions still accurate, or did the schema generation advance as a whole?** (F-05)
5. **The E4 response arm never crosses its threshold.** With cost 6 vs 1 the break-even is 5 and the reachable backlog is 3, so `expensive` is unconditionally priced out at all twelve consultations rather than responding to load. These are the parameters the owner specified. **Is a constant-in-backlog demonstration the intended scope for the preflight, or should the prices be re-set so the same agent claims under load and defers without it?** Re-pricing to obtain a mechanism flip is close to the parameter-fishing the owner warned against, so it is posed rather than done.
6. **`_offered`, `COMMITMENTS`, and 15 unused arguments.** The majority are base-class extension hooks and are correctly left alone. `runner/runtime.py:248-252` (`_offered`) has no caller anywhere including tests and docs. **Was it meant to be the single source for the offered-tool set that `_tool_schemas` and `_declarations` each re-derive?**
7. **Everything filed against an `[INFERRED ARCHITECTURE]` layering.** None. The declared layering was recoverable from §L, `AGENTS.md`, the architecture doc and module docstrings — evidence-order steps 1–3 — so no candidate layering was inferred and nothing was convicted against one.

---

## 8. Open rationale questions (§J)

Ten most structurally important units by inbound call count (`audit/raw/20-loadbearing.txt`). **Answer constraint applied: DOCUMENTED cites a source, STRONGLY IMPLIED cites code/tests and states the inference, UNKNOWN means no rationale was found. No rationale is supplied on the author's behalf.**

Note on evidence availability: for the seven untracked modules, `git log` returns 0 commits, so commit-message and blame evidence is **unavailable by construction** — those units can reach DOCUMENTED only via in-file prose. For `session.py`, blame is available but `[measured]` misleading: its birth commit is a flattened squash of an unmerged branch.

| # | Unit | Inbound | Rationale | Basis |
|---|---|---|---|---|
| 1 | `Session.snapshot` `session.py:433` | 350 | **UNKNOWN** | No docstring. 4 commits, all coarse-grained; birth commit is a squash. Nothing states why the whole-ledger projection is the primitive rather than targeted queries. |
| 2 | `ToolRegistry.execute` `tools.py:212` | 243 | **DOCUMENTED** | 224-char docstring; untracked, so in-file prose is the only possible source and it is present. |
| 3 | `Runtime.run` `runtime.py:655` | 173 | **STRONGLY IMPLIED** | 79-char docstring states *what* (one step per task per sweep), not *why* that bound. The sweep-budget computation at `:658-668` and `test_orchestration_workflow.py` termination tests imply the reason is guaranteed termination under decomposition. Inference stated, not documented. |
| 4 | `Session.claim` `session.py:152` | 161 | **UNKNOWN** | No docstring. Lease epoch semantics, the `generation` column and the never-retry rule are all decided here; no source states why. |
| 5 | `contracts.wire` `contracts.py:42` | 65 | **UNKNOWN** | No docstring. It is the canonical digest serializer for the whole system and one of six definitions (F-16); nothing states which is authoritative. |
| 6 | `PlatformMixin.commit` `platform.py:392` | 61 | **DOCUMENTED** | 218-char docstring, plus `README.md:150` and the architecture doc on the commitment boundary. |
| 7 | `Session.reserve` `session.py:201` | 47 | **UNKNOWN** | No docstring. Reserve-before-dispatch is the core authority invariant; the *rule* is documented in `README.md:181`, but not at the unit that implements it. |
| 8 | `PlatformMixin.ready_work` `platform.py:171` | 41 | **STRONGLY IMPLIED** | 74-char docstring: "expired leases are projected, recovered only on claim". Why projection rather than recovery is implied by `test_orchestration_recovery.py`'s crash cases (a read must not mutate), not stated. |
| 9 | `contracts.workflow_spec` `contracts.py:507` | 38 | **DOCUMENTED** | 86-char docstring plus `docs/orchestration-architecture.md`. |
| 10 | `Session.receive` `session.py:274` | 38 | **UNKNOWN** | No docstring. The settlement transaction — including the `_settled` hook folding usage in — is decided here. |

**Score: 3 DOCUMENTED, 2 STRONGLY IMPLIED, 5 UNKNOWN.** All five UNKNOWNs are in `runner/session.py`, the module with the highest inbound dependency count in the repository.

**Core-guarantee vs implementation tests.** §C.2 answers this directly rather than by inspection: `workflow_spec` (S1: 140 failures), `conforms` (S2: 128), `validate_schema` (S4: 83) are protected at the guarantee level. `select_work` (S3: 9 failures, 2 files), `worker_order` (S8: 3 failures, 1 file) and `_require_executable` (S6: 1 failure) are protected only narrowly — F-06, F-07.

**Decisions encoded with no recorded reason:**
- `64` appears as a bound in eight places in `contracts.py` with no named constant and no stated basis (`audit/raw/33-magic-constants.txt`).
- `quorum_frac=.45, margin=.05` at `runner/runtime_policies.py:196` — cross-inhibition parameters, unexplained.
- `DEFAULT_LEASE_SECONDS = 60` and eight independent `lease_seconds=60` defaults. `[measured]` The runtime overrides all of them (`runtime.py:372,495,503,613,625`), so they are latent rather than active — but nothing states why 60.
- `epsilon=1e-12` across four `sequential.py`/`inspection.py` entry points.
- **Clean:** every "never"/"must not" comment found in `runner/` states its reason. There are no bare "do not change this" comments and **zero** TODO/FIXME/HACK/XXX markers anywhere in scope.

---

## 9. Epistemic overclaims (§K)

513 claim sites extracted (`audit/raw/30-claims.txt`). Most "cannot"/"never" strings are **prescriptive refusals** — correct descriptions of a rule the code enforces — not claims about the world. A third candidate promotion was raised and **refuted on verification** (see §5 Withdrawn). Two genuine promotions survive:

1. **AVAILABLE → ACTIVE.** `outcome.metrics.policies.runtime_policies = {"allocation": "response", "lease": "fixed"}` (`runner/runtime_policies.py:244-258`, emitted at `runner/runtime.py:653`). Every other key in the `metrics` object is a measured count — `model_calls`, `tool_calls`, `artifacts`, `decisions`, `known_tokens`. These two are **read from the frozen spec declaration**, and `[executed]` the ledger contains no record of any allocation decision (F-04). **What the system knows:** "the spec declared the response arm." **What the string claims, by its container and its key name:** "the response policy ran." The codebase already made exactly this distinction correctly for commitment — `platform_capabilities.commitment.active_decisions` is sourced from the ledger — and did not apply it here.
2. **DERIVED → OBSERVED.** `docs/orchestration-verification.md:84` and its table state per-file test counts as fact; `[measured]` 2 of 8 are stale (F-24). A hand-written count presented in a verification report reads as a measurement.

**Correct by construction — noted because they are the hard cases and the codebase got them right:**
- The deferral reason at `runner/runtime.py:736` reads *"the allocation policy deferred every ready task and no declared cheaper capacity produced progress"* — it reports what was observed and does **not** claim cheaper workers do not exist. This is exactly the brief's worked example, and it is already correct.
- `README.md:226`: *"offline replay verifies the record, not the world"* — honestly scoped. **The residual gap is narrower than an overclaim:** "verifies the record" would naturally be read to include the allocation recorded in it, and F-02 shows it does not. The exclusion is unstated rather than misstated.
- `runtime_policies.describe()` separates what ran from what was available, and `active_decisions` comes from the ledger (L-5 holds).
- `worker.waiting_rule`'s tick semantics — raised as an overclaim and refuted. `docs/orchestration-architecture.md:379-382` states the formula verbatim, `runner/worker.py:68-70` names `now` separately from the ledger stamp, and a test covers it. The contract is documented, not misstated.

---

## 10. Not run

| Check | Reason |
|---|---|
| **§C.1 mutation testing** | mutmut 3.x generated **233 mutants** for `runner/runtime_policies.py`, then its "Running stats" phase did not complete under non-interactive output capture; `mutmut results` reports every mutant as *"not checked"* — **0 executed**. No surviving-mutant percentage exists and **none is estimated**. §C.2 controlled stub mutation was executed instead (8 stubs, full results in §4). `audit/raw/22-mutmut-NOTRUN.txt` |
| **gitleaks, trufflehog** | Not installed and not available; secrets reported from bandit plus a documented regex sweep, which is **not** claimed as a substitute. |
| **osv-scanner** | Not installed. |
| **jscpd** | Not available; §B.1 used pylint `duplicate-code` + normalized-AST block hashing, and each result states which method produced it. No token-overlap figure is estimated. |
| **pydeps, import-linter** | Not installed; the import graph came from grimp 3.17 as a library. |
| **§H churn, blame, numstat for 16 files** | **Untracked — no git history exists.** 3,934 source LOC and 5,913 test LOC invisible to every git-based measurement. Reported per file, no estimate substituted. |
| **§H 12-month churn window** | The repository is 99 days old; the window does not exist. Reported as a structural 0%, not an estimate. |
| **§H line-level re-fix attribution** | 24 of 35 tracked scope files have a single commit and the birth commit is a flattened squash, so blame attribution is known to be wrong. Running it would produce confidently wrong output. |
| **§G git blame on oldest TODO markers** | No input: **zero** TODO/FIXME/HACK/XXX markers exist in scope. |
| **§G churn-weighted complexity** | Five of the seven highest-complexity modules are untracked. |
| **Registry existence for local packages** | Not applicable in the direction that matters: the project declares **zero** runtime dependencies, and the stdlib-only claim was **verified** by AST rather than repeated. Registry checks were run against the build requirement and dev extra only. |
| **npm audit** | No JavaScript in scope. |

---

*End of findings. No source file, test, manifest, lockfile or CI config was modified; the SHA-256 manifest assertion in §2 is the proof. Remediation has not begun and will not begin without approval.*
