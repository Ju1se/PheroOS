# Coordination repair v2: prepared retry

**PREPARED_NOT_EXECUTED.** This directory contains a reviewable successor to the retained pre-dispatch abort. Creating this proposal and publishing code do not authorize another actionability campaign. The next-cycle Goal remains incomplete.

## Problem, hypothesis and mechanism

The first v1 actionability attempt stopped before inference because fractional adapter metadata failed existing current-authority validation. Runtime `0.1.0.dev3` already supplies `recorded_local_v2`, which uses explicitly labeled decimal strings for metadata and inherits the same generation implementation. This bench cohort `0.1.1.dev3` selects that adapter from a separate runner. The coordination hypothesis, tasks, policies, seeds, sampling, budgets per episode and diagnostic thresholds remain unchanged.

The v2 episode wrapper executes the frozen v1 policy/runtime path, preserves its original JSON, and writes a hash-bound `episode-v2.json`. Preparation now counts as verified progress; imported prefix knowledge does not count as new branch progress. Permission errors are classified explicitly. Configured inference capacity and actual dispatched work are separate.

Mailbox delivery and repeated prompt exposure are distinct measures. This consumer does not send mailbox messages: delivery/duplicate counts are zero with `CHANNEL_NOT_USED` and a null duplicate rate. Unexpected sends leave unobserved deliveries unknown. Exact repeated prompt messages are counted only for dispatched model requests; they are not multi-agent message duplicates or independent evidence.

## Baselines and experimental design

The unchanged controls are single agent and blackboard plus provenance dedup/TTL at N=2/4. Candidate N=2/4 and ownership/reuse ablations share the same finite tasks, tools, evaluator, accounting and interface. The proposal retains 28 actionability cells, 28 conditionally admitted collaboration parents and up to 12 sharing branches. All possible allotments total 499,712 tokens.

The old campaign's one conservative intent slot remains reserved: the new cohort admits at most 999 additional intents, within the original combined ceiling of 1,000. Its zero known/unknown model tokens and three settled preparation tools remain explicitly referenced. The total token ceiling remains 500,000. Running an additional actionability campaign requires separate authorization because the original Goal allowed only one. No paid API, new model download or confirmatory study is proposed here.

## Implementation and tests

The new runner verifies the predecessor's exact raw hashes, requires an explicit additional-campaign assertion, freezes config/source identities before loading a model, appends progress, and writes terminal records once. It preserves loader failures, attempted-but-unreturned episodes, missing usage, unknown accounting, source drift and unstarted rows. Later phases recompute admission from complete source-bound records. Invalid/incomplete whole phases cannot emit valid subset statistics or paired exports.

The versioned fork loop preserves v1 knowledge, source schedules, access, seeds, branch budgets and authority separation. It stops after invalid, unresolved, incomplete or source-drift observations and retains unstarted branches with null outcomes/costs. The existing statistical methods keep their meanings; valid completed phases still use `r_paired_world_mean_v1` and `coordination_repair_nested_forks_v1`.

Validation receipts are in [regressions](regressions). The first installed build passed 147 tests before a later review exposed missing whole-phase analysis gating. Its exact wheel remains at `artifacts/`. The corrected, independently installed wheel is under `artifacts/accepted/`; use its hash and `regressions/installed-dev3-final.json`. This engineering build history is preserved and adds no pilot observation.

## Results, negative findings and limits

No learned model was dispatched for v2 and no live pilot result exists. The earlier v1 reference finding remains 0/8 actual action/evidence changes between candidate and control. New tests establish finite reporting and orchestration behavior only. The four constructed task families and finite source-acquisition scheduler remain narrow; coordination efficacy, strong-model calibration, physical GPU scaling and long-running reliability remain unmeasured.

Additive audit correction: item 7.1 in the frozen v1 completion checklist summarized `call_units` incompletely. The unchanged exporter uses **model calls + tool calls + control operations**. Those logical units are not monetary cost or physical I/O. The v1 implementation and its historical audit bytes are preserved.

## Reproduce and next gate

From the current repository checkout, use the existing Python 3.12 validation environment:

```sh
python pheroos-bench/tools/verify_coordination_repair_install.py --bench-cohort dev3 --runtime-cohort dev3 --output /tmp/repair-v2-install.json
python pheroos-bench/tools/verify_coordination_repair_install.py --bench-cohort dev3 --runtime-cohort dev2 --output /tmp/repair-v2-legacy-install.json
```

Both commands require fresh output paths and run with retained core/runtime wheels, local bench build and no model/provider calls. The installed dev3 job includes mandatory Session integration; missing-runtime skips cannot count as a pass. Existing v1 tests run for both runtime cohorts.

The v1 publication manifest describes commit `9393527fd830aff218b2f41b44438a1aa4136cf3`. Verify it in a separate checkout of that commit: the current package version and installation CI deliberately describe the new cohort. Original experimental modules, configs, results and distributions remain byte-identical. The v2 publication manifest verifies the current changes separately.

The proposed live entry point is `pheroos_bench.coordination_repair_v2_pilot`; it requires `pilot-config-proposal.json`, a fresh output directory, the existing exact local model, the v1 predecessor directory, and `--authorized-additional-campaign` after explicit user authorization. The flag records an operator assertion; Session still supplies current execution authority independently. Until authorization arrives, keep this configuration unexecuted. After actionability, apply the unchanged diagnostic and intervention gates before any collaboration collection.
