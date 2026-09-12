---
experiment: pheroos-e3
stage: prospective design draft
status: NOT_FROZEN
date: 2026-09-12
estimand: paired_item_mean_v1
provider_calls_in_this_revision: 0
---

# E3 prediction and power-planning draft

This is a proposed plan after the statistical review, not an existing
preregistration or authorization to collect data. No confirmatory config is
published with it. The method revision changes the estimand; historical runs
must retain their original method and provenance.

## Question and prediction

Under matched total-token caps per item/arm/repetition, does the proposed
adaptive-K interaction policy improve mean exact-match accuracy relative to
an independently randomized stopping control and all declared static controls?
This asks about quality under a cap. Actual spending can differ; quality per
token or tokens needed to reach a target quality is not a confirmatory endpoint.

The working directional prediction is a positive adaptive-K effect against
random stopping if its signal identifies useful additional computation.
Confidence is low: signal computation consumes budget, and a strong static
control or uninformative signal could eliminate the gain. A five-percentage-
point accuracy gain is a **planning example**, not a calibrated forecast or
frozen minimum effect. Failure to reject superiority is not evidence of zero
effect; interpret the effect interval against the chosen meaningful effect.

## Proposed analysis

Use the versioned [data contract](../../E3-data-contract.md): average repeats
within each item, pair arm means, then average item differences. Bootstrap
items within benchmark strata. Use a two-sided 95% percentile CI (nominal
directional alpha 0.025), with 10,000 resamples proposed for the frozen run.
The median is a robustness diagnostic only. Degenerate primary/co-primary
intervals are inconclusive, never automatic successes.

Overall success requires the primary comparison, every static comparison,
and a calibrated mean-quality floor. The existing admission threshold and
cross-cell variance assertion remain in code, but need justification before
this plan can be frozen. A positive point estimate alone is insufficient.

## Synthetic sensitivity, not full experiment power

Reproduce from the installed bench package, with the bench directory as CWD:

```bash
python -m pheroos_bench.e3_power --trials 200 --resamples 499 --seed 20260912 \
  --output results/e3/synthetic-power-sensitivity.json
```

The [complete output](synthetic-power-sensitivity.json) uses the actual
`paired_percentile_ci` implementation. Control accuracy is 0.5; treatment
accuracy is 0.5 plus delta. All Bernoulli calls, arms and items are independent.
Each scenario runs 200 simulations with 499 bootstrap samples per simulation.
The implementation records the complete PRNG, draw order and bootstrap seed
schedule. These are newly generated diagnostics; the supplied draft's numerical
table was not independently reproducible without its original generator and
has been replaced with this run's results.

| Items | Repeats | True accuracy gain | Old median primary passes | Revised mean primary passes |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 3 | 0 pp | 0/200 (0%) | 4/200 (2%) |
| 100 | 3 | 10 pp | 0/200 (0%) | 142/200 (71%) |
| 100 | 3 | 20 pp | 30/200 (15%) | 200/200 (100%) |
| 100 | 5 | 5 pp | 1/200 (0.5%) | 79/200 (39.5%) |
| 100 | 10 | 10 pp | 98/200 (49%) | 200/200 (100%) |
| 400 | 1 | 10 pp | 0/200 (0%) | 159/200 (79.5%) |

The null row reports false positives, not power. These are small Monte Carlo
estimates: standard errors are up to 3.54 percentage points, and 0/200 or
200/200 does not prove exact 0% or 100% rates. The low bootstrap count is for
sensitivity diagnostics. These numbers depend on the stated generating process
and do not reproduce an audit simulation whose complete assumptions were not
supplied. In particular, R >= 10 is not a universal requirement; the 400-item,
R=1 scenario is a counterexample under these assumptions.

This only checks the primary gate. It does **not** establish power for the
conjunction of admission, primary, every static comparison and the quality
floor. It omits heterogeneous task effects, correlated decoding, provider
drift and benchmark-specific sampling. The final simulation must model those
features and report null rejection rates and joint success probability.

The retained admission rule deserves separate calibration. Under a normal
approximation, a 95% CI halfwidth is about 1.96 standard errors, so a 10-times
gate requires a gap exceeding about 19.6 standard errors. With independent
0.5 versus 0.6 accuracy and R=3, the paired-difference variance is approximately
0.49/3. Around 6,275 items **per benchmark** would merely make the expected
0.10 gap equal this threshold; that is not an 80%-power sample size. Raising
R to ten is not, by itself, a justification of the full admission design.

## Decisions required before freezing

| Decision | Required content |
| --- | --- |
| Policy | Executable adaptive-K signal, threshold, update and stopping rules; overhead charged to its cap. |
| Random control | Distribution and seed schedule fixed using separate design data; stopping draws independent of current item answers, correctness and K's realized trajectory. |
| Static controls | Exact N set, diversity mechanism, prompts, aggregation and deterministic tie rule. The current runner supports homogeneous static only. |
| Population | Named benchmark versions, sampling frame, distinct item IDs, benchmark weights and disjoint pilot/admission/confirmatory sets. |
| Model | Exact provider/model version, decoding settings, tokenizer, pricing basis and data-handling terms. |
| Effect and size | Scientifically meaningful mean gain, target joint power, item counts and R justified under realistic variance/correlation scenarios. |
| Gates | Justification or prospective versioned revision of the 10-times admission rule and cross-cell variance assertion; calibrated mean-quality floor. |
| Budget | Total-token caps including all control calls, total experiment call limit and a verifiable pre-dispatch input/output pricing bound. |
| Provenance | Frozen config, source/data/prompt fingerprints and an immutable timestamp before confirmatory collection. |

No outcome-based tuning or optional stopping is proposed. Stop once the fixed
grid is complete, or abort on accounting failure, model drift, execution error
or a declared resource limit. An aborted/incomplete run is not a statistical
negative result. Missing outcomes must not be selectively dropped or replaced;
any restart rule must be frozen before collection. No automatic paid POST retry.
Any outcome-driven revision requires a new plan and fresh confirmatory data.

The harness remains outside protocol-core. Experimental controllers have
`authority_scope="none"`; this draft grants no commit, publication or provider
execution authority and does not satisfy any existing research qualification
gate. Freeze the adaptive policies and full-design power analysis before
calling this a preregistered E3 experiment.
