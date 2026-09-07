# RAG 九月开发协议映射（v6）

## 1. 文档地位

- 上位协议：`D:\AI_Internship_2026\求职材料\2026-09_双项目升级计划_评审版.md`
- 已读取版本：**《2026 年 9 月 双项目升级执行协议 v6》定稿版**
- 本文件用途：把 v6 映射为 Enterprise Knowledge Assistant 仓库内可核对的阶段边界。
- 冲突顺序：用户在 v6 之后的明确补充裁决 > v6 上位协议 > 本文件 > 当前阶段专项设计 > 历史文档和旧聊天记录。
- 本文件只冻结边界，不证明 R1、R23、R4 或 R5 已经完成。

## 2. 当前生产基线与九月计划必须分开

截至 R0 开工日（2026-08-31），实际代码能够证明的生产基线是：

| 领域 | 当前已经实现 | 九月计划，当前尚未实现 |
| --- | --- | --- |
| 摄取 | `POST /api/v1/documents` 同步处理并返回 `201 Created` | 返回 `job_id` 的异步 API、Job 状态查询、独立 Worker、崩溃恢复 |
| 状态 | Document 只有 `processing / ready / failed` | 独立 Job 表和 Job 状态机 |
| 向量存储 | 进程内使用 Qdrant Local 路径 | Qdrant Server 和容器化连接 |
| SQLite | 文档元数据；每次仓储操作创建连接 | API 与 Worker 两个进程并发访问所需的 WAL、`busy_timeout` 和短事务策略 |
| 部署 | 本地 Python 应用启动 | v6 分阶段定义的最小 Compose 交付 |
| Agent | **没有接入生产应用或生产 API** | R5 仅设计受限 Agentic Retrieval 对照实验协议，是否启动取决于阶段门禁 |

因此，README、简历、演示和阶段报告不得把右栏内容写成现有能力。

## 3. v6 冻结时的 Agent 定位（历史基线）

v6 冻结时，Agent 仅定位为 `experiments/` 或 `evaluation/` 下的**受限 Agentic Retrieval 对照实验对象**：

- R5 只完成 failure taxonomy、step-level evaluation protocol、三组公平对照、轨迹记录要求和 adversarial cases 设计；
- 不进入 `app/`，不新增生产 Agent API，不改变既有生产回答链路；
- 不把“设计了 Agent 评测协议”表述成“实现了 Agent”；
- R6（Agent 实现）和 R7（Agent 实验）原属于十月开发候选，不属于 v6 的九月主分支承诺；
- 旧 V3 文档里的 Investigation、Draft、Approval、归档、HITL 和 LangGraph 主链路不得直接恢复。

2026-09-07 的补充授权仅按第 10 节窄范围覆盖上述 R6/R7 延期项。R6 受限
路由可以进入版本化 V2 Answer API；这不把 R5 的 Agentic 5×2 协议、完整
Agent 系统或 R7 Graph Retrieval 自动变为已实现能力。

## 4. 阶段边界

### R1：Qdrant Server 与最小 Docker Compose

目标是把 Qdrant 从 Local 模式切到 Server，并得到真实、可复现的最小容器运行方式。

R1 必须在实施时二选一并记录依据：

1. FastAPI 进入 Compose：Compose 中是 FastAPI + Qdrant 两个服务；SQLite 必须使用 named volume 保证持久化。
2. FastAPI 留在宿主机：Compose 中只有 Qdrant 服务；应用通过端口连接 Qdrant。

R1 验收时不能声称“FastAPI + Worker + Qdrant 三服务完整 Compose”，因为独立 Worker 属于后续 R23。R1 本身不实现异步 Job、Worker 或 Agent。

### R23：异步摄取最小完整闭环

R23 是九月 RAG 的核心工程阶段，必须在同一阶段同时完成：

- 异步上传 API 快速返回 `job_id`；
- Job 持久化表和可查询的 Job 状态；
- 与 FastAPI 分离的单机、单 Worker 进程；
- Worker 调用摄取核心完成文件解析、切分、Embedding、Qdrant 写入和 SQLite 状态更新；
- 一个**预先定义、可重复演示**的崩溃点；
- Worker 重启后能识别并恢复该未完成 Job；
- 幂等或补偿保证恢复后不产生重复的可见 Chunk；
- 自动化测试和最小集成验收通过。

这就是 R23 的最小完整定义。缺少 `job_id`、状态查询、独立 Worker、明确崩溃点或重启恢复中的任何一项，都不能宣称 R23 完成。详细去重系统、通用重试队列、分布式所有权等溢出范围进入 R2.5 或后续阶段。

R23 不改变既有同步 V1 API，除非届时专项设计明确新增兼容接口；不得用“后台函数”冒充独立 Worker。

### R4：同步与异步的测量和上线判断

R4 在 R23 通过后进行，不新增主要功能。必须实际比较并记录：

1. API 接收延迟；
2. 端到端摄取时间；
3. API responsiveness；
4. 连续上传行为；
5. crash recovery；
6. timeout 行为；
7. complexity trade-off。

在实验完成前，不预设“异步更快”或“异步一定应该替换同步”。异步即使端到端更慢，也可能因快速接收、可查询状态和可恢复性而有工程价值；最终结论必须由 R4 结果支持。

### R5：条件启动的 Agent 评测协议设计

R5 只有在 v6 时间门禁和前序阶段状态允许、且用户另行批准时才启动。R5 只设计协议，不实现或运行 Agent 系统。

协议至少覆盖：

- Dense Top-5；
- Dense Top-10；
- Agentic 5×2（每轮 Top-5、最多两轮、总候选预算最多 10）；
- 用第二轮 Jaccard / 替换比例区分“策略找到新证据”与“只是多取证据”；
- 固定数据、Embedding、生成模型、回答指令、证据格式、参数和版本记录；
- 可回放 trajectory、failure taxonomy 和 adversarial cases。

R5 完成只能表述为“设计了评测协议”，不能表述为“实现并跑完 Agent”。

## 5. R23 的 SQLite 双进程并发约束

独立 Worker 出现后，FastAPI 和 Worker 会同时读写同一个 SQLite 文件；“单 Worker”不等于“没有并发”。R23 设计和测试必须覆盖：

- **WAL**：允许读取与写入更合理地并行，但不把 SQLite 变成多写者数据库；
- **`busy_timeout`**：短暂锁竞争时有限等待，避免立即报 `database is locked`；
- **短事务**：数据库事务内只做必要的状态检查和更新，禁止把解析、Embedding、Qdrant 网络调用放在持锁事务内；
- **有限重试**：只针对可识别的短暂锁冲突，次数和退避值在 R23 基于测试冻结；
- **条件更新**：领取 Job 和关键状态转换必须检查旧状态，避免同一个 Job 被重复推进；
- **回滚测试**：事务失败后不得留下半更新的 Job/Document 状态。

具体 `busy_timeout`、重试次数、Job 状态名和迁移方式不是 R0 凭空决定的参数；它们由 R23 基于实际仓储实现和故障测试冻结，并记录在 `docs/DEV_STATE.md`。

P0 只承诺单机、单 Worker。它不支持网络分区、多个 Worker 争抢、旧 Worker 晚到竞争，因此不引入 Lease、Heartbeat、Generation 或 Fencing。

## 6. 删除—摄取竞态的九月规则

R23 采用最小、可验证的“活动摄取期间禁止删除”语义：

- 当 Document 对应 Job 仍处于待处理或处理中状态时，`DELETE` 返回 HTTP `409` 和稳定错误码 `DOCUMENT_PROCESSING`；
- P0 不提供取消接口，`DELETE` 不能隐式取消 Job；
- 拒绝删除时不得删除文件、Document、Job 或 Qdrant Point；
- 删除判定与 Job 活跃状态检查必须在 SQLite 的同一个短事务边界内完成，避免“刚检查完就被 Worker 领取”的时间窗；
- Worker 领取 Job 时也必须条件检查 Document 仍可处理；
- Worker 崩溃后，Job 在恢复完成或明确失败前仍视为活动，删除继续返回 `409`；
- `ready` 或终态失败文档的最终删除细节在 R23 结合现有 V1 删除语义写测试冻结，但不得破坏现有同步 API。

选择该规则是为了在单 Worker P0 中把竞态压缩成清晰、可测试的状态约束。协作式取消、强制删除和更复杂的并发所有权进入后续阶段。

## 7. 当前仍明确不做

- R2.5 的扩展重试、复杂去重和超出最小闭环的异步增强；
- R8 的完整可观测性平台；
- 生产 Agent API、Investigation 工作流、Draft、Approval、正式归档和 HITL；
- Redis、Celery、RabbitMQ、多 Worker、分布式任务队列；
- Lease、Heartbeat、Generation、Fencing、网络分区处理；
- 完整认证、多租户、RBAC 和公网生产部署；
- 生产 Reranker、生产 GraphRAG、多智能体和通用工具调用平台；R7 只允许在
  `evaluation/experiments/` 做预注册的学校领域 Graph Retrieval 对照；
- Prometheus/Grafana 等监控仪表盘；
- 未经授权的真实 Provider 调用和任何付费评测。

## 8. 阶段门禁与 Git 纪律

- 已完成主线顺序为 R0 → R1 → R23 → R4 → 条件启动 R5；补充授权后的顺序
  是 R6 完成并通过⑤ → 用户单独批准 R7，仍不得顺手推进下一阶段。
- 每阶段完成后更新 `docs/DEV_STATE.md`，将⑤拥有权验证保留为“未完成”，停止开发。
- 用户完成该阶段约定的拥有权验证并明确批准后，才能进入下一阶段。
- **2026-09-01 用户补充裁决**：从 R1 验收起，⑤只保留与就业/面试直接相关的知识点讲解和少量真实源码问题；取消“本人亲手修改真实实现”和必须产生 `git diff` 的要求。问题质量高于数量，不为凑满三题设置概念复述题。该裁决只改变学习验收形式，不降低代码测试、阶段停止或下一阶段显式授权门禁。
- 协议/预注册与实验结果必须独立提交；结果未产生前，提交信息不得暗示已经有实验结论。
- 不提交 `.env`、密钥、真实敏感文档或 Provider 原始秘密。
- R0 只处理文档与协议，不修改 `app/`、配置、依赖或生产逻辑。

## 9. R0 分诊结论

旧 V3 的 10 份设计文件整体移动到 `docs/archive/rag_v3_pre_v6/`。详细逐文件原因见该目录的 `README.md`。

它们被归档而不是删除：历史取舍仍可追溯，但不会再与活动协议并列。任何被延期能力若未来重新进入范围，都必须重新设计、测试和批准，不能直接把旧文档恢复为执行契约。

## 10. v6 之后的 R6/R7 补充授权（2026-09-07）

用户在 R0–R5 完成后明确扩大后续范围。该裁决晚于 v6 和 R5，因而只在以下窄范围内覆盖“R6/R7 未授权”的旧状态：

- R6 现在获准实现三分类 `retrieve / direct_answer / refuse` 的受限路由控制器；
- Dense Evidence 不足时最多进行一次确定性查询改写和一次额外检索；
- R6 不使用 LangGraph、Memory、Multi-Agent 或多轮循环；
- `direct_answer` 只处理问候、系统能力和使用方法，事实问题必须检索或拒答；
- R6 完成、测试、独立评测并通过拥有权验证前，R7 不得开始；
- R7 未来只在 `evaluation/experiments/` 建设学校领域 Property Graph 和 Graph+Dense 对照，实验通过前不进入 `app/`；
- 真实 Provider 仍需逐次提交调用量、token 上限和预算并另行获批；
- R8、R2.5、通用 Agent 平台和其他未重新授权能力仍不在范围内。

R6 的详细冻结契约见 `docs/r6_routing_agent_design.md` 与 `evaluation/r6_routing_protocol.json`。旧 R5 协议保留为“实施前预注册”的历史证据，不回写成已经实现。

截至 2026-09-07，R6 实现与首次冻结边界评测已经完成，结果见
`evaluation/r6_routing_report.json`；⑤拥有权验证仍未完成。该工程结果不自动
授权 R7，也不改变“R7 只能留在实验目录、结果通过后再决定是否接入主链路”的
边界。
