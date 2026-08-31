# RAG V3（v6 之前）设计文档归档

## 归档状态

本目录中的文件是《2026 年 9 月 双项目升级执行协议 v6》定稿前形成的历史设计材料，**不再是九月开发的执行依据，也不得据此直接实现功能**。

唯一上位执行协议位于仓库外：

`D:\AI_Internship_2026\求职材料\2026-09_双项目升级计划_评审版.md`

仓库内对该协议的 RAG 映射见 `docs/r_protocol.md`，实际阶段状态见 `docs/DEV_STATE.md`。如历史文档、旧聊天或旧计划与 v6 冲突，以 v6 和 `docs/r_protocol.md` 为准。

## 为什么整体归档

这 10 份文件共同描述了一套旧 V3 P0：它同时包含异步摄取、较完整的 Agent 工作流、Investigation API、审批/版本化草稿、Agent 评测和更复杂的可靠性机制。v6 已将九月范围重新拆成 R1、R23、R4 和条件启动的 R5，并明确：

- R5 只设计受限 Agentic Retrieval 对照实验协议，不实现 Agent；
- Agent 不进入生产 `app/` 和生产 API；
- 审批、草稿版本、Lease/Fencing、多 Worker 等不属于九月主线；
- R23 只实现单机、单 Worker 的最小完整异步闭环。

旧文件内部相互引用。若只把其中一部分留在活动文档区，会形成看似可执行、实际混合新旧边界的协议，因此按 v6 的“默认归档”原则整体保留为历史资料。

## 文件分诊表

| 文件 | R0 处理 | 主要原因 |
| --- | --- | --- |
| `v3_september_upgrade_spec.md` | 归档 | 把完整 Agent/HITL 纳入旧 P0，阶段顺序与 v6 冲突 |
| `v3_stage0_adr.md` | 归档 | 预设旧 V3 Agent 与超出 R23 最小闭环的可靠性设计 |
| `v3_api_contract.md` | 归档 | 定义生产 `/api/v3/investigations`、审批等接口，v6 不允许九月实现 |
| `v3_state_machines.md` | 归档 | 混合摄取、Investigation、草稿和审批状态机 |
| `v3_data_model.md` | 归档 | 包含 Investigation、Evidence、Trace、Approval 等旧生产数据模型 |
| `v3_acceptance_examples.md` | 归档 | 验收范围覆盖旧完整 Agent 和超出 R23 的机制 |
| `v3_agent_decision_contract.md` | 归档 | 属于 Agent 实现契约，而 v6 的 R5 仅做评测协议设计 |
| `v3_evaluation_protocol.md` | 归档 | 虽有可参考的三组对照，但混入旧实现、真实 Provider 和旧时间表 |
| `v3_test_matrix.md` | 归档 | 测试矩阵映射旧完整 V3，而非 v6 的 R1/R23/R4/R5 |
| `PARKING_LOT.md` | 归档 | 使用旧 V3/P0 口径；九月不做项现统一由 `docs/r_protocol.md` 管理 |

## 使用规则

- 可以用这些文档了解历史思考和被放弃的方案。
- 不得把其中的目标、接口、状态、数字或验收项写成当前能力。
- 后续若某项重新进入范围，必须先在对应阶段重新决策并写入 `docs/DEV_STATE.md`，不能直接“恢复旧设计”。
- 本目录不证明任何功能已经实现，也不包含实验结果。
