# 中英文术语表

[返回学习入口](index.md)

由 Knowledge Curator 在知识发布时更新。同义词指向同一个规范页；只添加已有页面的相对链接。不要将“已收录”视为“学习者已掌握”。

| 中文术语 | 英文与缩写 | 一句话定义 | 规范知识页 |
| --- | --- | --- | --- |



| 缓冲区生命周期与物理驻留 | npu-buffer-residency-lifetime | 缓冲区仍然存活，不代表它此刻占着核内缓存。 | [缓冲区生命周期与物理驻留](fundamentals/npu-buffer-residency-lifetime.md) |
| 连续分配与外部碎片 | npu-contiguous-allocation-fragmentation | 总空闲容量足够，不保证存在一段足够长的连续地址。 | [连续分配与外部碎片](optimization/npu-contiguous-allocation-fragmentation.md) |
| SPILL加权搬运目标 | npu-spill-weighted-transfer | 优化 SPILL 搬运量需要按缓冲区大小与 COPY_IN 属性计费，不能只数次数。 | [SPILL加权搬运目标](optimization/npu-spill-weighted-transfer.md) |
| 最大空闲段 | largest free block | 没有额外对齐约束时，判断连续请求能否放置的关键长度；不同于总空闲量。 | [连续分配与外部碎片](optimization/npu-contiguous-allocation-fragmentation.md) |
| 物理驻留 | residency | 缓冲区当前实际占用核内缓存；逻辑存活不保证当前驻留。 | [缓冲区生命周期与物理驻留](fundamentals/npu-buffer-residency-lifetime.md) |
