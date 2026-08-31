# 2026 年 9 月升级规格：可靠异步摄取与受限两轮调查 Agent

> 状态：阶段 0 范围对齐修订完成，等待最终验收；阶段 1 尚未批准。
> 启动条件：用户完成当前学习计划，并在九月单独批准阶段 1。
> 证据边界：本文是实施计划，不代表功能已经实现，也不能把计划能力写入简历。

## 1. 项目基线与升级目标

当前仓库已经完成 V1/V2 RAG 基线：TXT/PDF 同步摄取、SQLite 文档元数据、Qdrant Local、Dense 检索、文档范围过滤、Search/Answer 分离、应用侧 Citation、无证据拒答、OpenAI/DeepSeek Provider、自动化测试和固定离线评测。既有数字只适用于 10 份合成文档和 50 道问题，不能推广为真实企业效果。

九月 P0 不建设完整企业平台，目标是补齐以下作品集证据：

1. Qdrant Server 与最小 Docker Compose；
2. 单机、单 Worker 的可靠异步摄取；
3. 受限 Agentic 两轮检索；
4. 子问题拆解、多文档对比、证据表和调查报告；
5. 可在 CI 离线回放的轨迹评测，以及经单独授权的真实 Provider 对照评测；
6. README、架构图、状态图、实验报告和局限性说明。

项目升级后的准确定位是：

> 一个面向选定企业文档范围、支持可靠异步摄取和最多两轮证据调查的本地 RAG 应用。

它仍不是经过真实企业流量、完整身份体系和多租户验证的生产平台。

## 2. 必须保持的兼容边界

- 保留 `POST /api/v1/documents` 同步摄取和 `201 Created`；
- 新增 `POST /api/v2/documents` 异步摄取和 `202 Accepted`；
- 现有 `RetrievalService` 继续负责 ready 校验、Embedding、文档范围过滤、Top-K 和分数过滤；
- 现有 `AnswerService` 继续负责证据回答、拒答和应用侧 Citation；
- V2 Worker 只能调用接收既有 `document_id` 和安全文件路径的 processing core，不能再次创建 Document 或重新走完整上传外壳；
- `documents.sha256 UNIQUE` 保留；不同 Key 上传相同 SHA 仍返回 409；
- Dense 保持正式检索方案；Hybrid/BM25 继续作为负向实验，Reranker 不进入 P0；
- 现有 10 文档/50 题作为回归集，不用它反复调参；
- 现有测试和 branch-aware 85% 覆盖率门禁不能无解释退化；
- `.env`、API Key、内部路径和私密原文不得进入 Git、日志或 Trace。

## 3. P0 架构

```text
FastAPI
├── /api/v1/documents          同步 201，兼容保留
├── /api/v2/documents          异步 202，创建 Document/Job
├── /api/v2/ingestion-jobs     状态查询
├── /api/v2/documents/{id}     状态查询、受限删除、显式重试
├── /api/v1/search|answers     既有检索与回答
└── /api/v3/investigations     创建、查询、提交澄清

API / Application Services
├── IngestionService + processing core
├── IngestionJobService
├── RetrievalService / AnswerService
├── InvestigationService
├── AgentGenerationProvider
└── Trace / Evaluation adapters

Agent workflow
validate_scope
  -> decompose_subquestions
  -> retrieval_round_1（全局候选预算 5）
  -> pure decision kernel
  -> [需要且有预算] retrieval_round_2（全局候选预算 5）
  -> build_evidence_table
  -> answer_or_refuse
  -> persist investigation result

Storage / Runtime
├── SQLite：Document、Job、Investigation、Evidence、Trace 等业务状态
├── Qdrant Server：可重建的 Chunk、向量和来源 metadata
├── 文件系统：staging 与规范原文件
├── 单个独立 Worker：异步摄取
└── Docker Compose：API + Worker + Qdrant
```

LangGraph 可以负责工作流编排和节点恢复，但不能替代 RetrievalService，也不能成为业务状态真相源。P0 没有审批副作用，调查报告只是 Investigation 的结果。

## 4. 异步摄取范围

### 4.1 状态

```text
DocumentStatus：processing / ready / failed / deleting / deleted
IngestionJobStatus：staging / queued / processing / succeeded / failed
```

队列状态只属于 Job。Document 创建后使用 `processing`，不增加 Document `queued`。P0 没有 cancelled 状态，也没有取消接口。

### 4.2 上传 Saga

固定顺序：流式临时落盘并计算 SHA → 校验 → SQLite 同一事务创建 Idempotency/Document/Job(staging) → 原子重命名到规范路径 → 条件更新 Job=queued → 返回 202。

恢复器处理：

- final 文件存在且 Job=staging：校验后条件入队；
- temporary 存在而 final 不存在：完成原子重命名后入队；
- 两者均不存在：Job/Document 失败收敛；
- 没有数据库记录的过期临时文件：按保留规则清理；
- 任一恢复动作必须幂等，不得创建第二个 Document 或 Job。

### 4.3 单 Worker 最小可靠性

P0 明确不保留 `ingestion_generation`，也不实现 Lease、Heartbeat 或 Fencing：

1. Worker 启动时获取共享数据目录上的 OS 级独占进程锁；无法获取时必须失败退出；
2. Compose 固定 `worker` 副本数为 1，运行手册禁止并行启动第二个 Worker；
3. Job 通过 SQLite 条件更新从 queued 原子领取为 processing；
4. Worker 崩溃后，新的唯一 Worker 取得进程锁，再由启动恢复器检查遗留 processing Job；
5. 恢复前按 `document_id` 清理该未 ready Document 的 Qdrant 残留，再安全重放；
6. Chunk ID 采用确定性 UUIDv5；相同输入重放覆盖同一点；
7. Document 只有在文件、Chunk 和 Qdrant 写入全部成功后才变为 ready；检索只接受 ready Document；
8. Qdrant 部分写入、SQLite 回滚或永久失败必须进入补偿清理；
9. SQLite 事务必须短小，事务中不得调用 Embedding、Qdrant 或 LLM。

该协议只保证同一主机、共享本地数据目录、单 Worker 的崩溃恢复。P0 不支持多主机、网络分区、两个 Worker 同时存活或旧 Worker 晚到竞争。

确定性 Chunk ID 的规范输入为：

```text
document_id
+ chunker_version
+ chunker_config_hash
+ page_number（TXT 使用 0）
+ global_chunk_index
+ chunk_content_sha256
```

### 4.4 删除与重试

- Document=`processing`，或关联 Job=`staging/queued/processing` 时，DELETE 固定返回 `409 DOCUMENT_PROCESSING`；
- P0 不提供取消或 force 删除；
- ready/failed 且不存在活跃 Investigation 引用时，可以进入 deleting 并完成文件、Qdrant、业务记录的幂等清理；
- failed Document 显式 retry 时必须重新上传相同文件指纹，保留 Document ID、创建新 Job；
- 文件恢复到规范路径前，新 Job 只能是 staging；
- failed 终态前应清理不完整文件和 Qdrant 残留；`stored_path` 仍保存规范目标地址，但不承诺文件存在。

## 5. SQLite 并发边界

单 Worker 不等于单进程：FastAPI 与 Worker 会同时读写 SQLite。P0 必须：

- 启用 WAL；
- 配置并记录 `busy_timeout`；
- 使用短事务和条件更新；
- 对 `database is locked` 进行有上限的退避重试；
- 事务失败完整回滚；
- 禁止在数据库事务内调用网络服务；
- 测试 API 创建 Job 与 Worker 更新其他 Job 的并发；
- 测试 Worker 重启、Qdrant 部分写入、重复 Key 和重复 SHA。

P0 默认使用 `busy_timeout=1000ms`，首次 busy/locked 失败后最多重试 2 次，退避 50ms、150ms。API 耗尽后返回 `503 DATABASE_BUSY`；Worker 耗尽后停止循环并退出，由下一唯一 Worker恢复。阶段 2 fixture 若证明默认值不合适，必须先修改 ADR 和配置版本。SQLite 只声明单机小规模能力；只有实测成为瓶颈后才评审 PostgreSQL 或 Redis。

## 6. Investigation 与两轮 Agent

### 6.1 REST 与状态

P0 提供：

- 创建 Investigation；
- 查询 Investigation；
- 在 `needs_clarification` 时提交澄清信息；
- 统一的 4xx/5xx 安全错误。

状态只允许：

```text
created / running / needs_clarification / completed / failed
```

不包含 waiting_approval、rejected、cancelled 或 Draft 版本状态。调查报告是 Investigation 结果，不是已审批或正式归档报告。

### 6.2 Agent 约束

- 顶层 `document_ids` 必须非空，所有检索调用自动继承该范围；模型不能新增文档；
- 整个 Investigation 最多两个逻辑检索轮次，不是每个子问题各两轮；
- 每个逻辑轮次合并、去重后最多接纳 5 个候选 Chunk；两轮总候选预算最多 10；
- 子问题规划可以产生多条查询，但轮次控制器必须在全局预算内分配并截断；
- 范围判断、覆盖率、第二轮触发、停止原因、证据充分性和证据表构造尽量实现为无 I/O 纯函数；
- Provider 与 Retrieval 产生轨迹，决策内核只读取结构化轨迹；
- 轨迹必须可序列化和离线回放；CI 不需要 API Key；
- 文档内容是不可信 Evidence，不得改变系统规则或调用非白名单工具；
- P0 不提供网络、Shell、代码执行、任意文件、任意数据库写入工具。

公式、候选参数和停止原因见 `docs/v3_agent_decision_contract.md`。

## 7. 评测口径

### 7.1 三组公平对照

固定保留：

1. 单轮 Dense Top-5；
2. 预算匹配的单轮 Dense Top-10；
3. 两轮 Agentic：每轮最多 5 个候选、全局最多两轮、总候选预算最多 10。

三组都记录去重候选数、Evidence Recall、MRR、延迟、检索次数和 Provider token/成本。不得把候选预算增加造成的收益单独描述成 Agent 策略收益。

统一：题集、文档、Embedding、生成模型、温度、最终回答指令和 Evidence/Citation 格式。单轮回答 Prompt、Agent 规划 Prompt、第二轮查询 Prompt 分别版本化并完整记录，不宣称规划 Prompt 完全相同。

### 7.2 参数冻结

- 正式对照臂的候选预算按上述 Top-5/Top-10/5×2 固定；
- score threshold 的候选网格为 `None / 0.20 / 0.25 / 0.30 / 0.35 / 0.40`；
- coverage threshold 的候选集合为 `0.60 / 0.75 / 1.00`；
- 每个已覆盖子问题所需 Evidence 数候选为 `1 / 2`；
- 不直接采用旧语义实验中的 `0.37`；
- 进入 Agent 开发前，在固定 fixtures 上离线选择并写入版本化实验配置，记录指标、拒答误差和选择理由；
- 现有 10 文档/50 题只做回归，V3 参数使用新建 Agent fixtures 的开发部分选择，最终盲审题不参与调参。

### 7.3 24 道 Agent 题

每题至少标注：题型、允许 document IDs、期望子问题、期望 Evidence/Chunk、期望结论、是否进入第二轮、期望停止原因、应答/拒答标签和 Citation 要求。

- Week 1：冻结 Schema 与评分规则；
- Week 2：完成第一批题目；
- Week 3：完成剩余题目；
- Week 4：间隔数日后进行第二次盲审，不查看第一次理由；
- 两次不一致的题目必须修改、删除或标为歧义题，歧义题不进入硬门禁。

详细指标和 DeepSeek 待验证冒烟模板见 `docs/v3_evaluation_protocol.md`。

## 8. CI 与真实 Provider 分层

CI 只运行：

- Fake/确定性 Provider 单元测试；
- 固定轨迹回放；
- Agent 决策纯函数；
- 异步状态与故障注入；
- 固定评测 fixtures 指标回归；
- 无 API Key 的 Qdrant Server 小型集成测试。

CI 不读取 OpenAI/DeepSeek Key，不产生费用。真实 Provider 使用单独的显式命令；运行前必须再次确认模型、Prompt 版本、调用数、token 上限和预算。报告必须记录时间、Provider、模型、token、成本和延迟。

DeepSeek 结构化输出在阶段 0 只冻结协议，状态为“待验证”，不阻塞文档冻结。进入 Agent 实现前再申请真实调用授权。

## 9. 依赖锁定

当前仓库只有范围式 `requirements.txt` 和 `requirements-dev.txt`，没有 lockfile。P0 选择与现有 pip 工作流兼容的 `pip-tools`：

- 保留现有两个文件作为直接依赖输入；
- 经单独批准安装工具后，生成 `requirements.lock.txt` 和 `requirements-dev.lock.txt`；
- 本地演示与 CI 使用 Python 3.12 和锁文件安装；
- 依赖升级通过重新编译、测试和审查完成，不手工修改生成文件；
- 是否启用 hashes 在 Windows/Linux 双环境验证后决定。

阶段 0 不安装 pip-tools，也不生成锁文件。

## 10. 阶段门禁与五周时间线

### 阶段

1. 阶段 0：本文档集冻结；
2. 阶段 1：Qdrant Server 连接适配与最小 Compose，完成 V1 回归；
3. 阶段 2：SQLite Job Queue、processing core、单 Worker、并发与恢复；
4. 阶段 3：受限两轮 Agent、证据表和调查报告；
5. 阶段 4：24 题评测、真实 Provider 对照、README 和交付收口。

阶段名称与周次不是同一概念。一周可以完成前一阶段并在获得批准后进入下一阶段。

### 周次

- Week 1：阶段 0 最终冻结；获批后完成 Qdrant Server、Compose、评测 Schema；
- Week 2：异步摄取、SQLite 并发测试、第一批 Agent 题；
- Week 3：异步门禁、两轮检索、剩余 Agent 题；
- Week 4：多文档对比、证据表、调查报告、盲审和对照实验；
- Week 5：停止新增功能，修复 Bug，完成报告、README、演示和简历材料。

若 Week 2 结束时异步摄取门禁未通过，不进入 Agent。若 Week 3 动态两轮 Agent 不稳定，降级为确定性两阶段 Workflow，但保留相同轨迹结构、范围限制、候选预算和评测协议。

## 11. P0 完成定义

1. V1 同步 201、Search、Answer、Citation 和拒答无回归；
2. V2 异步 202、状态查询、幂等、Saga、单 Worker 恢复和失败补偿通过；
3. processing/活跃 Job 删除统一返回 `409 DOCUMENT_PROCESSING`，不存在取消接口；
4. Qdrant Server 与 `api + worker + qdrant` Compose 可重复启动并持久化；
5. WAL、锁冲突、有限重试、事务回滚和重启恢复测试通过；
6. Investigation 只使用五状态和完整 REST 查询/澄清契约；
7. 全局最多两轮、每轮 5 个候选、文档范围继承和纯决策内核通过自动化测试；
8. 能生成多文档证据表和带 claim-level Citation 的调查结果；证据不足时澄清或拒答；
9. 24 题 Schema、双轮标注和歧义处理完成；三组公平对照可复现；
10. CI 只使用 Fake/回放和无密钥 Qdrant；真实 Provider 结果与离线结果分开；
11. 旧回归和 branch-aware 85% 覆盖率门禁通过；
12. README、架构图、状态图、实验报告和限制说明与实际证据一致。

未获得授权或未执行真实 Provider 时，只能写“离线轨迹和 Fake Provider 已验证”，不能宣称真实 Agent 端到端已验证。

## 12. P1 与明确不做

P1 统一记录在 `docs/PARKING_LOT.md`，包括 Draft、Approval、正式归档、取消、Redis/Celery、多 Worker、Lease、Heartbeat、Generation、Fencing、完整认证、多租户、Reranker、GraphRAG 和监控仪表盘。

P0 不做通用多 Agent、任意 Tool Calling、MCP、微服务重写、Kubernetes、大型前端、OCR、本地模型训练或没有 bad case 支持的检索堆叠。

## 13. 面试边界

用户最终需要能够解释：

1. 为什么异步摄取不能只依赖 FastAPI BackgroundTasks；
2. 单 Worker 模式如何恢复，以及为什么不能宣称支持多 Worker；
3. 为什么 processing 文档对检索不可见；
4. SQLite 与 Qdrant 部分成功时如何补偿；
5. 为什么两轮检索必须与 Dense Top-10 做预算匹配对照；
6. coverage、第二轮触发和停止原因如何由纯函数决定；
7. Citation 的三个评分层面分别证明什么；
8. 为什么真实 Provider 与 CI 必须隔离；
9. 为什么 Hybrid、Reranker、GraphRAG 和审批闭环没有进入 P0；
10. 当前评测为什么不能代表真实企业环境。
