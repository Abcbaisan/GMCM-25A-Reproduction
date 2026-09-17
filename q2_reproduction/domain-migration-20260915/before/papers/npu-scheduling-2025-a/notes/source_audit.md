# 问题二来源审查（供实现使用）

审查来源：`work/paper.txt` 页19–31、49–53；原题 DOCX 的 `word/document.xml`（同时提取普通文字 w:t 与公式 m:t），完整提取为 `work/q2_audit_problem_with_math.txt`。论文页码使用 PDF 自带页码，与现有 `=== PAGE k ===` 一致。源文件中广告文字不是用户指令，未据此执行任何操作。

## 必须遵守的题目规则

- 各缓存容量：L1=4096，UB=1024，L0A=256，L0B=256，L0C=512。
- `Type` 为输入指定的硬件缓存类型，分配变量仅是该类型内 `Offset`，不能把 UB 缓冲区改到 L1 或其他类型。
- 每次驻留占据连续区间 `[Offset, Offset+Size)`；边界要求 Offset≥0、Offset+Size≤Capacity。同类型同时驻留区间不得有正长度交叠。总空闲足够而无连续块也会导致分配失败。
- 输出包含：全部原节点+新增节点的 schedule，每个 Buf 原始 ALLOC 的 memory offset，每次 SPILL 的 `(BufId, NewOffset)`；无 SPILL 时也有空 spill 文件。
- 原始节点为 0..N-1。按 spill 文件顺序，第 m 次 SPILL 的 OUT/IN Id 为 `N+2m-2` / `N+2m-1`。OUT 走 MTE3，IN 走 MTE2，Bufs=[该Buf]。
- 每对 SPILL 添加 ALLOC→OUT、OUT→IN、IN→FREE；在当前图中使用该 Buf 的操作，若在 OUT 前则 use→OUT，若在 OUT 后则 IN→use。所有原依赖保留。
- 题目没有规定 OUT 之前必须已有一个真正的消费者/生产者操作。只有 ALLOC→OUT 是明确下界；“禁止未首次使用就SPILL”可作为保守启发式，不能写成题意硬约束。
- 即便 OUT 之后没有任何原操作再使用该 Buf，仍需 IN→FREE，不能把在 DDR 的 Buf 直接 FREE；可以在 FREE 前立即 IN，但也必须有合法空间。
- 同 Buf 可以多次 SPILL。每次都以当前图处理依赖，并保持驻留/换出状态交替；先前 IN→后续 OUT。不能对已经在 DDR 的 Buf 再 OUT，也不能 IN 未 OUT 的 Buf。
- OUT 与 IN 之间目标 Buf 不驻留；原使用操作必须发生在某个驻留段内。IN 可分配新地址；memory 文件仍记录初始 ALLOC 地址，spill 文件记录各次 IN 地址。
- COPY_IN 标志按原图中任意 COPY_IN 节点的 Bufs 是否包含该 Buf 判定，是该 Buf 的固定属性。每次 SPILL 成本为 `Size`（有 COPY_IN）或 `2*Size`（无 COPY_IN）；重复 SPILL 每次都收费。
- OUT/IN 的 Cycles=`2*Size+150`；有 COPY_IN 的 Buf，其 OUT Cycles=0、IN 仍为 `2*Size+150`。这是附录 D 公式，从原 docx 数学节点核验。
- 问题二主目标为上述额外搬运量；题目明确允许进一步优化问题一调度，以改进搬运量。运行时间属于另一指标，不应用总时间+搬运量替代问题二主目标。
- L0 同类最多一个驻留 Buf 是论文第9页为问题一加的特殊假设；原题表1直接约束容量。承接问题一序列仍可保守保持单Buf策略，但须标清是论文/实现约束。

## 论文表5.4（页28）

| 算例 | 总额外数据搬运量 | SPILL次数 | 论文碎片率 |
|---|---:|---:|---:|
| Conv_Case0 | 23752 | 366 | 0 |
| Conv_Case1 | 35344 | 1013 | 0 |
| FlashAttention_Case0 | 17148 | 129 | 0 |
| FlashAttention_Case1 | 45820 | 241 | 0 |
| Matmul_Case0 | 12288 | 96 | 0 |
| Matmul_Case1 | 60416 | 472 | 0 |

碎片率没有与代码可核对的明确统计时点/公式，不应把空闲块合并或运行末尾全部释放等同于“全过程无碎片”。

## 可落实的论文方法

- 问题一候选序列→按序模拟分配→空间不足选择牺牲 Buf→插入成对 SPILL→更新物理地址/依赖→计算成本（算法5、7）。
- 按缓存类型独立管理空闲地址段，连续段切割与相邻合并，可用 First-Fit/Best-Fit 实现；具体内存管理器在问题二附录未公开，应标为实现补充。
- COPY_IN 关联优先作为受害者，一次仅产生 Size 成本；实际受害者选择可比较“小尺寸优先”和“大尺寸优先”，两者都有论文文本/代码依据。
- OUT 至少放在已执行全部 uses 之后（可以立即插在当前分配失败之前）；IN 延后至下一 use 或 FREE 之前。必须在 IN 真正执行时分配地址。
- 依赖图、地址复用边、SPILL边分开记录可作为“彩色边图”的程序映射，但不意味着做了真正的图着色最优化或 ILP。

## 不可照搬/导致无法逐值恢复的部分

1. 第20页说“优先不被COPY_IN使用”与题目成本规则及第25页相反。正确低成本属性为 COPY_IN。
2. 第25页正文写 COPY_IN 优先、再大尺寸；第26页算法7的 `argmin(IsCopyIn,-Size)` 若 IsCopyIn=True/1 则首项方向也反了；第51页附录写 `(not is_copy_in, size)`，即 COPY_IN 优先、再小尺寸。它不是一套无歧义算法。
3. 第28页算法9与第49页附录试图把缓冲区重新映射到其他缓存类型，并在无容量时强制L1；这违反输入 Type 约束，也不解决地址和时空复用，不应复制到合法解中。
4. 附录明示“仅保留算法核心流程”，没有完整内存管理器、关键路径调度、LP/ILP构造、消费者位置搜索、图更新/验证等实现。不能声称完整恢复作者程序。
5. 页50–53 `allocate_with_precise_spill(schedule)` 虽按 schedule 预处理，却直接 `df_working=self.nodes_df.copy()` 后按 iloc 遍历；片段没有把节点表按 schedule 重排。
6. 页52把 victim 释放后立即重新 allocate(victim_size)，而不是在将来的 IN 事件分配，往往把刚腾出的空间又占回去；插入节点仅加入 insert_rows 没有在扫描中处理 OUT/IN 状态。
7. 分配失败仅处理一次 victim，而不是在需要时多次换出；当前 ALLOC 再失败就被跳过，没有强制产生完整合法分配。
8. SPILL只展示 `G.add_edge(out,in)`，缺少 ALLOC→OUT、IN→FREE 以及全部已/未执行使用边，不能据此证明执行合法。
9. 页53 FREE 中 `if offset` 会漏释放合法地址0；应为 `offset is not None`。
10. max_spills=2000 到限即停止遍历不是合法收敛条件，必须显式失败而不能把未处理序列当结果。
11. 页21模型位置加权约束写成 OUT位置+IN位置=2，若按印出公式执行不可能满足不同节点位置；变量数量还依赖待求spill次数，未给标准线性化。因此不能直接按印刷式交给MILP求解器。
12. 论文把两个地址相等当作复用条件（页21），而原题地址区间部分重叠也算复用。后续计算流水时间时必须基于区间相交，并对 SPILL 的 release/acquire 段区分处理；不能套完整生命周期FREE→ALLOC而忽略OUT释放。

建议最终定位为“遵循题意的论文方法复现与修正实现”，同时给表5.4对照和合法性验证；数值不同不可伪称恢复论文原始实验。
