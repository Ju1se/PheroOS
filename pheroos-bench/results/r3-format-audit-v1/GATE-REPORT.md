# R3 format diagnostic v1

Original outcomes remain **{'failed': 20}**, with **0/160 valid actions**. Every original call and its cost is retained in `calls.jsonl`; historical evidence is untouched.

Format classifications: `{"sole_json_fence_object":160}`. Unwrapping only a sole lower-case JSON fence, without editing its contents, yields **14 posthoc public-valid actions** against their original histories. Main admissions: `{"inspect":10,"submit":1}`; probe admissions: `{"inspect":3}`. These are potential parser admissions, not observed successful rollouts, authorized publications, or collaboration gains.

Actual original usage remains **55,154 main tokens + 19,761 probe tokens**; unknown tokens are zero. This offline audit made no model calls and did not run the hidden final scorer.

A separately frozen capability-admission pilot is justified to distinguish the exact action-format failure from other capability limits. It must declare any normalization rule, prompts, tasks, evaluator, limits, and stopping decision before calls; give every policy the same interface; and preserve failures and costs. This audit does not pass G5, justify an R4 efficacy comparison, or promote a policy. No original history was rewritten and no normalized artifact was propagated.

`manifest.json` binds every source evidence file, the verified historical source freeze, and this audit's source/tests. `summary.json` and `calls.jsonl` are explicitly posthoc diagnostics with `counts_toward_verdict=false`.
