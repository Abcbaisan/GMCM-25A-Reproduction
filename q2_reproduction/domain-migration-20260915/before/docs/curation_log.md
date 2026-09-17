# 知识整理日志

## 2026-09-15 教材扩写与领域 Word 阅读版

角色：系统维护与 Knowledge Curator；领域：machine_learning、mathematical_modeling、numericalanalysis；本次不创建研究项目。已运行 --find 查询规范概念与未处理候选，并对照既有合并记录。保留全部候选状态及五个规范 card_id，不重新合并、不发布六张未审核的建模方法卡。

| 规范 card_id | concept_id 与目标 | 教学增量与理由 | 证据核查 |
| --- | --- | --- | --- |
| 625b38d2-8c30-4cd7-9b54-6ccb2901b9b3 | handbook/fundamentals/npu-buffer-residency-lifetime.md | 明确事件后状态，增加转移表、事件追踪与非法序列辨析 | source_audit.md 的 OUT/IN 规则；config-v2.json 与 tests.log 的既有运行记录 |
| ef7fdbda-9e9f-435e-ac59-a670a208f515 | handbook/optimization/npu-contiguous-allocation-fragmentation.md | 展开最大洞判据、First Fit 与 Best Fit 的例子，增加原创地址图 | 同项目来源审查及 test_fragmentation_repack_is_real_and_paid 历史记录；容量10图为教学手推 |
| c19cadb3-1365-4628-8ad1-eec5eb8fd939 | handbook/optimization/npu-spill-weighted-transfer.md | 增加逐项计费表、重复换出反例和自测解析 | 同项目静态 COPY_IN 属性与成本规则；test_copy_in_cost_and_reuse_barriers 历史记录 |
| 85029d26-4377-42e9-9c72-61882a1ffb58 | domains/numericalanalysis/handbook/fundamentals/absolute-relative-error.md | 增加分母正下界推导、误差区间图、零点边界与严格界差值 | 重新打开 Cornell CS4220 2026-01-30 的 Absolute and relative error 与李晓鹏课程第1章；新增例子为显式手算 |
| 2ab59910-db1c-4c7b-8ffc-9dbc7f392136 | domains/numericalanalysis/handbook/fundamentals/significant-digits-error-criterion.md | 展开科学计数法代入、充分必要条件证明、进位边界和误差限不足反例 | 李晓鹏第1章幻灯片51、55，物理页57、63；按原页半单位约定逐式复核 |

不更改知识类型与概念等价关系，回链仍指向原规范页；术语表补充最大空闲段与物理驻留的区分。未重跑 NPU 实验，不把历史日志写成此次测量。规范页 updated_at 更新为本次日期；原审核日期保留。

系统变化：新增 handbook_authoring 工作流与 export_handbook.py；按配置读取领域、过滤 published、按前置关系排序，将 LaTeX 数学节点转成 Word 原生公式并嵌入本地 PNG/JPEG。源元数据与审计段不进入阅读正文。运行13项回归检查通过；原系统测试改为隔离的空知识夹具，并忽略编辑器锁定的 .vs 文件与输出目录。

渲染说明：documents 默认渲染器因本机缺少 soffice.exe 未成功；改用 Microsoft Word 只读导出 PDF，再复用技能 render_docx.py 的 PNG 栅格化流程。最终逐页结果记入 exports/handbooks/manifest.json；其未核查标记不可当作已通过。

每次整理追加一行；不要删除旧决策。尚无实际整理记录。

| 日期 | 卡片 ID | 规范概念 ID | 操作与目标路径 | 来源核验与决策理由 | 变化摘要/未决问题 |
| --- | --- | --- | --- | --- | --- |


## 2026-09-14 · npu-scheduling-2025-a

角色依次为 Research、Capture、单一 Curator，无并发写入。已检索 SPILL、fragmentation、缓存、复现、验证、resident，无命中；比较空全局索引与候选队列后新建3概念。未新建分类，复用fundamentals/optimization。三个outbox/inbox同UUID配对，canonical另有独立UUID；只在规范页成功写入后标记候选merged。

| 候选卡 | 概念 | 目标 | 核验与处理 |
| --- | --- | --- | --- |
| e6e0fe98-641f-41e2-9aa8-4efe12fe5d26 | npu-buffer-residency-lifetime | handbook/fundamentals/npu-buffer-residency-lifetime.md | 合并；核验题目审查与已通过回归测试；限定2025A题环境 |
| b65b05d3-beb5-46b8-a3fc-3a7cffa3c070 | npu-contiguous-allocation-fragmentation | handbook/optimization/npu-contiguous-allocation-fragmentation.md | 合并；核验题目审查与已通过回归测试；限定2025A题环境 |
| a4c25b1d-5a6d-487e-bde3-424843eef70b | npu-spill-weighted-transfer | handbook/optimization/npu-spill-weighted-transfer.md | 合并；核验题目审查与已通过回归测试；限定2025A题环境 |

- 57bcdc4b-af18-4b1f-b333-5ce9aa47e6a8 / npu-q2-local-reproduction-20260914：research_finding，reviewed，不进入规范手册。证据核查：finding/F2-001.md，数值与正式结果对应，缺完整作者程序不能解释全部差距。

- 991ae0c9-fe69-48ff-8e76-765fa65d0cea / npu-q2-paper-numeric-gap：open_question，needs_review，不进入规范手册。证据核查：notes/source_audit.md，数值与正式结果对应，缺完整作者程序不能解释全部差距。

## 2026-09-14 · 今日 Inbox 全量复核

role=Knowledge Curator；domain_id=numericalanalysis、machine_learning、mathematical_modeling；project_id=study_20260914_error_digits、npu-scheduling-2025-a。单一 Curator 写入。
按 domain.yaml 路径扫描：今日7张接收卡，数学建模无新增卡。先运行 --find error、有效、npu，再对照全局3条规范记录、全部候选正文与旧整理日志。数值分析两卡是前置/应用关系，和NPU三概念无语义重复。复用 fundamentals，不扩展分类。

| 卡片 ID | 规范概念 ID | 操作与目标路径 | 来源核验与决策理由 | 变化摘要/未决问题 |
| --- | --- | --- | --- | --- |
| 1467f74f-0068-4d6f-8afe-0d05fea6f612 | significant-digits-error-criterion | 合并至 domains/numericalanalysis/handbook/fundamentals/significant-digits-error-criterion.md | 核对李晓鹏第1章幻灯片48–49、51、55（PDF物理页53–54、57、63）；误差定义另核对Cornell Absolute and relative error；手工复核推导和例题 | 新规范UUID；源卡reviewed/merged；补前置与回链、术语；未提供课堂教材，按明示约定发布 |
| 9c75f391-d023-402e-af56-84bc7db73373 | absolute-relative-error | 合并至 domains/numericalanalysis/handbook/fundamentals/absolute-relative-error.md | 核对李晓鹏第1章幻灯片48–49、51、55（PDF物理页53–54、57、63）；误差定义另核对Cornell Absolute and relative error；手工复核推导和例题 | 新规范UUID；源卡reviewed/merged；补前置与回链、术语；未提供课堂教材，按明示约定发布 |
| 57bcdc4b-af18-4b1f-b333-5ce9aa47e6a8 | npu-q2-local-reproduction-20260914 | 保留 reviewed / pending，留在Inbox | 复读finding/F2-001.md、evidence/EV2-20260914.md、comparison.json与optimized/validation.json；六实例搬运量及对数一致 | 局部结果不升级为教材；作者完整程序和输出仍缺，差异原因未解决 |
| 991ae0c9-fe69-48ff-8e76-765fa65d0cea | npu-q2-paper-numeric-gap | 保留 needs_review / pending，留在Inbox | 复读finding/F2-001.md、evidence/EV2-20260914.md、comparison.json与optimized/validation.json；六实例搬运量及对数一致 | 局部结果不升级为教材；作者完整程序和输出仍缺，差异原因未解决 |
| a4c25b1d-5a6d-487e-bde3-424843eef70b | npu-spill-weighted-transfer | 已有合并，不重复发布；handbook/optimization/npu-spill-weighted-transfer.md | 对照旧日志、源卡和规范页一致；复读source_audit.md、config-v2.json与tests.log，未重跑实验 | 补target_concept_id及规范页互链；保留engineering_insight |
| b65b05d3-beb5-46b8-a3fc-3a7cffa3c070 | npu-contiguous-allocation-fragmentation | 已有合并，不重复发布；handbook/optimization/npu-contiguous-allocation-fragmentation.md | 对照旧日志、源卡和规范页一致；复读source_audit.md、config-v2.json与tests.log，未重跑实验 | 补target_concept_id及规范页互链；保留engineering_insight |
| e6e0fe98-641f-41e2-9aa8-4efe12fe5d26 | npu-buffer-residency-lifetime | 已有合并，不重复发布；handbook/fundamentals/npu-buffer-residency-lifetime.md | 对照旧日志、源卡和规范页一致；复读source_audit.md、config-v2.json与tests.log，未重跑实验 | 补target_concept_id及规范页互链；保留engineering_insight |

数值来源核验为公开网页/PDF文本；截图接口部分失败，未将失败截图当作核验依据。NPU核验为既有本地证据复核，不声称本轮重新运行实验或重新审核论文原件。全部历史候选及outbox保留。

验证结果：build_handbook.py 成功（更新2个生成文件），随后 --check 通过 domains、metadata、references、links、indexes 检查。另核对全局5个唯一规范概念、7张接收卡中5张reviewed/merged，所有合并目标与索引一致；另1张reviewed研究结果、1张needs_review问题保留。结构检查不替代上述语义与证据审核。

2026-09-15 Word 最终验收：机器学习8页、数学建模8页、数值分析7页已逐页查看；公式、图片、中文、表格与页码可读，无截断或重叠。源页及图片哈希与最终导出一致，文件哈希记录于 manifest.json。
