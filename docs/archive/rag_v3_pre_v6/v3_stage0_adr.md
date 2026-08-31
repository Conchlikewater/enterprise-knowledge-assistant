# V3 阶段 0 架构决策记录（ADR）

> 状态：范围对齐修订完成，等待阶段 0 最终验收；尚未实现。
> 适用范围：V2 异步摄取、最小 Docker 交付与 V3 受限两轮调查 Agent。
> 规则：ADR、API、状态图、数据模型、决策契约和测试矩阵发生冲突时，先修正文档，不由实现自行选择。

## ADR-001：分阶段门禁

实施顺序固定为：阶段 0 文档冻结 → 阶段 1 Qdrant Server 与最小 Compose → 阶段 2 单 Worker 异步摄取 → 阶段 3 两轮 Agent → 阶段 4 评测和交付。

阶段 2 的幂等、SQLite 并发、崩溃恢复、Qdrant 补偿和 ready 可见性没有通过前，不进入阶段 3。每阶段完成后暂停，下一阶段需要用户单独批准。

## ADR-002：保留 V1，新增版本化异步接口

`POST /api/v1/documents` 继续同步返回 201。新增 `POST /api/v2/documents` 返回 202、Document ID 和 Job ID。V1 与 V2 可复用内部 processing core，但 V2 Worker 不能调用会创建新 Document 或再次落盘的完整 `ingest()` 外壳。

## ADR-003：Qdrant Server 与最小 Compose 属于 P0

正式的 API、Worker 和演示环境使用 Qdrant Server。Local/Fake 只允许单进程隔离测试。最小 Compose 只包含 `api + worker + qdrant`，包含持久卷和真实依赖健康检查。

旧 Local 数据不直接搬运内部文件；需要保留时先备份，再通过原文受控重摄取。任何清理现有数据的动作都要再次确认。

## ADR-004：P0 使用 SQLite Job Queue 和一个 Worker

P0 使用 SQLite 持久任务表与独立 Worker。Compose 固定一个 Worker 副本，运行手册也只允许一个 Worker。Redis、Celery、RabbitMQ、PostgreSQL 和多 Worker均延期。

Worker 启动时必须取得共享数据目录上的 OS 级独占锁。锁被占用时第二个 Worker 必须失败退出。P0 可靠性只覆盖同一主机、共享本地数据目录和单 Worker 崩溃重启，不覆盖网络分区、多主机、双活 Worker或旧 Worker 晚到竞争。

## ADR-005：P0 不使用 Generation、Lease、Heartbeat 或 Fencing

P0 不保存 `ingestion_generation`、`active_ingestion_generation`、`lease_owner`、`lease_token`、`lease_expires_at` 或 `heartbeat_at`。

最小可靠性由以下不变量组成：

1. OS 进程锁保证异步 Worker 单实例；
2. SQLite 条件更新保证 queued→processing 原子领取；
3. 新 Worker 只有在获得进程锁后才能恢复遗留 processing Job；
4. processing Document 不可检索；
5. 重放前可按 `document_id` 安全清理未 ready Document 的残留；
6. 确定性 Chunk ID 使相同重放覆盖同一点；
7. 只有全部写入成功后才在短事务中提交 Job=succeeded、Document=ready；
8. 失败先补偿，再进入 failed。

多 Worker、Lease、Heartbeat、Generation、Fencing 进入 P1。实现和文档不得把 P0 描述为分布式 exactly-once。

## ADR-006：确定性 Chunk ID

使用 UUIDv5，规范输入为：

```text
document_id
+ chunker_version
+ chunker_config_hash
+ page_number（TXT 使用 0）
+ global_chunk_index
+ chunk_content_sha256
```

Qdrant Point 不携带 generation。每个 Point 至少保存 Chunk ID、Document ID、页码、全局索引、内容哈希、切分器版本和配置哈希。处理失败或重启恢复时，在单 Worker 排他条件成立后按 Document 清理并重放。

## ADR-007：上传采用 staging Saga

顺序固定为：临时落盘并计算 SHA → 文件校验 → SQLite 事务创建 Idempotency/Document/Job(staging) → 原子重命名 → 条件更新 queued → 返回 202。

恢复器只在唯一 Worker 进程内运行，处理孤儿临时文件、规范文件缺失和 staging Job。文件未就绪时 Job 不能进入 queued。跨文件系统、SQLite 和 Qdrant 没有分布式事务，因此通过幂等动作和补偿实现最终收敛。

## ADR-008：保留 SHA 唯一与请求幂等

- 同 Idempotency-Key、同文件指纹：返回原 Document/Job；
- 同 Key、不同文件：`409 IDEMPOTENCY_KEY_REUSED`；
- 不同 Key、相同 SHA：`409 DOCUMENT_ALREADY_EXISTS`；
- failed Document 通过显式 retry 重新上传相同指纹文件，创建新 Job，保留 Document ID；
- 不修改现有 `documents.sha256 UNIQUE`。

当前为本地单用户范围，可以安全返回已有 Document ID；未来引入身份或多租户后必须先做权限检查。

## ADR-009：状态、删除和取消边界

队列状态只属于 IngestionJob。Document 创建后为 processing。P0 不提供取消，也没有 cancelled 状态。

Document=processing 或关联 Job=staging/queued/processing 时，DELETE 固定返回：

```text
HTTP 409
error.code = DOCUMENT_PROCESSING
```

ready/failed Document 在没有活跃 Investigation 引用时可以删除。Draft、Approval、已批准报告保留策略因这些能力已延期到 P1，不进入 P0 删除规则。

## ADR-010：SQLite 并发策略

API 与 Worker 是独立进程，因此必须启用 WAL、`busy_timeout`、短事务和有上限的锁重试。所有外部 I/O 均在事务外执行。

P0 默认冻结为：`busy_timeout=1000ms`；首次失败后最多再重试 2 次，退避分别为 50ms、150ms。只重试 SQLite busy/locked，唯一约束、状态冲突和校验错误不重试。

API 耗尽重试后返回 `503 DATABASE_BUSY`。Worker 耗尽重试后停止当前任务循环并以失败状态退出，不继续产生外部副作用；新的唯一 Worker 取得进程锁后恢复遗留任务。阶段 2 固定 fixture 必须验证该默认值；如果需要调整，先修改 ADR 和配置版本再实现，不能在代码中静默改变。

选择依据必须包含并发创建 Job、Worker 更新其他 Job、回滚和重启恢复结果。未出现瓶颈前不迁移数据库。

## ADR-011：Investigation 只使用五状态

P0 状态固定为：`created / running / needs_clarification / completed / failed`。

P0 不包含 Draft、Approval、revise、reject、正式归档、cancel 或版本化报告。调查报告是 Investigation 完成结果。SQLite 是 Investigation 业务状态真相源；LangGraph Checkpoint 和轨迹只用于执行恢复与离线回放，不能覆盖 SQLite 终态。

## ADR-012：Agent 使用纯决策内核与受限工具

LangGraph 只负责编排，RetrievalService 继续负责实际检索。以下逻辑优先实现为无 I/O 纯函数：覆盖率、第二轮触发、停止原因、证据充分性、证据表构造和文档范围越界判定。

模型只能使用限定范围检索和读取 Evidence/Citation 的白名单工具。顶层 `document_ids` 由服务端注入所有检索调用，模型不能覆盖或扩大。P0 禁止任意网络、Shell、代码执行、文件访问和数据库写入工具。

整个 Investigation 最多两轮检索；每轮接纳的全局去重候选最多 5 个，总预算最多 10 个。详细规则以 `v3_agent_decision_contract.md` 为准。

## ADR-013：三组预算对照与参数选择

正式评测同时保留 Dense Top-5、Dense Top-10 和 Agentic 5×2。三组使用相同题集、文档、Embedding、生成模型、温度、最终回答指令和 Evidence 格式。

规划 Prompt 不要求相同：单轮、子问题规划和第二轮查询 Prompt 分别版本化。每组必须报告去重候选数、Evidence Recall、MRR、延迟、检索次数和 Provider 成本。

阶段 0 只冻结 score threshold、coverage threshold 和最低 Evidence 数的候选集合；进入 Agent 开发前使用固定 fixtures 选择最终配置。旧报告中的 `0.37` 不自动成为配置。

## ADR-014：CI 与真实 Provider 隔离

CI 只使用 Fake/确定性 Provider、固定轨迹、固定评测 fixtures 和无 Key 的 Qdrant Server，不读取真实 Key，也不产生费用。

真实 Provider 对照使用单独命令，执行前再次确认 Provider、模型、Prompt 版本、调用次数、token 上限和预算。结果必须明确区分离线回放与真实在线调用。

## ADR-015：DeepSeek 结构化输出协议先冻结、真实调用待授权

阶段 0 只冻结 `deepseek-v4-flash` 候选模型、Prompt 版本、Pydantic Schema、兼容解析、一次受控重试、模板化降级、请求次数、token 上限和预算模板，状态标记为“待验证”。

真实调用不阻塞阶段 0 文档冻结，但必须在 Agent 实现前单独申请授权。未执行时不能宣称 DeepSeek 结构化 Agent 输出已经验证。

## ADR-016：依赖使用 pip-tools 锁定

仓库当前没有 lockfile。为减少迁移成本，保留 `requirements.txt` 和 `requirements-dev.txt` 作为直接依赖输入，后续经批准安装 pip-tools，并为 Python 3.12 生成 `requirements.lock.txt` 与 `requirements-dev.lock.txt`。

阶段 0 不安装工具、不生成锁文件。是否启用 hash 锁定，要在 Windows 开发环境与 Linux CI 安装都通过后决定。

## ADR-017：P1 延期能力

Draft、Approval、正式归档、取消、多 Worker、Lease、Heartbeat、Generation、Fencing、Redis/Celery、完整认证、多租户、Reranker、GraphRAG 和监控仪表盘均延期到 P1。延期原因和重新进入条件统一记录在 `PARKING_LOT.md`。
