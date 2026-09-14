# R3 local GPU pilot — 2026-09-12

**All 20 declared episodes and 80 model calls completed with known costs. The
pilot does not demonstrate an effective cooperative improvement or pass G4.**
No configuration, task, prompt or threshold was changed after results were seen.
All outputs, including malformed and incorrect proposals, remain in the record.

This is a real local inference run on RTX 5070 Laptop, using
[Qwen2.5-Coder-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct)
revision `2e1fd397ee46e1388853d2af2c993145b0f1098a`, float16, PyTorch
`2.11.0+cu128`, Transformers `4.57.3` and Python 3.12.3. One model instance served
logical agents sequentially. No model API, remote inference or paid service was
used. The earlier G1/R0 Python 3.14 environments were not replaced.

| Arm | Successful worlds / 4 | Input tokens | Output tokens | Total tokens |
| --- | ---: | ---: | ---: | ---: |
| Single agent | 2 | 8,887 | 941 | 9,828 |
| Independent proposals | 2 | 4,632 | 811 | 5,443 |
| Fixed manager graph | 1 | 6,738 | 910 | 7,648 |
| Blackboard | 2 | 8,189 | 948 | 9,137 |
| Version-filtered blackboard | 1 | 7,138 | 926 | 8,064 |

Total usage was **40,120 tokens**, with zero unknown tokens and zero pending
reservations. All arms used the same per-episode 8,192-token cap, four-call
limit, model, sampling settings, tools and verifier. Caps were reserved before
dispatch; actual usage was committed before acknowledgment. Failed candidates
consumed **31,500 tokens across 63 rejected proposals** and were not dropped.
All 80 generations and 17 verified publications went through fresh declared
public-core authority gates using the explicit development reference Store.

Every arm solved `clamp`. Only independent proposals solved `chunk_count` in
this run. Single and blackboard solved the dispatch-limit update; no arm solved
the channel-route update. Four small closed worlds and one repetition cannot
support quality noninferiority, superiority, or general model comparisons.

The run preserved nine observations where one logical agent consumed another
agent's publicly verified work and then produced different text. **These are
not nine semantic improvements:** five new proposals were rejected; the four
accepted proposals were equivalent clamp implementations or a repeated evidence
answer. The independent audit probes behavior and separates this from the frozen
raw-text metric. The run demonstrates transport, verification, authority and
accounting paths; it does not demonstrate useful semantic adaptation from shared
work, controlled causation, or swarm efficacy. No strategy is promoted.

Peak measured CUDA tensor allocation was **3,177,852,928 bytes** (about 2.96 GiB).
This is not total process/device memory or an agent-concurrency capacity result.
Elapsed time is diagnostic only: independent CPU installation tests were running
concurrently during part of the pilot, and the first arm pays warm-up costs.
The measurements must not be treated as a fair latency/throughput comparison.
No R4 scaling curve or Mac GPU replication was executed.

Validation: **304 bench tests passed**; external runtime **78 tests passed**.
Independent runtime wheel and sdist installation checks each passed **78 tests**
(42.02 s and 46.02 s), including the unchanged G1 CLI journey with result 204 and
26 units. The task verifier uses a finite AST interpreter; generated code never
executes in the host Python environment. Hidden final cases never enter prompts
or feedback. R1/R2 source and negative results were not modified for this pilot.

Evidence:

- [Frozen inputs](freeze.json), [GPU/model environment](environment.json),
  [package versions](runtime-packages.txt).
- [All episodes](episodes.jsonl), [all prompts, responses and receipts](trace.jsonl),
  [raw summary](summary.json), [independent audit](independent_audit.json),
  [audit interpretation](INDEPENDENT-AUDIT.md).
- [External installed-package acceptance](runtime-install-acceptance.json),
  [runtime test output](runtime-tests.log), [validation receipt](validation.json).

The source paths in the freeze are the paths used during execution, including
the temporary runtime checkout. Model and virtual-environment files remain local;
the model manifest binds their downloaded weight/config/tokenizer hashes.
To repeat, use the same sources/dependencies/model and a new output directory:

```bash
python -m pheroos_bench.r3_pilot \
  --config r3-pilot-v1.json --output results/r3-new-run \
  --runtime-python /path/to/PheroOS-runtime/.local/venv312/bin/python \
  --runtime-source /path/to/PheroOS-runtime \
  --model-path /path/to/PheroOS-runtime/.local/models/qwen2.5-coder-1.5b
```

The [R3 contract](../../R3-data-contract.md) remains an engineering-pilot contract,
with `counts_toward_verdict=false`. A subsequent experiment must use a new version
and freeze any new task design, mechanism or model before inspecting its outcomes.
