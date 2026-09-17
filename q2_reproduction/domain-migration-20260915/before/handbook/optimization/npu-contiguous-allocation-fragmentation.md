# 连续分配与外部碎片（Contiguous Allocation）

<!-- knowledge-meta:start -->
```json
{
  "card_id": "ef7fdbda-9e9f-435e-ac59-a670a208f515",
  "concept_id": "npu-contiguous-allocation-fragmentation",
  "target_concept_id": "",
  "title": "连续分配与外部碎片（Contiguous Allocation）",
  "aliases": [
    "连续分配与外部碎片"
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
  "origin_outbox": "papers/npu-scheduling-2025-a/knowledge_outbox/20260914-npu-contiguous-allocation-fragmentation-b65b05d3-beb5-46b8-a3fc-3a7cffa3c070.md",
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
总空闲容量足够，不保证存在一段足够长的连续地址。分配失败时要同时看总量与最大空闲段。

## 学习前提
先学缓冲区驻留状态与半开区间。本章假定缓存类型固定、每个缓冲区占据一段连续地址，区间长度与容量采用同一题目单位；不另加题目未规定的对齐限制。

## 直觉
两排隔开的空座位不能直接当作一排连续座位。选择“第一个空位”或“最合适的空位”都不能跨过中间仍占用的位置。

## 定义与判断步骤
缓存容量为 $C$，大小为 $s>0$ 的请求放在起始地址 $a$，占据半开区间 $[a,a+s)$。可行性要求

$$0\le a,\qquad a+s\le C.$$

还必须与同类型当前驻留区间无正长度交叠。若完整空闲段长度依次为 $h_1,\ldots,h_k$，没有额外对齐要求时，存在合法连续位置等价于

$$\max_i h_i\ge s.$$

空闲段为空时，没有正大小请求可放置。总空闲量 $F=\sum_i h_i$ 满足 $F\ge s$ 只是必要条件，因为总和没有表达空闲空间的位置。First Fit 按地址选择首个可用洞，Best Fit 选择可容纳请求的最小洞；两者先决条件都是至少有一个洞足够长。

## 最小例子
容量为 10，B 驻留在 $[4,7)$，请求 A 的大小为 5。以下是教学手算，数字不代表实验配置。

![总空闲为 7 但最大连续空闲只有 4](assets/fragmentation.png)

图为本系统原创教学示意。横轴表示地址区间；浅色为空闲，深色为 B。

1. 左洞 $[0,4)$ 长度为 4，右洞 $[7,10)$ 长度为 3。
2. 总空闲 $F=4+3=7$，看起来超过请求的 5。
3. 最大洞长度为 4，小于 5，所以 First Fit 与 Best Fit 均无法分配。
4. 若按合法事件释放 B，三个相邻区间才能合并为 $[0,10)$，此时可以分配 A。

进一步把 A 的大小改成 3，两个洞都可放置。First Fit 会选左洞；Best Fit 会选恰好大小为 3 的右洞。这说明策略只在可行位置之间选择，不能凭策略名称消除不可行性。

## 领域应用
遇到分配失败时，先记录缓存类型、请求大小、空闲段列表和最大段长度。仅打印“剩余容量”无法区分容量不足与外部碎片。

本项目通过真实 OUT/IN 重装缓冲区处理部分碎片情况。教学上应把“合并相邻空洞”与“搬动驻留数据”区分开：前者更新空闲区间表示，后者改变数据位置，需要合法事件并支付搬运成本。

## 误区与边界
释放后合并相邻空洞不能越过仍驻留的 B。把 B 的地址字段直接改掉也不是免费整理，因为数据移动和依赖变化没有得到执行。

本实现使用保守启发式，不保证最小成本。运行末尾所有缓冲区都释放，只说明末态空闲，不能证明整个执行过程没有碎片。若实际硬件另有对齐、保留区或不可移动对象等限制，本章最大洞判据须增加相应条件。

## 自测与解析
1. 空闲段长度为 2、2、2，请求为 3，能否分配？不能。总量 6 足够，但最大洞只有 2。
2. 在本章图中，大小为 4 的请求能否分配？能，左洞恰好满足；占据 $[0,4)$ 与 B 的 $[4,7)$ 只共享端点，没有正长度交叠。
3. 释放 B 后是不是一定“零成本”？若是合法 FREE，该事件释放空间；若还要保存 B 并通过 SPILL 腾出空间，就需要按规则换出换入和计费，不能混淆。

## 关联知识
- [缓冲区生命周期与物理驻留](../fundamentals/npu-buffer-residency-lifetime.md)：决定哪些区间当前占用。
- [SPILL 加权搬运目标](npu-spill-weighted-transfer.md)：比较整理空间带来的代价。

## 来源与证据
规则定位：[项目来源审查](../../papers/npu-scheduling-2025-a/notes/source_audit.md) 的连续区间、容量和 OUT/IN 规则。历史回归 test_fragmentation_repack_is_real_and_paid 使用 UB=1024，结果见 [实验配置](../../papers/npu-scheduling-2025-a/reproduction/config-v2.json)与[历史测试日志](../../papers/npu-scheduling-2025-a/reproduction/tests.log)。

本章容量 10 的示例、最大洞判断及示意图是教学手推，不是硬件实测，也不采用论文中缺少明确统计口径的“碎片率”作为结论。

## 审核与变更记录
原页于 2026-09-14 由 Codex Knowledge Curator 发布；原审核证据与候选合并记录保留在 docs/curation_log.md 及源候选。

2026-09-15 教材扩写：保留概念与来源，补充状态或计算步骤、边界反例和自测解析；图为原创教学示意，非实验结果。数值分析来源重新打开核对；工程知识对照既有 source_audit.md、[实验配置](../../papers/npu-scheduling-2025-a/reproduction/config-v2.json)与[历史测试日志](../../papers/npu-scheduling-2025-a/reproduction/tests.log)。未重跑 NPU 实验，候选记录不变。
