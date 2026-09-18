# 问题三：流水调度与受限优化（独立尝试）

本目录是**本地补充算法**，不是优秀论文作者源码或全局最优性证明。基于仓库问题二的正式三文件，以同一指标口径计算总执行周期及额外数据搬运量，尝试改进时间且严格控制搬运增长。

## 输入和基线

- 官方附件 ZIP：仓库根目录 `通用神经网络处理器下的核内调度问题附件.zip`（每个案例含 Nodes / Edges）。
- 问题二默认基线：`q2_reproduction/runs/q2-20260914/optimized/` 下的 `*_schedule.txt`、`*_memory.txt`、`*_spill.txt`；另参考 `q2_reproduction/results/`。
- 对每个基线/候选，必须先通过 `verify_q2.verify_case()`。不采用任何未验证或超出搬运预算的候选。
- 默认搬运预算：`D_candidate <= 1.05 * D_baseline`。**5% 是本项目明确设定的实验容忍阈值，并不是题目指定的数值**；可用 `--tolerance-pct` 调整。基线 D=0 时只能接受 D=0。

## 时间模型

根据题目附录 B/C/D 的抽象执行规则构建前驱集合：保留原始 Edges；为每一对 SPILL 加入 ALLOC→OUT→IN→FREE、OUT 前各次使用→OUT、IN→后续使用和连续多次 SPILL 的衔接；按每个缓存地址的实际复用增加上次 OUT/FREE→本次 ALLOC/IN 的边。不同 Pipe 可并行，每个 Pipe 内按最终 schedule 先进先出，不考虑额外未给出的硬件微架构开销。ALLOC/FREE 为零周期。SPILL_OUT 使用 MTE3、SPILL_IN 使用 MTE2；COPY_IN 类型缓冲区的 OUT 周期为 0，其他 OUT 和所有 IN 按 `2*Size+150`。该公式与仓库问题二 events 的周期记录一致。

对序列中每个节点计算：

```text
start(v) = max(所有前驱 end(u), 当前 Pipe 上一个节点的 end)
end(v)   = start(v) + Cycles(v)
总时间   = max(end(v))
```

这是**基于题目抽象的估算器**，不是硬件实测，也未验证与优秀论文所有数值一致；后续应结合题面附录 C 的完整图示进一步核对。

## 优化办法

1. 保留问题二已验证的优化结果作为不能劣化的基线，额外试用问题二 `results/` 历史方案。
2. 从基线抽取原始拓扑序，重新尝试 `farthest` / `cost-distance`、Best-Fit / First-Fit 内存分配。
3. 用原始 DAG 的反向最长路径构造关键路径优先与 FREE 优先两个候选拓扑序，并重新执行问题二分配。
4. 对目前最好方案，尝试相邻、同 Pipe、不同缓冲区、无直接依赖的两个普通操作交换；每次评估完整流水时间，只有更快才保留。
5. 用验证器复核最终三文件；在搬运预算内按 (总周期、搬运量、SPILL 对数) 选择。不改善时原样保留基线，绝不宣称一定提升。

## 运行方法

在仓库根目录运行：

```bash
python -m unittest discover -s q3_reproduction -p 'test_q3.py' -v
python q3_reproduction/q3.py --case all --tolerance-pct 5 --max-swaps 64 --swap-passes 2
python q2_reproduction/verify_q2.py --zip '通用神经网络处理器下的核内调度问题附件.zip' --results q3_reproduction/results
```

Windows CMD 中 `--zip` 路径也应按实际文件路径传入；脚本默认使用仓库根目录的官方 ZIP。若希望快速复核单例，加 `--case Matmul_Case0`。输出目录可用 `--out` 指定。

## 输出与结果可信度

`results/` 中每案例写出官方三文件 `*_schedule.txt`、`*_memory.txt`、`*_spill.txt`，另写 `report.json`，记录每个算例的基线/选中周期、搬运量、候选成败及独立验证状态。**仅实际执行脚本后产生的 report 和正式三文件才能称为六案例实验结果。** `examples/` 是单独标注的人工小算例，不作为官方结果。

`q3.py` 的执行结束码为非零时表示至少一个案例失败；即使部分结果文件存在，也不得将整批结果称为验证通过。GitHub Actions 工作流尝试自动执行并提交结果；仓库可能因 Actions 权限或运行限制而不自动产出，请以实际提交和 `results/report.json` 为准。
