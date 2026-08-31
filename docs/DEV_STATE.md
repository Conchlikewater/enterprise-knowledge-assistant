# Enterprise Knowledge Assistant 开发状态

> 本文件是阶段接手和决策账本，不是功能宣传页。能力是否已实现，必须以源码、测试和 Git 证据为准。

## 1. 当前状态

- 上位协议：`D:\AI_Internship_2026\求职材料\2026-09_双项目升级计划_评审版.md`
- 协议版本：**《2026 年 9 月 双项目升级执行协议 v6》定稿版**
- RAG 九月升级真实开工日期：**2026-08-31**（Australia/Sydney）
- 当前阶段：**R0 协议对齐——文档实施已完成/待⑤验收**
- 已正式完成阶段：无
- 下一阶段：R1，**尚未开始**
- ⑤拥有权验证：**未完成**
- 工作区基线：R0 开工时 `main` 与 `origin/main` 无领先/落后，HEAD 为 `11449b22e5df9181ecb7952f034da2f6b4875143`

## 2. R0 接手上下文

### 当前生产代码能够证明的事实

- V1 上传是同步摄取，`POST /api/v1/documents` 返回 `201 Created`；
- Document 状态为 `processing / ready / failed`，没有 Job 表；
- Qdrant 使用 Local path 模式，不是 Qdrant Server；
- SQLite 当前主要保存文档元数据，尚未按 API + Worker 双进程并发边界设计；
- Search 与 Answer 分离，支持文档范围、Citation 和无证据拒答；
- OpenAI/DeepSeek 是回答 Provider 对照能力，不等于 Agent；
- 仓库当前没有生产 Agent、独立 Worker、异步摄取或三服务 Compose。

### 历史方案

R0 开工前，`docs/` 根目录有 10 份未跟踪 V3 设计文档。它们描述了比 v6 更大的旧 P0，包括完整 Investigation/Agent、Draft/Approval、旧状态机和更复杂的 Worker 可靠性机制。实际业务代码没有跟随这些文档修改。

R0 将它们整体归档到 `docs/archive/rag_v3_pre_v6/`，保留历史证据但取消执行地位。归档不是删除，也不表示旧方案已经实现。

## 3. 当前阶段决策

| 决策 | 结论 | 原因 |
| --- | --- | --- |
| 协议来源 | v6 是唯一上位规则 | 避免旧聊天、旧 V3 和实际执行范围互相冲突 |
| 旧 V3 文档 | 10 份整体归档 | 文件相互引用且混合 R23、R5、R6/R7；局部保留容易误执行 |
| Agent 定位 | 仅是 R5 的实验评测协议对象 | 九月不实现 Agent，不进入 `app/` 或生产 API |
| R23 P0 | 单机、单 Worker 最小闭环 | 证明真正异步、状态、崩溃恢复和一致性，不扩成分布式队列 |
| 删除—摄取竞态 | 活动 Job 时返回 `409 DOCUMENT_PROCESSING` | 不引入取消，形成最小、明确、可测试的竞态语义 |
| 多 Worker 可靠性 | Lease/Fencing 等延期 | 单 Worker P0 不解决网络分区或旧 Worker 晚到竞争 |
| R4 结论 | 保持开放 | 必须先测 API 延迟、端到端、恢复和复杂度，再决定工程价值 |

## 4. R0 修改范围

- 新建 `docs/r_protocol.md`：仓库内 v6 边界映射；
- 新建本文件：阶段状态、决策、未决问题和接手信息；
- 新建 `docs/archive/rag_v3_pre_v6/README.md`：历史资料说明和逐文件分诊；
- 将 10 份旧 V3 文档移动到上述归档目录；
- 归档独立提交：`d816394`（`docs(r0): archive pre-v6 RAG plans`）；
- 不修改 `app/`、配置、依赖、测试逻辑或生产 API；
- 不启动容器，不调用真实 Provider，不运行付费评测。

## 5. 未决问题

以下问题不在 R0 猜答案，必须在对应阶段检查现状、设计、测试后记录：

1. R1：FastAPI 进入 Compose，还是保留在宿主机而只容器化 Qdrant？
2. R1：若 FastAPI 进入 Compose，SQLite named volume、Qdrant volume 和健康检查如何落地？
3. R23：Job 的最终状态名、表字段、迁移方式和兼容 API 路径是什么？
4. R23：用于演示恢复的唯一明确崩溃点选在哪里，如何保证可重复？
5. R23：SQLite `busy_timeout`、锁冲突有限重试次数和退避值，经什么测试冻结？
6. R23：现有同步 `IngestionService` 抽取出的共享摄取核心边界是什么，如何避免同步/异步两套逻辑漂移？
7. R4：测量结果是否支持把异步接口作为演示主路径，还是只作为新增可选能力？
8. R5：到条件检查日时，前序质量和剩余时间是否允许启动协议设计？

## 6. 最容易误改或误报的位置

- `README.md` 当前正确描述 Qdrant Local 和同步摄取；R1/R23 完成前不要提前改成 Server/异步已完成。
- `app/api/routers/documents.py` 的现有 `201` 同步边界受保护；新增异步能力不能无意破坏它。
- `app/services/ingestion_service.py` 当前是完整同步流程；R23 应抽取可复用核心，不应复制一套漂移实现。
- `app/storage/sqlite_document_repository.py` 当前没有 Job 双进程并发协议；不能只加一张表就宣称恢复可靠。
- Qdrant 当前按本地路径初始化；R1 必须先完成连接适配和回归，独立 Worker 才能安全共享 Server。
- 当前删除逻辑不理解活动 Job；R23 必须按 `409 DOCUMENT_PROCESSING` 规则补齐竞态测试。
- 归档里的 Agent API、Approval、Lease/Fencing 只是历史设计，不能复制到九月主线。

## 7. 环境与安全记录

- R0 未安装或升级依赖；
- R0 未启动 Docker 或 Qdrant；
- R0 未调用 OpenAI、DeepSeek 或其他真实 Provider；
- `.env` 仍只作为本地配置使用，不读取、不记录、不提交；
- R0 未删除旧资料，只做仓库内可追溯归档；
- R0 未修改业务代码。

## 8. 阶段门禁

R0 文档工作完成后必须停止，并由用户完成简化版⑤拥有权验证：

1. 先阅读本阶段讲解；
2. 一次回答一道，共 3 道具体问题；
3. 不要求亲手修改代码或制造 Git diff；
4. 问答和必要纠错完成后，才把本文件的⑤改为“已完成”，并记录验收日期；
5. 即使⑤完成，仍需用户明确批准，才能开始 R1。

**下一阶段尚未开始。**
