# Receptor-Gated Ligand Field v0.7 E1 Preregistration Qualification Audit

状态：`phase1-preregistration-rejected`；normative closure、E1 implementation、
actual runtime、Main、GoldenOracle、G2 和 G3 仍为 `NO-GO`

日期：2026-07-29

## 1. 决定

Environment-config E0 candidate 之后，没有直接复制实现或用 E0 输出指导第二个
实现。研究先建立无 `.git` 的 source-only authoring projection，并在任何代码、
config、environment key 或比较结果出现前，连续执行三轮 preregistration 与
冻结后 blind review。

三轮结果都是 `rejected`：

| Attempt | P0 | P1 | P2 | Phase 2 |
| --- | ---: | ---: | ---: | --- |
| v1 | 0 | 6 | 1 | unauthorized |
| v2 | 0 | 6 | 1 | unauthorized |
| v3 | 0 | 5 | 0 | unauthorized |

因此当前最强结论不是“E1 已实现”，而是：

> 现有四份 source bytes 尚不足以让一个 blind author 在不作 post-freeze
> 设计选择的情况下写出可执行、可逐字节比较的 E1 preregistration。

本轮明确停止 prose-only v4。先关闭 normative、source-neutral machine
contracts，再重新启动 E1。API key 不是 blocker，也不是当前允许输入。

## 2. Prospective source-only boundary

E1 authoring input 只包含：

```text
v0.7 review profile
  119802 bytes
  sha256:bbea97c5c360853a12c00bf1983f07beb7eac8f401ad3adc8f3b433d84d270e6
v0.7 fixture companion
  62097 bytes
  sha256:322365b8eb50d5479329fde2a734901e8bd96ce48bcfe1afa177588d38788360
V2 authoring checkpoint
  52105 bytes
  sha256:d0f3447d2b6cf0d09ec29aac9522a4ae66d164200f58f883528398b23c9e55c7
V2 closure design
  50024 bytes
  sha256:a462140f0a21880b479eb17e8acad0eb4e2349866210f2881de8685f769b21bb
```

输入 projection 绑定的 lineage 是：

```text
integration parent =
  4c7993d09391977b892958dc0962e9a62f200d1b
integration parent tree =
  ff481af7126e97dc8c7d0391f04c899524082faf
```

普通 branch/worktree 共享 `.git` objects、refs、reflogs 和 sibling worktrees，
不能作为不观察 E0 的隔离边界。因此 authoring 使用无 `.git` blob directory；
predecessor candidates 与 reviews 在下一轮开始前均先只读冻结。

但 host 没有 OS-enforced read allowlist 或完整 syscall audit。本轮只能
保留：

```text
bounded_process_non_exposure = false
historical_non_exposure_proven = false
cognitive_independence_proven = false
scientific_replication_claim = false
```

Fresh actor 与静态 access ledger 是有界的程序性证据，不是历史或认知独立证明。

## 3. Frozen attempt identities

| Attempt | Candidate inventory root | Blind-review root |
| --- | --- | --- |
| v1 | `sha256:2d39d42b...054905b2` | `sha256:82038a5b...e9fae00` |
| v2 | `sha256:d11561bb...6d59070` | `sha256:cd1e316c...965a77b` |
| v3 | `sha256:7503a0a8...cd1a142` | `sha256:517afea8...965a77b` |

完整 roots 为：

```text
v1 candidate =
  sha256:2d39d42bf674d4a787b3e3843b0ff13b49da21a3115e9e4a0d37f812054905b2
v1 review =
  sha256:82038a5be442422d9818e7f84a0b163545d0ced3ed33dc8a702626598e9fae00
v2 candidate =
  sha256:d11561bb1a5118579d775007cb9a59a89c8552fd9cb842bd5bd6244786d59070
v2 review =
  sha256:cd1e316c299b8cd96854af757dac51b6b099fd67a01b26b800a8c192aafd851e
v3 candidate =
  sha256:7503a0a876df06fc0bd16a673410117e3bb56d73aab1376c88c110eebcd1a142
v3 review =
  sha256:517afea80801fbb62aec28b440db1db372285740d24d18c097c172795965a77b
```

Machine attempt ledger 位于 external qualification bundle：

```text
branch =
  codex/v07-e1-prereg-qualification
external commit =
  a7a51a704a61ea8b9abae07c95e2ba45a3912467
artifact =
  qualification_artifacts/e1_phase1_prereg_qualification/
bundle inventory file count = 49
bundle inventory root =
  sha256:415cea4127ce3b86139b3b056c2a81383d1a23dedf4ac1eeff089eb13da4513a
verifier =
  src/rglf_lab/e1_phase1_prereg_qualification.py
  29739 bytes
  sha256:a5b03a4ea7175c5cc0f1b446e0d6b3f9badc954b07b9fb116d4e13f8e101703d
tests =
  tests/test_e1_phase1_prereg_qualification.py
  5774 bytes
  sha256:7822903bb098a236314beb06def5bdd4e5fa547f25ce2b1479830794c97678f0
```

Bundle 的 integration seal 自身不进入该 inventory-root preimage。

Targeted verification 得到 `6 passed, 10 subtests passed`；Ruff、mypy、
`compileall`、deterministic verifier invocation 与 `git diff --check` 均通过。
未运行 full test discovery，因此这里不声称 full suite green。Verifier 只证明
frozen bundle preservation 与 recorded NO-GO semantics，不实现 E1。

## 4. 为什么三轮都没有进入 implementation

### 4.1 V1

V1 没有闭合：

- exhaustive two-way rule provenance；
- `document_prefix` selector grammar；
- typed source/derived fact variants；
- Phase 2 verification package；
- executable attacks 与 refusal behavior；
- exact comparison view 与 non-authorizing join。

Blind review 为 `P0=0, P1=6, P2=1`。

### 4.2 V2

V2 增加 13-field mapping、artifact schemas、literal case IDs 与 false claim
vector，但仍把 structural presence 当成 executable closure。具体仍缺：

- 自洽的 rule-bearing predicate 与完整 source entailment；
- JSON selector byte-span/EOF semantics；
- literal derived-fact identity；
- independent verification 与 A/B replay bindings；
- total mutation/retained-evidence semantics；
- unique-key join claim schema。

Blind review 仍为 `P0=0, P1=6, P2=1`。

### 4.3 V3

V3 关闭 JSON lexical span、unique join claim keys 和 final author-action ledger，
但 blind review 仍发现五个 P1 groups：

1. source hashes、selectors、JSON pointers、evidence cardinality 与 line binding
   不能对 exact frozen inputs 自洽执行；
2. fact IDs、ordered input arrays 与 `derivation_id` 仍未全部 literal freeze；
3. artifact types、root labels、typed-fact retention 与 clean replay roles
   仍需 verifier 自行选择；
4. fault union、predicate triggers、precedence、actor expectations 与
   zero-semantic-output refusal 仍未闭合；
5. exact 13-field mapping、sticky mismatch records 与 acyclic claim staging
   仍未闭合。

Blind review 为 `P0=0, P1=5, P2=0`。

## 5. Static leakage result 的严格含义

三个 frozen candidates 的 post-freeze static leakage audits 都得到：

```text
P0 = 0
P1 = 0
P2 = 0
verdict = accepted_static_bytes_only
```

这些 audits 没有发现 E0 专属：

- artifact/contract/corpus/attack roots；
- environment keys；
- case/reason IDs；
- module/test paths；
- test outputs 或 failure feedback；
- generated projection bytes、roots 或 140-record enumeration。

与 E0 的 hash overlap 只有四个允许共享的 scientific-source hashes。

这只支持“冻结文件中未发现静态 E0 泄漏”。它不证明 author 实际从未读取其他
path，不证明 model 没有历史记忆，也不使 rejected preregistration 变成
independent implementation。

## 6. Gate accounting

```text
e1_preregistration_attempt_count = 3
e1_preregistration_accepted_count = 0
e1_implementation_file_count = 0
e1_test_file_count = 0
e1_generated_configuration_count = 0
e1_environment_key_count = 0
e1_projection_output_root_count = 0
e0_e1_join_count = 0
formal_v2_source_independent_materializer_pair_count = 0
normative_schema_count = 0
actual_root_count = 0
actual_runtime_execution_count = 0
base_materialization_count = 0
rechain_execution_count = 0
provider_request_count = 0
```

因此：

| Claim | Current result |
| --- | --- |
| E0 internal candidate closure | present |
| Blind E1 preregistration | rejected |
| E1 source implementation | absent |
| E0/E1 exact equality | not run |
| Normative environment schema | open |
| Main/Golden eligibility | false |
| G2/G3 | blocked |
| Provider authorization | false |
| Relative algorithm advantage | no evidence |

## 7. 下一顺序

后续只允许 provider-free normative work：

1. 冻结 actual source-selector identities、byte spans、JSON pointers、evidence
   cardinality 与 line-offset contract；
2. 冻结 literal typed-fact inventory、derivation IDs 与 rooted fact artifact；
3. 冻结 complete artifact types、root formulas、source inventory 与 clean-process
   A/B/verifier roles；
4. 冻结 executable mutation/fault union、predicate triggers、precedence、actor
   expectations 与 zero-semantic-output refusal；
5. 冻结 acyclic 13-field comparison view、sticky mismatch records 与
   non-authorizing downstream claim receipt；
6. 对上述 normative package 做两路 source-distinct contract review；
7. 只有 review 达到 P0=0、P1=0，才重新启动新的 E1 preregistration；
8. E1 两侧冻结后才允许 exact join；mismatch 必须保留，不能反馈给 author 修
   答案；
9. 后续仍需 T7-A1 policy、final C1、Main/Golden、actual chains、G2/G3；
10. G0-G3 全过以前，不读取 API key，不运行 provider canary 或 LLM
    experiment。

## 8. Claim boundary

本审计支持的最强结论是：

> E0 mapping 具有 source-dependent engineering candidate，但当前 normative
> source package 还不能支持一个 blind、逐字节可比较的第二实现；三次失败已经
> 作为 negative result 保留。

它不证明 receptor-gated ligand field 优于 sparse communication、blackboard、
retrieval routing、learned graph pruning 或任何 baseline。H1-H5 仍是可证伪
假设，H6 仍是系统级 claim gate；“最合适方向”仍只能解释为理论动机强的候选
架构。
