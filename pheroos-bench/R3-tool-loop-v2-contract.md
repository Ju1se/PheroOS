# R3 tool/action loop v2

Method `r3_tool_loop_pilot_v2` is a finite engineering pilot, not a confirmatory
experiment or a promotion of the R1/R2 candidates. It responds to v1's observed
serialization/provenance failures and lack of useful semantic adaptation. The
four worlds have already been observed; they are not held-out evaluation data.
V1 code, configuration, outcomes and gates remain frozen and unchanged.

All five arms use the same Qwen2.5-Coder-1.5B-Instruct local weight revision,
float16 CUDA adapter, sampling, verifier, tool interface and call budget. There
are six generation turns per episode, 256 maximum generated tokens per call,
2,048 prompt-plus-generation tokens, and a 12,288 total token cap. The grid is
four worlds by five arms: 120 main calls. One resident model runs sequentially;
logical agent identities do not imply GPU concurrency. Every attempted episode
is retained; no stronger model, remote API, automatic retry or CPU fallback is
used. Existing runtime development-authority limitations still apply.

The explicit actions are `inspect(target)` and `submit(candidate)`, represented
as exact JSON objects. Code submissions use a `code_lines` array joined once
with newline characters before the unchanged v1 verifier. There is no automatic
repair of malformed JSON, nested fences, alternate keys or missing citations.
Code tests and closed-document contents are available through the same inspect
tools in every arm. Instructions, initial code, test/source identifiers and
current source versions are public. A code inspection executes one visible test
against the current workspace using the bounded integer interpreter. A document
inspection returns the exact current source record. A public-valid submitted
patch updates the workspace seen through retained verified artifacts. Valid
inspection and submission receipts require fresh runtime publication authority.
No generated code is executed on the host.

- Single: one solver keeps its complete history.
- Independent: two solvers receive three turns each and only their own history;
  final selection uses the same public verifier. This is a budget-matched simple
  baseline, not six agents denied the opportunity to use a multi-step tool.
- Manager graph: three consecutive two-turn roles retain the last two records;
  this is a fixed handoff scaffold, not a learned scheduler.
- Blackboard: successive logical agents retain the last three records.
- Versioned blackboard: the same three-record bound, with current-version
  filtering and exact receipt deduplication; no efficacy promotion is implied.

After each arm selects its history, the actual offline tokenizer measures the
complete prompt. If prompt plus 256 exceeds 2,048, the oldest whole record is
evicted and the prompt/workspace is rebuilt until it fits. The identical rule
applies to all arms, including single. Every tokenizer request and removed ID
is retained and its logical transport/time counted; this makes single a solver
with a bounded context, not guaranteed unlimited history. A base task that
cannot fit aborts. A probe starts from the main call's fitted memory and removes
only the declared eligible artifacts; it may not silently evict extra records.

The workspace is a projection of accessible verified patch receipts, not a
persistent shared repository. Evicting or withholding a patch can restore the
original code. The probe therefore intervenes on access to the shared artifact
and its workspace projection, not merely a notification.

Evidence source updates occur before turn 4 in all arms. Retained stale
receipts never become current sources or authorize current submissions. Final
selection retains the latest current-version public-valid submission. Hidden
code cases are scored after each prefix and at the end, but neither hidden
scores nor cases appear in model context, tool feedback or selection policy.
Prefix curves explicitly refer to the source version current at that turn;
turn 4 is a changed task, not a drop on an unchanged quality curve.

At zero-based steps 2 and 4, every episode also runs one same-seed probe. Only
current-version verified receipts from other agents are removed from that
step's original memory; workspace projection is recomputed from the remaining
memory. The branch has identical initial task inputs and inspect permissions.
All 40 scheduled probes run, including those with nothing eligible to remove.
Probe actions are verified and authorized but do not enter the main history.
Each episode's two probes have a separate 4,096 token cap. Both branches' actual
usage and every failed action remain in the evidence; total maximum calls are
160 and maximum reserved tokens are 327,680. Main and probe costs are reported
separately and together; probe cost is never presented as free collaboration.

Actions are compared by inspect target or finite public-probe code behavior /
evidence answer and citations, not raw-text hashes. A difference with both
actions valid and an eligible removed artifact is an observed effect of access
to that artifact in this one-step fork. It is not necessarily an improvement,
a downstream rollout effect, or evidence of a general swarm advantage. Identical
prompt probes check repeatability. Invalid branch responses cannot count as a
valid action change. No threshold or efficacy verdict is declared here.

The exclusive output directory receives source/test/config/contract/model
hashes before any generation, raw prompts/responses, tool receipts, publication
requests and authority projections, main/probe durable ledgers, prefix curves,
and summaries. Transport, publication, budget and accounting errors terminate
collection as INVALID_ABORT; received usage is retained and unknown dispatched
cost stays allocated. Logical JSON transport and tool-receipt bytes exclude
physical disk/device traffic. Elapsed times are descriptive; probe interleaving
and runtime authorization overhead prevent interpreting them as pure GPU
throughput. R4/G5 advancement requires a separate review of actual evidence.
