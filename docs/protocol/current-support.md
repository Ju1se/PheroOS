# Current Support Matrix

Applies to `pheroos 0.1.0` after the D-06–D-14/private-attention cleanup,
audited at `2225f3f`. PheroOS supports governed authority/commit contracts.
This matrix describes interface support, not demonstrated swarm intelligence,
production readiness, or a published Stable release.

| Capability | Interface/version | Status | Verification entry |
| --- | --- | --- | --- |
| Baseline manifests, quorum, fallback, output | `pheroos.protocol.v1`, `pheroos-core-v1` | Public Draft | `pheroos conformance examples/toy-protocol` |
| Scoped authority and Baseline Output | Capability/Protocol schema v3, `pheroos.protocol.v2`, Store/session/output v2 | Public Draft | `tests/conformance/test_authority_store_v2_contract.py`; `examples/scoped-output-protocol/run.py` |
| Scoped Hybrid Replay | Hybrid Replay v2 on Store-backed authority | Public Draft; replay/currentness contract | `examples/hybrid-replay-protocol/run.py` |
| Optimal/Hybrid Commit, certificates, finality | Assurance-specific Commit v1 profiles; exact v2 durable contracts | Public Draft; attention cannot issue authority | `tests/conformance/test_commit_integrity_conformance.py`; `tests/conformance/test_commit_tck_v2.py` |
| Driver invocation and scoped Trace stores | `DriverInvocationStoreV2`, `ScopedTraceStoreV2`; Runtime Integration v1 | Public Draft, replaceable adapters | `tests/conformance/test_runtime_integration_v1_contract.py`; `tests/conformance/test_scoped_trace_store_v2_contract.py` |
| Small consumer surface | `pheroos-stable-python-api-v1`: 37 roots, 121-symbol closure | Draft promotion candidate, `formal_stable=false` | `tests/typing/stable_consumer.py`; `tests/packaging/test_stable_candidate_distributions.py` |
| Attention/pheromone scoring | Private implementation; legacy manifest metadata | Experimental; no public pheromone exports or swarm profile | Internal tests/fixtures do not confer a public ABI or efficacy claim |
| Experiments, datasets, model calls, statistics | Independent `pheroos-bench` package in this repository | Research tooling; separate dependencies and delivery | `pheroos-bench/tests/`; its build/install checks |

All 1,232 exports across the six public facades are **Draft**. The small
consumer candidate is the recommended starting point; it is not a facade
removal or formal stability promotion. Consumers pin an exact artifact or
commit and the versions they implement. See the
[consumer contract](stable-core-consumer.md) and
[API lifecycle](../process/api-lifecycle.md).

## Sources and refresh

Exact membership and lifecycle come from the
[public inventory](../../pheroos/conformance/abi/public-python-api-v1.json),
[lifecycle inventory](../../pheroos/conformance/abi/public-python-api-lifecycle-v1.json),
[candidate inventory](../../pheroos/conformance/abi/stable-python-api-v1.json),
and [runtime compatibility manifest](../../pheroos/conformance/abi/runtime-compatibility-v1.json).
The [profile selector](../../pheroos/conformance/profile.py) owns current
manifest dispatch. Without a Commit declaration, legacy swarm/Hybrid
manifests select `pheroos-core-v1`. Neither `pheroos-swarm-v1` nor
`pheroos-hybrid-swarm-v1` is an active public profile. Hybrid Commit retains
its declared attention bounds and attention/authority separation checks.

For a reviewed interface change, run the existing inventory generators with
`--check`, inspect the ABI diff, and update this matrix, the candidate consumer,
tests, and migration notes as applicable. A mismatch needs an explicit
contract decision; do not refresh machine artifacts merely to make a check
green.

## Where new behavior belongs

| Owner | Changes it accepts |
| --- | --- |
| Core | Protocol/capability declarations, Governance semantics, Trace, versioned contracts, compatibility tests |
| External runtime | Scheduling, execution, cancellation, retries, run recovery, external effects |
| External adapters, optionally maintained with runtime | Concrete model, tool, and storage backends implementing public contracts |
| Bench | Datasets, experimental algorithms, controls, measurements, statistical methods |

An extension should primarily change its owner. Prefer the existing Driver,
Store, and Trace contracts; verify a replacement through the same contract
tests from an installed package and an external working directory. See
[extension points](extension-points.md).

## Historical material

The [Hybrid Pheromone ABI](hybrid-pheromone-abi.md), its
[v1 migration](hybrid-pheromone-v1-migration.md), and the July 2026
[hardening plan](../process/production-readiness-hardening-goal-plan.md)
preserve earlier design and execution evidence. Their old export counts,
swarm support descriptions, and planned release actions apply to the recorded
versions/checkpoints. This matrix and the current inventories supersede those
support descriptions; they do not retroactively change recorded experiments.
