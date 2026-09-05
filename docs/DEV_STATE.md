# Enterprise Knowledge Assistant 开发状态

> 本文件是阶段接手和决策账本，不是功能宣传页。能力是否已实现，必须以源码、测试和 Git 证据为准。

## 1. 当前状态

- 上位协议：`D:\AI_Internship_2026\求职材料\2026-09_双项目升级计划_评审版.md`
- 协议版本：**《2026 年 9 月 双项目升级执行协议 v6》定稿版**
- RAG 九月升级真实开工日期：**2026-08-31**（Australia/Sydney）
- 当前阶段：**R23 异步摄取最小完整闭环——实现与工程验收已于 2026-09-02 完成，⑤拥有权问答已于 2026-09-05 完成**
- 已正式完成阶段：R0、R1、R23
- 下一阶段：R4；**尚未开始**，必须由用户明确批准
- ⑤拥有权验证：R0 已完成（2026-08-31）；R1 已完成（2026-09-01）；R23 已完成（2026-09-05）
- 工作区基线：R0 开工时 `main` 与 `origin/main` 无领先/落后，HEAD 为 `11449b22e5df9181ecb7952f034da2f6b4875143`

## 2. R0 接手上下文

### R0 开工时生产代码能够证明的事实

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

## 5. R1 实施记录

### 已冻结的工程决策

| 决策 | R1 结论 | 边界与理由 |
| --- | --- | --- |
| Compose 拓扑 | FastAPI `api` + Qdrant `qdrant` 两个服务 | 形成一条可复现启动命令；Worker 尚未实现，不能称三服务 |
| SQLite/上传持久化 | `app_data` named volume | FastAPI 进入容器后，容器重建不能丢失 SQLite 和上传文件 |
| Qdrant 持久化 | `qdrant_data` named volume | collection、向量和 payload 独立于容器生命周期 |
| Qdrant 连接模式 | `RAG_QDRANT_URL` 与 Local path 二选一 | Compose 使用 Server；URL 为空时保留 V1 单进程 Local 兼容路径 |
| 对外端口 | 只绑定 `127.0.0.1` | 当前没有认证/TLS，不允许包装成公网部署能力 |
| Qdrant telemetry | Compose 中显式关闭 | 本地作品集不需要向外发送匿名使用统计 |
| 健康语义 | Qdrant 不可用时 API `/health` 返回 503 | 防止容器仍运行时把依赖故障误报成健康 |
| CI | 无 API Key 的 Qdrant Server service | 验证真实 Server 写入/检索/删除，同时不产生 Provider 费用 |

R1 没有修改现有生产 API：`POST /api/v1/documents` 仍同步完成摄取后返回
`201 Created`。没有新增 Job、Worker、异步接口、崩溃恢复或 Agent。

### 实际修改

- Server 连接与测试提交：`52585ce85ff02b4e348f4398f6982fb9b46147ef`；
- 两服务运行与 CI 提交：`00d8605fcf2fe15387aef6e27934b7df59454615`；
- `app/core/config.py`：增加类型化的 Qdrant Server URL、可选 API Key 和超时；密钥不进入 `repr`；
- `app/main.py`：根据 URL 是否存在装配 Qdrant Server 或 Local adapter；
- `app/storage/qdrant_vector_store.py`：同一存储端口支持互斥的 Local/Server 连接模式；
- `Dockerfile`、`.dockerignore`、`compose.yaml`：非 root API 镜像、两服务拓扑、健康检查和两个 named volume；
- `.github/workflows/ci.yml`：加入固定版本 Qdrant Server service；
- `tests/integration/test_qdrant_server.py`：真实 Server 临时 collection 往返和清理；
- `tests/unit/test_config.py`、`tests/unit/test_qdrant_vector_store.py`：配置、秘密隐藏、连接互斥和超时测试；
- `README.md`、`.env.example`、`requirements.txt`：运行边界、配置与兼容方式。

### 本次验证证据（2026-09-01）

- Docker Desktop 4.88.1 使用 WSL2 后端，`api` 与 `qdrant` 均达到 `healthy`；
- `/health` 正常时返回 200，组件包括 SQLite、Qdrant 和 Provider 配置状态；
- 临时停止 Qdrant 后 `/health` 返回 503 + `VECTOR_STORE_ERROR`，恢复后回到 200；
- Qdrant 容器重建后 `knowledge_chunks` collection 仍存在，验证 named volume 持久化；
- Qdrant 重建日志明确显示 `Telemetry reporting disabled`；
- 真实 Server 集成测试验证 upsert、文档范围检索、按文档删除及测试 collection 清理；
- 完整质量门禁：158 项测试通过、34 个参数化子测试通过、branch-aware 覆盖率 88.67%，Ruff、依赖、字节码与离线评测全部通过；
- 测试和离线评测未调用 OpenAI、DeepSeek 或其他真实 Provider。

### 本机 Docker 故障与数据边界

- 用户在故障排查前曾点过一次 Docker Desktop factory reset；随后只读盘点确认旧 Docker volume/容器为空，旧 named-volume 数据不能假定仍存在；
- 仓库宿主机 `data/app.db`、`data/qdrant` 与 `data/uploads` 未被 factory reset 删除；R1 没有直接迁移或删除这些 Local 数据；
- Docker 4.88.1 启动失败的直接原因是两个遗留 AF_UNIX socket 目录。采用可恢复的目录改名后启动成功，没有再次 factory reset；
- R1 新建 `enterprise-knowledge-assistant_app_data` 与 `enterprise-knowledge-assistant_qdrant_data`，R1 验收时两个服务均运行且健康；
- factory reset 或 `docker compose down --volumes` 会清空 named volume，README 已明确警告。

## 6. R23 已决问题与后续未决问题

R23 已通过源码和测试冻结：

1. Job 使用 `pending / running / ready / failed`，表随 `PRAGMA user_version=2` 兼容新增；V1 同步 `201` 保留，V2 异步接口使用 `/api/v2/documents` 和 `/api/v2/jobs/{job_id}`。
2. 唯一强制崩溃点是 Qdrant upsert 成功后、SQLite ready 事务前；测试用两个独立 Python 进程和真实 Qdrant Server 可重复验证。
3. SQLite 默认 `busy_timeout=5000 ms`，同时使用 WAL 和短事务。有限等待由 SQLite 内部完成，不叠加应用层事务重试；测试覆盖短锁释放后成功、锁超时安全失败和并发条件领取。
4. `IngestionProcessor` 只接收既有 `Document`，负责安全路径校验、parse/chunk/embed/upsert；V1 编排与 Worker 各自负责状态和补偿，避免复制两套处理算法。

后续仍未决：

1. R4：测量结果是否支持把异步接口作为演示主路径，还是只作为新增可选能力？
2. R5：到条件检查日时，前序质量和剩余时间是否允许启动协议设计？

## 7. 最容易误改或误报的位置

- `POST /api/v1/documents` 仍是同步 `201`；异步能力只在新增 V2 `202` 接口，不能把两者说成一次破坏性替换。
- `app/services/ingestion_service.py` 与 Worker 共用 `IngestionProcessor`，但状态编排不同；不能把 processing core 误说成任务队列。
- Qdrant Local 只供 V1 同步单进程开发和单进程测试；API + Worker 的真实双进程运行必须使用 Qdrant Server。
- Job 的 `ready` 和 Document 的 `ready` 在一个 SQLite 事务中提交；Qdrant 本身不参与事务，跨存储仍是补偿式一致性。
- 当前只按部署拓扑保证一个 Worker；不要启动第二个 Worker，也不要宣称已解决 Lease、Fencing、网络分区或旧 Worker 晚到写入。
- `processing` 文档删除固定返回 `409 DOCUMENT_PROCESSING`；P0 没有取消，不要顺手增加另一套状态转换。
- 归档里的 Agent API、Approval、Lease/Fencing 只是历史设计；R5 也只设计实验评测协议，不实现 Agent。

## 8. 环境与安全记录

- R0 未安装或升级依赖；
- R0 未启动 Docker 或 Qdrant；
- R0 未调用 OpenAI、DeepSeek 或其他真实 Provider；
- `.env` 仍只作为本地配置使用，不读取、不记录、不提交；
- R0 未删除旧资料，只做仓库内可追溯归档；
- R0 未修改业务代码。
- R1 只安装了构建镜像所需的公开依赖并拉取固定的 `qdrant/qdrant:v1.19.0` 镜像；
- R1 未读取、打印、修改或提交 `.env` 内容，启动日志检查未发现密钥；
- R1 未调用真实 Provider，也未执行付费评测；
- R1 没有删除 Docker volume、D 盘 Local 数据或恢复目录。
- R23 未安装或升级依赖，未读取、打印或修改 `.env`，全部新增测试使用 Fake/确定性 Provider；
- R23 没有调用 OpenAI、DeepSeek 或运行付费评测；
- 2026-09-02 Docker Desktop 再次受遗留 AF_UNIX socket 影响。只将当前 `run` 和 `docker-secrets-engine` 目录可恢复地改名，没有 factory reset、删除 volume 或清理镜像；
- 修复后 `enterprise-knowledge-assistant_app_data` 与 `enterprise-knowledge-assistant_qdrant_data` 均仍存在，API/Qdrant healthy、Worker Up。

## 9. 阶段门禁

R0 的简化版⑤拥有权验证已完成。用户能够区分：

- 归档用于保留旧方案的可追溯记录，同时取消其执行地位；
- 同步摄取等当前能力与异步摄取、Worker、Agent 等计划能力；
- R0 文档完成、⑤验证和下一阶段授权是三个不同门禁。

根据用户最新要求，后续问题以就业和面试价值为准：先讲本阶段知识点，再提出少量、与刚完成阶段直接相关的问题；不为凑数量设置低价值验证。

R1 的代码、运行、测试与知识问答已经完成。用户于 2026-09-01 明确要求取消以后各阶段的本人手动代码修改，只保留知识点和有就业价值的源码问题；该裁决已同步到 `docs/r_protocol.md`。

用户随后明确指示“继续下个阶段”，因此 R23 获得启动授权。R23 完成后仍必须停止，⑤状态保持“未完成”，直到知识讲解与高价值问题验收结束；R4 不得提前开始。

R23 的实现、完整工程测试和事实文档已于 2026-09-02 完成。用户于 2026-09-05 完成⑤问答，能够说明独立 Worker 与 `run_in_threadpool()` 的边界、固定崩溃点后的恢复步骤，以及 WAL、`busy_timeout`、短事务和条件领取各自解决的问题。纠错补充强调：V1 同步接口继续保留并与 Worker 共用 `IngestionProcessor`；当前机制不包含 Lease/Fencing，不能宣称支持多 Worker、旧 Worker 晚到竞争或网络分区。R23 阶段门禁至此关闭；R4 仍必须等待用户明确的新阶段指令。

## 10. R23 实现前设计冻结（2026-09-01）

- 兼容 API：V1 同步 `201` 保留；V2 异步 `202` 返回 `document_id + job_id`；
- Job 状态：`pending / running / ready / failed`；Document 继续使用 `processing / ready / failed`；
- SQLite：兼容新增 Job 表，启用 WAL、默认 5000 ms `busy_timeout` 和短事务；
- Worker：单机单 Worker、原子领取；启动时把遗留 `running` 恢复为 `pending`；
- 共享核心：V1 与 Worker 复用既有 Document 的 parse/chunk/embed/upsert 流程；
- 崩溃点：Qdrant upsert 成功后、SQLite 终态提交前强制结束 Worker；
- 恢复幂等：重放前按 `document_id` 清理残留 Point；不声称处理仍存活旧 Worker；
- 删除语义：Document 为 `processing` 时返回 `409 DOCUMENT_PROCESSING`，P0 不提供取消；
- 详细契约和验收证据：`docs/r23_design.md`；实现、测试与边界现已互相映射。

## 11. R23 实施与验证记录（2026-09-02）

### 当前新增能力

- 保留 V1 同步 `POST /api/v1/documents → 201`；
- 新增 V2 `POST /api/v2/documents → 202`，返回 `document_id`、`job_id` 和 `status_url`；
- 新增 `GET /api/v2/jobs/{job_id}`，只暴露稳定状态、时间戳、尝试次数和安全错误码；
- 独立 `python -m app.worker` 进程原子领取持久化 Job，并推进 Job/Document 状态；
- Worker 启动时把遗留 `running` Job 恢复到 `pending`，重放前按 `document_id` 清理残留向量；
- 活动摄取文档删除返回 `409 DOCUMENT_PROCESSING`；终态文档沿用 V1 文件、向量、SQLite 删除编排；
- Compose 已从 R1 的 API + Qdrant 扩展为 API + Worker + Qdrant 三服务。

### 数据与状态证据

- SQLite schema 版本：2；新增 `ingestion_jobs`，一个 Document 最多关联一个 Job；
- Job：`pending → running → ready/failed`，Worker 进程消失时下次启动执行 `running → pending`；
- Document：`processing → ready/failed`；
- 领取使用 `BEGIN IMMEDIATE` + 条件更新，`attempt_count` 每次真实领取增加；
- Job/Document 成功或失败终态在同一 SQLite 短事务更新；
- WAL、默认 5000 ms `busy_timeout` 和短事务构成当前双进程 SQLite 并发策略。

### 故障与恢复证据

- 固定崩溃点：Qdrant upsert 成功后、SQLite ready 提交前，测试进程以退出码 91 结束；
- 第二个独立进程启动后恢复同一 Job，最终 `attempt_count=2`、Document/Job 都为 ready，Qdrant 没有重复可见 Chunk；
- Qdrant 部分写入后抛错会触发向量/文件补偿并把两个业务对象共同置为 failed；
- SQLite ready 提交结果不确定时先回读：确认 ready 则保留数据，否则 Worker 退出并走启动恢复，避免误删已经成功的数据；
- 失败状态无法写入时 Worker 也退出，避免一个 live Worker 永久遗留 running Job。

### 最终质量结果

- 完整质量门禁：182 项自动化测试通过、34 个参数化子测试通过；
- branch-aware 覆盖率：87.59%，门槛 85%；
- Ruff lint/format、依赖、字节码和固定离线评测通过；
- 离线评测仍为 10 份合成文档、50 道题，指标口径与 R1 前一致；
- 真实 Qdrant Server 测试只验证存储和进程边界，Embedding/LLM 仍使用 Fake/确定性 Provider，无付费调用。

### 已知边界

- 不支持取消、Idempotency-Key、业务自动重试队列、背压或长期 reconciler；
- 不支持多 Worker、Lease/Fencing、旧 Worker 晚到竞争或网络分区；
- 处理失败会清理源文件，P0 没有失败 Job 重试接口；
- R4 尚未实测同步/异步延迟与复杂度，因此不能提前宣称异步“更快”或已经取代同步主路径；
- Agent 未实现；R5 尚未开始。
