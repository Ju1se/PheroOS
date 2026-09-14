**Outer campaign integrity: PASS.** The independent [audit](campaign-audit-v1.json) reconciles the campaign records and 680 input hashes before and after review. It does not validate the inner episode databases, raw receipts, authority decisions, evaluator outcomes or paired exports. Those remain subject to the separate full-grid audit and root R4 gate decision; this report does not authorize R5.

The new campaign records one fresh 264-row attempt covering the original 66 conditions and four worlds. Its inner freeze and seeded order are byte-identical to the original. All 641 frozen source identities, 19 model-file hashes and four separately frozen campaign files match. The separately pinned original audit is `ACCOUNTING_AND_ABORT_INTEGRITY_PASS`; its source remains `INVALID_ABORT` with no usable whole-grid export. Original evidence and the interrupted episode remain unchanged.

Both retained accounting tables independently reconcile by row and counter:

| Reported counter | Original known subtotal | Replication | Combined known subtotal |
| --- | ---: | ---: | ---: |
| Actual tokens | 2,824,212 | 3,402,842 | 6,227,054 |
| Model calls | 5,891 | 7,134 | 13,025 |
| Tool calls | 5,890 | 7,085 | 12,975 |
| Control operations | 186,609 | 220,957 | 407,566 |

The original has 205 reported rows and 59 null accounting rows, indexed 205–263. The replication has 264 reported rows. Reserved tokens, unknown tokens and unknown calls have zero reported subtotals; the original missing rows remain explicit. Combined figures are therefore known subtotals, not complete totals. Monetary cost remains null. This checks the preserved summary counters; raw receipt and SQLite accounting are outside this audit.

The outer campaign ran from **2026-09-13 19:19:30.674515 UTC** to **22:20:14.775078 UTC**: 10,844.100566093 monotonic seconds, 10,844.100563382 realtime seconds and 10,844.100564739 boottime seconds. These include identity checks and observation overhead and are not GPU time.

The observer retained **2,164 samples / 462,702 bytes**, including startup and finish, under the declared five-second nominal period and 20,000-sample cap. Sample gaps ranged from 2.776263764 to 7.438088911 seconds; the short final gap follows explicit shutdown. Maximum absolute realtime-minus-monotonic interval difference was **3,822,289 ns**; maximum boottime-minus-monotonic difference was **3,819,173 ns**. Every recorded interval and summary value reconciles. The wrapper reports successful join and no observer errors. These are bounded sampled diagnostics with no newly applied anomaly threshold. They do not establish continuity between samples, an environmental cause, production resilience or soak maturity. Observer overhead stays separate from episode `call_units`.

Exact artifact identities:

| Artifact | SHA256 |
| --- | --- |
| Campaign freeze | `aa759c38385bdb3f8852b38e02b5eed5e4de222b983353a63037fad4bd9ba709` |
| Campaign summary | `f3af8ebe41f939d15dbc2366cf356540cdc1db955b456c0514b1c2b17654c8ee` |
| Clock observations | `38cae17d617a14e4ff81e73979c37b53fb3bc3dcc2630ae4fe109d1212af371d` |
| Original and replication inner freeze | `fc535ea621a7d26582fd2888cac088b1f3f0604efdb98a4b54d0bdf147714e1c` |
| Original independent abort audit | `723d36f07fc5cccd1466d55ca6e890983c0a41f68c817e7212189666c31d8bf5` |
| This audit JSON | `987b314cdef771eb982a14b62a266798403ccbb776338ce81b37be71ac82720b` |

The [retained audit source](campaign-audit-v1-source.py) is byte-identical to the executed temporary script: `ead50e42073b3bd2d5fef07a2534b80efb9b257842432ca85d6b3c38f6fb62a4`. It imports no runner or runtime and creates only the exclusive additive audit report.

The final full bench regression used `/home/scott/projects/PheroOS/pheroos-bench/.venv/bin/python -m pytest -q -rs`, with cwd `/home/scott/projects/PheroOS/pheroos-bench`. The interpreter resolves to `/usr/bin/python3.12`, Python 3.12.3. Result: **1,171 passed, 17 skipped in 16.67 seconds; exit 0**. All skips require the separately installed Session runtime absent from the bench environment: 15 R3 capability cases, one R4 Session test module and one R4 measurement integration case. [Exact command, interpreter, output and skip reasons](../master-goal-audit-v1/bench-post-replication-validation-v1.json) are retained with SHA256 `d781777d01c3093f62a9f04b12dc7cab6cc63bc075b32b97941aaab937d53cb6`. No R5 study was invoked, and no frozen evidence or source was modified.
