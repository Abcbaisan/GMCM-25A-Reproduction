# SPILL加权搬运目标（Weighted Transfer Cost）

<!-- knowledge-meta:start -->
```json
{
  "card_id": "c19cadb3-1365-4628-8ad1-eec5eb8fd939",
  "concept_id": "npu-spill-weighted-transfer",
  "target_concept_id": "",
  "title": "SPILL加权搬运目标（Weighted Transfer Cost）",
  "aliases": [
    "SPILL加权搬运目标"
  ],
  "category": "optimization",
  "status": "published",
  "disposition": "pending",
  "merged_into": "",
  "project_id": "npu-scheduling-2025-a",
  "domains": [
    "machine_learning",
    "mathematical_modeling"
  ],
  "knowledge_type": "engineering_insight",
  "source_project": "papers/npu-scheduling-2025-a",
  "origin_outbox": "papers/npu-scheduling-2025-a/knowledge_outbox/20260914-npu-spill-weighted-transfer-a4c25b1d-5a6d-487e-bde3-424843eef70b.md",
  "delivery_status": "delivered",
  "delivered_to": "",
  "supersedes_card_id": "",
  "difficulty": "beginner",
  "created_at": "2026-09-14",
  "updated_at": "2026-09-15",
  "reviewed_by": "Codex Knowledge Curator",
  "reviewed_at": "2026-09-14",
  "prerequisites": [
    "npu-buffer-residency-lifetime"
  ],
  "related": [
    "npu-buffer-residency-lifetime",
    "npu-contiguous-allocation-fragmentation"
  ],
  "sources": [
    {
      "type": "experiment",
      "reference": "papers/npu-scheduling-2025-a/reproduction/config-v2.json",
      "locator": "E2-20260914-v2; reproduction/tests.log; code/test_q2.py"
    },
    {
      "type": "project",
      "reference": "papers/npu-scheduling-2025-a/notes/source_audit.md",
      "locator": "原题DOCX与论文页19—28、49—53核对；原件SHA256见config.json"
    }
  ],
  "open_questions": []
}
```
<!-- knowledge-meta:end -->

## 一句话理解
SPILL 要按每次搬运涉及的缓冲区大小与 COPY_IN 属性计费，单纯减少次数不一定减少目标成本。

## 学习前提
先理解一次 SPILL 是成对的 OUT/IN，而非一个孤立节点。这里的计费口径来自 2025 年 A 题问题二；Size 使用题目给定单位。

## 直觉
搬运次数相同，搬一个大箱子和一个小箱子的工作量不同；次数较多的小箱子也可能更便宜。但本题不是按直观搬运距离或时间估价，而是使用明确的目标公式。

## 定义与公式
令 $k$ 遍历每一次 SPILL 对，$s_k$ 为对应缓冲区 Size。若原图任意 COPY_IN 节点的 Bufs 含该缓冲区，令 $c_k=1$，否则 $c_k=0$。总额外搬运量为

$$D=\sum_k(2-c_k)s_k.$$

先代入属性，再乘大小，最后对所有事件求和：有 COPY_IN 属性时系数为 1，无该属性时系数为 2。同一缓冲区换出三次，就在求和中出现三项；不能先按 BufId 去重。

## 最小例子
下面仅比较成本，假定两个候选调度均已通过依赖与地址合法性检查。

| 候选方案 | Size | COPY_IN 属性 | SPILL 对数 | 每对成本 | 总成本 |
| --- | --- | --- | --- | --- | --- |
| A | 100 | 有 | 3 | 100 | 300 |
| B | 200 | 无 | 1 | 400 | 400 |

教学手算：A 的每对成本为 $(2-1)\times100=100$，重复三次得到 300；B 为 $(2-0)\times200=400$。只比较次数会偏好 B，按问题二主目标则 A 更好。

再看相同属性下的比较：一个 Size=300 的 COPY_IN 缓冲区换出一次，成本 300；Size=100 的同属性缓冲区换出两次，成本 200。因此“优先少换出”和“优先某个属性”都不足以单独确定全局最优解，还需考虑大小与后续事件。

## 领域应用
先验证输出合法，再从正式输出逐对重算成本。独立验证器不应读取求解器自行报告的总分作为证据，否则两者可能共享同一个漏计错误。

诊断成本差异时，可逐行列出 BufId、Size、静态 COPY_IN 属性、单次成本和累计成本。重复换出必须逐次保留。在本项目中，相同 $D$ 时才进一步比较 SPILL 对数。

## 误区与边界
目标 $D$ 与 Cycles 是不同指标，不能把该式直接当作程序完成时间或任意硬件的真实流量。COPY_IN 属性按原图静态判断，不随本次换入来源的猜测改变。

一个低成本但非法的调度不能参与“更优”比较。只把 OUT 写入输出而没有配对 IN，会同时破坏合法性与计费依据。

## 自测与解析
1. 无 COPY_IN 的 Size=80 缓冲区换出两次，成本是多少？每次 160，两次 320。
2. 同一个 COPY_IN 缓冲区第一次换出计费后，第二次可以免费吗？不能。求和对象是每次 SPILL 对，重复事件重复收费。
3. 两个合法方案都为 $D=300$，能否从本式判断哪个运行更快？不能。需要时间模型或另行测量；本式没有包含完整执行时间。

## 关联知识
- [缓冲区生命周期与物理驻留](../fundamentals/npu-buffer-residency-lifetime.md)：检查 OUT/IN 配对与状态。
- [连续分配与外部碎片](npu-contiguous-allocation-fragmentation.md)：腾出容量仍需满足连续地址条件。

## 来源与证据
计费规则定位：[项目来源审查](../../papers/npu-scheduling-2025-a/notes/source_audit.md) 中 COPY_IN 固定属性、每次 SPILL 成本及问题二主目标。历史测试 test_copy_in_cost_and_reuse_barriers 的配置和结果见 [实验配置](../../papers/npu-scheduling-2025-a/reproduction/config-v2.json)与[历史测试日志](../../papers/npu-scheduling-2025-a/reproduction/tests.log)。

本章表格、追加的同属性比较和自测为自拟手算，未声称是六算例结果。本次只复核既有证据与算术，没有重新运行 NPU 实验。

## 审核与变更记录
原页于 2026-09-14 由 Codex Knowledge Curator 发布；原审核证据与候选合并记录保留在 docs/curation_log.md 及源候选。

2026-09-15 教材扩写：保留概念与来源，补充状态或计算步骤、边界反例和自测解析；图为原创教学示意，非实验结果。数值分析来源重新打开核对；工程知识对照既有 source_audit.md、[实验配置](../../papers/npu-scheduling-2025-a/reproduction/config-v2.json)与[历史测试日志](../../papers/npu-scheduling-2025-a/reproduction/tests.log)。未重跑 NPU 实验，候选记录不变。
