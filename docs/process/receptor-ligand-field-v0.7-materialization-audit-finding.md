# Receptor-Gated Ligand Field v0.7 Materialization Audit Finding

状态：NO-GO；public review 已正确 fail closed；G2/G3 继续阻断

检查点日期：2026-07-28

## 1. 决定

当前 `v0.7` design inventory 还不是可唯一复现的 materialization contract。
不得发布 `materialization-review-passed`，不得把 `activation_ready`、
`artifact_bytes_compiled`、`runner_implemented` 或
`receipt_artifact_bytes_present` 改为 `true`，不得迁移 active lock。

本次处置不改变任何 PheroOS ABI、schema、TCK root、Evidence Ledger、
Governance、Optimal Commit、permission、fallback 或 output authority。全部 review
controller 仍为：

```text
authority_scope="none"
commit_authority=false
output_authority=false
publication_authority=false
```

审查没有读取 outcome，没有调用 evaluator/provider，没有使用 credential，也没有使用
网络。

## 2. 可执行反例

两个互不读取对方源码的 disposable materializer 曾分别通过自己的局部测试：

```text
Materializer A: 5/5 PASS
Materializer B: 3/3 PASS
transport supervisor: 5/5 PASS
```

但首次真实源码审计和交叉编译发现：

1. 两边对 base payload 使用不同的自创 outer schema，不可能产生 byte-exact 相同的
   12 个 base artifacts；
2. 两边都曾把 positive fixture 的 `fixture_input` 当成 payload，而不是
   `canonical_post_closure_transaction_product`；
3. 一边给 base completion 写入非空 artifact manifest root，而 review transport
   要求 base 的外层 receipt/manifest 都为 `null`；
4. 另一边读取 review manifest 未声明的 comparative-plan 文件，并把
   `--supervisor-source-root` 的 SHA-256 root 当作本地路径；
5. transport-only fake fixture 使用任意 stable IDs、任意 payload、空
   `profile_defined_root_pairs` 和任意 `E-FAKE` code，内部 comparison 仍可得到
   `comparison_passed=true`。

因此“两个实现相同”不等于“两个实现实现了冻结语义”。局部单测绿色也不等于
materialization gate 通过。

这些实现错误可以修复；更重要的是，它们暴露了规范级 underdetermination。若只修
当前代码而不先关闭规范缺口，任何新 payload 都只是第三种未预注册解释。

## 3. 已关闭的 stop-line

审计中曾出现一个 P0 条件：public supervisor 可以把两个相同但任意的 opaque output
误当作 semantic acceptance。当前隔离 candidate 已在 orchestration 前加入
`blocked-underspecified-v1` guard，public run 必须以 `MR-INPUT-BINDING` 拒绝。

所以当前快照为 P0=0；transport comparison 只能是内部 transport test，不能成为
public gate。该 guard 只能在下文所有关闭条件具备新 identity 后被替换，不能直接切换
为 `complete`。

Clean candidate commit
`5c1d2a92b8a257955aa287df674f6d1a32d1f424` 的最终短 re-audit 为：

```text
P0 = 0
P1 = 3
P2 = 1
P3 = 0
decision = NO-GO, correctly fail-closed
```

三个 P1 分别聚合为：下节七项 normative underdetermination、future supervisor exact
oracle 未实现、R7 closed attack matrix 未实现。P2 是 future pass 所需的更强 source
independence 证明：当前 Git/AST/source-root/non-identical-file audit 足以绑定 refusal，
但未来 acceptance 还必须验证 runtime resolved-module origins，并审查近似复制或共享
semantic helper。A/B 中仍存在的 refusal/process-proof transport schema 只能封存
NO-GO，不是 R3-R5 semantic acceptance schema。

## 4. 仍开放的规范级阻断

### 4.1 `BaseMaterializationV1` 不存在

Materialization plan 把 base payload 写成：

```text
C(canonical_base_object) || LF
```

但 profile、fixture companion 和 materialization plan 没有共同冻结一个 exact
`BaseMaterializationV1`：

- 没有 exact top-level schema literal；
- 没有六类 constructor output 的 exact field set；
- 没有 `stable_id` 与 `base_artifact_id` 的唯一映射；
- 没有 constructor/parameter preimage、normalized view、path inventory、
  construction trace 和 source commitment 的统一 outer object；
- 没有这些 outer fields 的 root labels 和 exclusion rules。

Profile 对 domain records、NDJSON、manifest 和 normalized path families 的局部定义，
不足以唯一推出一个 review payload object。

### 4.2 source-independent equality 与 manifest source binding 冲突

`ArtifactManifestV07` 强制包含 `producer_source_root`，而 materialization plan 又要求
A/B base payload byte-exact、source-independent。当前没有规定 source field 应被
排除、替换为 placeholder，还是移入 source-bound wrapper。实现不能自行选择。

### 4.3 `PositiveTransactionProductV1` 不存在

Materialization plan 把 positive payload 写成：

```text
C(canonical_post_closure_transaction_product) || LF
```

但没有冻结 exact schema、field set、transaction before/after binding、closure trace、
observed receipt binding、root labels 和 exclusion rules。Profile 定义了 literal
fixture input、expected receipts、commitment 和 branch mechanics，却没有定义该
post-closure outer product。

因此把 payload 设为 `fixture_input` 是错误的；任意其他未冻结 wrapper 同样错误。

### 4.4 `raw_ndjson_bytes` 缺少 canonical JSON encoding

Normalized view 暴露 `/raw_ndjson_bytes`，而 profile canonical value domain 不接受
原生 byte string。当前文档没有唯一指定该 field 使用 UTF-8 string、base64 string、
byte array、content-addressed reference，还是 byte sidecar。

这会改变 base bytes、JSON Pointer value、byte operations 和全部下游 roots。

### 4.5 `profile_defined_root_pairs` 没有 exact oracle

Plan 只冻结 locator 语法和“all and only applicable”的自然语言，没有冻结 71 个
record 的 exact locator descriptor set、derived preimage registry，以及 raw negative
payload 是否允许 `payload#` locator。`base_root` 等字段也没有全部 exact preimage
公式。

### 4.6 R3 review records 没有 ABI

R3 要求 normalized-view commitment、exposed path inventory 和 construction trace，
但三者没有 exact schema、field set、serialization、root label 或 bundle layout。

### 4.7 phase identity 没有绑定 materialization contract

`MaterializationReviewInputIdentityV1` 绑定 profile 和 fixture companion，但没有绑定
定义 R3/R4 outer payload 的 normative contract path、byte count、raw root 和 semantic
contract root。后来补写自然语言不能原地改变 V1 含义。

下一版必须使用新的 identity schema/root label，并从 R0 重启。

## 5. Supervisor 在解除 guard 前仍缺少的证明

未来 supervisor 可以做声明式 transport/oracle 检查，但不得实现 task reducer。至少
必须验证：

1. companion 中 exact ordered 12 base IDs、3 positive IDs、56 negative IDs；
2. constructor/recipe mapping 和每个 negative 的 exact expected code；
3. 每项 exact root-locator descriptor set，解析 `companion#`/`payload#`，按声明式
   preimage 重算 `derived#`，并检查 all-and-only；
4. positive/negative receipt、set、artifact、manifest、filename 和 raw bytes；
5. source-bound equality/non-equality 矩阵；
6. completion、verification、attempt、observation、source inventory、process proof
   和 bundle manifest 的 exact keys、labels 和 byte algorithms；
7. runtime resolved-module origins 和 import paths 只位于对应 namespace/stdlib；
8. fresh-process reread时不加载任一 materializer，并重算全部 RAW/H 和 inventories。

当前 transport verifier 只验证 key/hash/count/order 和 A/B equality；不能靠双方一致
替代上述 frozen oracle。

## 6. R7 尚未完成

当前 supervisor 只有少量 transport probes，未覆盖 materialization plan R7 的 closed
attack matrix，包括：

- companion flip/truncate/append/duplicate-key/root mismatch；
- base permutation/duplicate/unknown constructor/wrong order；
- positive/negative recipe missing/duplicate/additional/reordered；
- duplicate operation container/index/parent failures；
- schema、geometry、OOM/crash 和 coverage/sequence precedence forgery；
- operation/recipe/receipt/set/artifact/manifest root tamper；
- shared helper、symlink、generated code、runtime import escape；
- partial write、pre-rename crash、timeout、OOM 和 RSS cases；
- predecessor/lock/phase/core/candidate mutation；
- credential、socket、outcome 和 evaluator access。

每项必须有 closed case ID 和 retained classified refusal receipt；unclassified exception
或缺项均为失败。

## 7. 当前 fail-closed 处置

Public supervisor 必须在 pass manifest 前以 `MR-INPUT-BINDING` 拒绝，并列出：

```text
BaseMaterializationV1 exact contract missing
PositiveTransactionProductV1 exact contract missing
raw_ndjson_bytes encoding missing
content-addressed materialization contract identity missing
```

两个 disposable materializer 也必须在 R2 exact 12/3/56 companion preflight 后、进入
R3 前以 `MR-BASE-MATERIALIZATION` 拒绝。它们不得继续封存旧的自创 71-item output，
且应删除不可达的猜测性 R3-R5 实现。

当前 retained refusal evidence 绑定：

```text
candidate branch = codex/v07-materialization-review
candidate commit = 5c1d2a92b8a257955aa287df674f6d1a32d1f424
phase identity root =
  sha256:cbf5f90dd5c485aea96cd08e43358b83711eb8ea183901dca6df2da4b653f574
A source root =
  sha256:cf7e2b6f9e2634a9d249cb542ee8291fab347d858bdccc5ee550a4585a581460
B source root =
  sha256:a73afd5665233db215f8ddc08f30326be43cb87bb7f4dc294fe5a275f609ab08
supervisor source root =
  sha256:a3112b419b7a5c35338900d2ddae726f3a249ae210f356484c66bc30b9eb241f
refusal code = MR-INPUT-BINDING
refusal manifest root =
  sha256:758fd1e0978da8712a144571ffabd9b1574ba7b7deb1554714fc38b5ac980e22
refusal bundle file count = 9
fresh refusal reread = verified
```

Bundle 以只读形式保存在 protocol-core、active lab 和 candidate worktree 之外的 external
evidence namespace；复制后再次由 fresh process 重算 manifest 和九个 declared files，
结果一致。

该 refusal 是保留的 negative engineering result，不是 arm `R` 的 outcome，也不能
用于比较 `R` 与 `F/P/S/B/Q/G`。

## 8. 关闭顺序

1. 冻结机器可读 `MaterializationContractV2`，明确 base/positive schema、field sets、
   byte encoding、root labels、exclusions 和 `raw_ndjson_bytes` encoding；
2. 两位独立 reviewer 对 contract bytes 做 duplicate-key、canonicalization、
   all-and-only field/root 和 closure review；
3. 创建 `MaterializationReviewInputIdentityV2`，绑定 contract path、byte count、
   raw root 和 semantic contract root；
4. 实现上述声明式 exact supervisor oracle；
5. 把 R7 每个 bullet 展开为 closed case-ID manifest 并实现完整 refusal evidence；
6. 从新的 clean immutable candidate commit 重新独立实现 A/B；
7. 从 R0 重跑 R0-R8，并由 fresh process 独立复读 sealed bundle；
8. 只有 design-review 和 promotion-review 都通过，才可讨论 v0.7 lock migration。

旧 V1 attempt、旧 payload roots 和旧 semantic bodies只能作为 rejected diagnostic
evidence保留，不能迁移为 V2 acceptance evidence。

## 9. 对 G0-G8 和科研结论的影响

```text
G0 = passed
G1 = passed
G2 = blocked
G3 = blocked
G4-G8 = not authorized
full_smoke_authorized = false
hypothesis_conclusions = {}
comparative_superiority_conclusion = null
```

API key 不能关闭本报告中的任一阻断，也不是开始实验的充分条件。在新的 deterministic
contract、G2 和 G3 全部通过前，不得执行 provider canary、pilot 或 confirmatory
LLM run。

本报告进一步加强而不是改变当前科研结论：RG-LF 是理论动机很强、值得检验的候选
架构；现有证据尚未证明它优于 sparse communication、blackboard、retrieval routing、
learned graph pruning 或其他预注册 baseline。
