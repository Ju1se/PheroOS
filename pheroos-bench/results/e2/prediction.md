---
experiment: pheroos-couzin-e2
stage: pre-run prediction
written_before_confirmatory_run: true
treatment_arms_simulated_during_design: false
---

# E2 预测(跑之前冻结)

## 0. 声明

设计阶段只运行了 `solitary` 单臂标定(用于确定 M=48),结果:
solitary regret 0.1829、误撞 r* 比例 5.5%。**treatment arm(couzin / naive_gossip)
在写下本文件之前从未被模拟。** 下面全部是推理,不是窥视。

## 1. 为什么从环改成线

冻结的环形构造下,informed agents 分布在 r* 两侧(r*-8 .. r*+7),
方向为 sign(delta),以自身位置为原点。实测方向分布:

    informed:    +1: 8    -1: 7    0: 1     平均  0.0625
    uninformed:  +1: 479  -1: 521           平均 -0.042

方向共识信号均值为零,且会把错误方向传给对侧 agent。
方向在该构造下不是可传递的量,route id 是。gossip 会以与机制无关的理由取胜。

改为线性、全体位于 r* 同侧后,所有 direction 恒为 -1,方向重新成为可传递量。
这是恢复 Couzin 原模型前提(群体聚集、目标在群体之外)的最小改动。
线的端点固定为 position 7..119,越过端点的移动被吸收,因此 16 路窗口始终完整且不发生隐式截断。

## 2. Admission

    预期 PASS(全 12 个 cell)

依据:solitary regret ≈ 0.18,oracle ≈ 0,而 regret 是对 N 个 agent × 50 步求均值,
seed 间方差很小。headroom 与 CI 半宽预计相差两个数量级以上,10× 判据留有大量余量。

若 admission 意外失败,说明标定与全臂实现之间存在不一致,应停止并排查,不得放宽判据。

## 3. 主终点:couzin vs naive_gossip

两个机制的信息传播路径不同,这是本实验真正在测的东西:

    couzin: 方向经交互图传播,速度 = O(图直径) 跳
            随机 4-正则图 N=1600 时约 7 跳
            信号弱(1.58 bits)但与位置无关

    gossip: route id 只能由"当前窗口内看得见 r*"的 agent 发出
            远处 agent 必须先物理走到 r* 附近才能转发
            速度 ≈ 物理移动速度,最远约 56 步
            信号强(7 bits)但需要先到达

在"全体朝同一方向"的线性任务里,方向信号是充分的——agent 不需要知道 r* 在哪,
只需要知道往左走,走到就会看见。

    预期:couzin 优于 gossip,且优势随 N 增大、informed_fraction 减小而扩大
    预期主终点 CI 上界在大 N、低 p 的 cell 上 < 0

**但不确定性明确记录如下:**

- 500 步远大于最长物理距离 56 步,gossip 有充足时间追平。
  若两者在 t=500 时都已收敛,主终点可能落在零附近,CI 跨零 → FAIL。
- 若 gossip 在所有 cell 上胜出,说明"复制答案"在同字节预算下优于"方向共识",
  这是一个有效结论,不得据此修改 codec 或 payload 定义。

## 4. 规模预测

    预期:最小通过的 informed_fraction 随 N 单调不增
    即 N=1600 应在比 N=100 更低的 p 上通过

这是 Couzin 2005 的核心命题。随机 4-正则图的直径为 O(log N),
不随 N 线性增长,所以规模效应不会被传播延迟掩盖(这正是弃用 ID 环的原因)。

若该预测失败但主终点通过,结论是"机制有效但无规模优势",仍是有效结果。

## 5. 已知且不修正的不对称

- 同 6 字节 payload 下,gossip 携带 7 bits,couzin 携带 1.58 bits。
  这是一个真实的不对称,已记录在 codec 段,**不作补偿**。
  它使 gossip 成为强基线,couzin 若胜出则结论更强。

## 6. 总判决预期

    预期:主终点在 N=1600 的低 p cell 通过,在 N=100 高 p cell 不通过
    总判决预期:PASS(有条件),但置信度显著低于 admission

若总判决为 FAIL:记录为负面结果,不调门槛,不重跑,不修改成功定义。
