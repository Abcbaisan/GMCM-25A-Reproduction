# 缓冲区生命周期与物理驻留（Lifetime and Residency）

<!-- knowledge-meta:start -->
```json
{
  "card_id": "625b38d2-8c30-4cd7-9b54-6ccb2901b9b3",
  "concept_id": "npu-buffer-residency-lifetime",
  "target_concept_id": "",
  "title": "缓冲区生命周期与物理驻留（Lifetime and Residency）",
  "aliases": [
    "缓冲区生命周期与物理驻留"
  ],
  "category": "fundamentals",
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
  "origin_outbox": "papers/npu-scheduling-2025-a/knowledge_outbox/20260914-npu-buffer-residency-lifetime-e6e0fe98-641f-41e2-9aa8-4efe12fe5d26.md",
  "delivery_status": "delivered",
  "delivered_to": "",
  "supersedes_card_id": "",
  "difficulty": "beginner",
  "created_at": "2026-09-14",
  "updated_at": "2026-09-15",
  "reviewed_by": "Codex Knowledge Curator",
  "reviewed_at": "2026-09-14",
  "prerequisites": [],
  "related": [
    "npu-contiguous-allocation-fragmentation",
    "npu-spill-weighted-transfer"
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
缓冲区仍然存活，不代表它此刻占着核内缓存。判断地址能否复用，要看物理驻留状态。

## 学习前提
先理解按节点顺序执行、ALLOC 申请和 FREE 释放。本章只使用 2025 年研究生数学建模竞赛 A 题问题二及本项目实现的规则。逻辑存活表示这份数据尚未结束生命周期；物理驻留表示它当前实际占用指定类型的核内缓存。

## 直觉
可以把核内缓存想成一张容量有限的工作台。暂时把材料移到别处，会腾出桌面，但不会让这项工作自动完成。这个比喻只说明两种状态的区别；具体何时能换出、换入和释放，仍由本题依赖约束决定。

## 定义与状态变化
对缓冲区 $b$，令 $A_b(t)$ 表示事件 $t$ 执行后的逻辑存活状态，$R_b(t)$ 表示物理驻留状态，取值均为 0 或 1。任意合法状态满足

$$R_b(t)\le A_b(t).$$

驻留一定意味着存活，但存活可能处于等待换回状态。下面按单个缓冲区说明转移：

| 执行事件 | 事件前状态 | 事件后状态 | 对物理空间的作用 |
| --- | --- | --- | --- |
| ALLOC | 尚未存活 | 存活且驻留 | 获得一段连续地址 |
| OUT | 存活且驻留 | 存活但不驻留 | 释放当前占用区间 |
| IN | 存活但不驻留 | 存活且驻留 | 重新取得合法区间 |
| FREE | 存活且驻留 | 生命周期结束 | 释放当前占用区间 |

这里把状态定义在事件之后，避免区间端点的歧义。本题每对 SPILL 有 ALLOC→OUT、OUT→IN、IN→FREE 依赖；使用操作必须在驻留状态发生。实现中的 active、resident、pending 分别跟踪逻辑存活、当前驻留和待换回状态。

## 最小例子
教学手推事件序列：ALLOC A → USE A → OUT A → IN A → USE A → FREE A。

1. ALLOC 后，A 存活且驻留，第一次 USE 合法。
2. OUT 后，A 仍然存活，但原地址不再由 A 占用，可在满足其余依赖和地址约束时复用。
3. IN 执行时必须重新找到足够的连续空间，地址可以与原来不同。只在计划中写下 IN，并不会提前获得物理空间。
4. 第二次 USE 之后执行 FREE，A 的逻辑生命和本次驻留一起结束。

若把第二次 USE 放在 OUT 与 IN 之间，错误出在“不驻留却使用”；若删除 IN 直接 FREE，错误出在违反本题 IN→FREE 依赖。二者不是同一个问题。

## 领域应用
排查调度器时，可在每个事件后分别检查存活集合和驻留集合。地址冲突检查只比较同一缓存类型中当前驻留的缓冲区，不能让所有逻辑存活对象始终占着初始地址。

一个实用的诊断顺序是：先检查该事件是否允许发生，再更新状态，最后检查地址占用。若先删除对象再做合法性检查，可能把非法释放的证据一并抹掉。

## 误区与边界
OUT 不是 FREE，IN 也不是重新开始一个逻辑生命周期。同一个缓冲区可多次换出，但每次都要遵循驻留与非驻留交替，不能连续 OUT 两次。

“没有后续 USE 就可以直接 FREE”在本题不成立，因为仍存在 IN→FREE 依赖。这是题目形式约束，不能推广为所有操作系统都必须把数据换回后才能释放。

## 自测与解析
1. A 已 OUT，B 想用 A 的旧地址，是否一定合法？不一定。A 已释放该地址是一个条件，还要检查 B 的类型、连续空间以及原依赖和地址复用依赖。
2. IN 的新地址不同于 ALLOC 地址，是否开始第二个生命周期？没有。逻辑存活从原 ALLOC 延续到 FREE，变化的是物理驻留位置。
3. 某程序只维护 active 集合，能否直接据此计算核内占用？不能。被 OUT 的对象仍在 active 中；需要另行跟踪 resident。

## 关联知识
- [连续分配与外部碎片](../optimization/npu-contiguous-allocation-fragmentation.md)：已释放的总空间不一定构成连续空间。
- [SPILL 加权搬运目标](../optimization/npu-spill-weighted-transfer.md)：每次换出换入还有成本。

## 来源与证据
规则定位：[项目来源审查](../../papers/npu-scheduling-2025-a/notes/source_audit.md) 中“必须遵守的题目规则”，对应原题数学节点提取和论文页 19–31、49–53。历史实现验证定位：[实验配置](../../papers/npu-scheduling-2025-a/reproduction/config-v2.json)与[历史测试日志](../../papers/npu-scheduling-2025-a/reproduction/tests.log)，测试名 test_nonresident_use_and_free_rejection、test_repeated_spills_and_crossing_rejection。

本章状态表、事件追踪和自测是对已核验规则的教学展开；本次没有重新运行 NPU 实验。历史运行记录与配置见上方链接。

## 审核与变更记录
原页于 2026-09-14 由 Codex Knowledge Curator 发布；原审核证据与候选合并记录保留在 docs/curation_log.md 及源候选。

2026-09-15 教材扩写：保留概念与来源，补充状态或计算步骤、边界反例和自测解析；图为原创教学示意，非实验结果。数值分析来源重新打开核对；工程知识对照既有 source_audit.md、[实验配置](../../papers/npu-scheduling-2025-a/reproduction/config-v2.json)与[历史测试日志](../../papers/npu-scheduling-2025-a/reproduction/tests.log)。未重跑 NPU 实验，候选记录不变。
