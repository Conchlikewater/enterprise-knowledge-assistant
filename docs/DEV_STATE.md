# Enterprise Knowledge Assistant 开发状态

> 本文件是阶段接手和决策账本，不是功能宣传页。能力是否已实现，必须以源码、测试和 Git 证据为准。

## 1. 当前状态

- 上位协议：`D:\AI_Internship_2026\求职材料\2026-09_双项目升级计划_评审版.md`
- 协议版本：**《2026 年 9 月 双项目升级执行协议 v6》定稿版**
- RAG 九月升级真实开工日期：**2026-08-31**（Australia/Sydney）
- 当前阶段：**R6 受限路由 Agent——实现、首次冻结评测和本地质量门禁已完成，⑤拥有权验证待完成**
- 已正式完成阶段：R0、R1、R23、R4、R5
- 下一阶段：R6 完成、评测和⑤验证后才可由用户另行批准 R7；**R7 当前未开始**
- ⑤拥有权验证：R0 已完成（2026-08-31）；R1 已完成（2026-09-01）；R23 已完成（2026-09-05）；R4 由用户在阅读完整参考答案后明确授权关闭并进入 R5（不记为独立作答）；R5 由用户在阅读完整参考答案后明确授权收口（2026-09-06，不记为独立作答）；R6 未完成
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
| Agent 定位 | R5 是协议；R6 后续获准实现受限路由控制器 | 不能把三分类路由和一次重试包装成通用 Agent；R7 图检索仍未开始 |
| R23 P0 | 单机、单 Worker 最小闭环 | 证明真正异步、状态、崩溃恢复和一致性，不扩成分布式队列 |
| 删除—摄取竞态 | 活动 Job 时返回 `409 DOCUMENT_PROCESSING` | 不引入取消，形成最小、明确、可测试的竞态语义 |
| 多 Worker 可靠性 | Lease/Fencing 等延期 | 单 Worker P0 不解决网络分区或旧 Worker 晚到竞争 |
| R4 结论 | V2 作为长耗时摄取演示首选，V1 保留兼容 | 异步更快返回并支持恢复，但本次端到端更慢；只作作品集演示决策 |
| R5 公平对照 | Dense Top-5 / Dense Top-10 / Agentic 5×2 | Top-10 控制“多取证据”的混杂因素；R5 只冻结协议，不产生 Agent 结果 |

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

R5 入口已经解决：用户在 2026-09-05 明确要求给出 R4 完整参考答案后开始下一阶段。该授权提前于 v6 的名义日历检查点，但 R0、R1、R23、R4 技术阶段及 CI 均已通过；因此只提前启动条件 R5 的协议设计，范围没有扩大。

R23 收口时仍未决、现已部分推进：

1. R6 已用独立 36 条路由样例和 12 条重试样例完成冻结边界评测；它没有复用当前 50 道 RAG 题，也没有执行 R5 Agentic 5×2。R7 的学校语料、50 题、Evidence 与图路径标注仍未开始。
2. 真实 Provider、模型和预算必须在未来实验运行前单独申请；R5 不运行真实模型。

## 7. 最容易误改或误报的位置

- `POST /api/v1/documents` 仍是同步 `201`；异步能力只在新增 V2 `202` 接口，不能把两者说成一次破坏性替换。
- `app/services/ingestion_service.py` 与 Worker 共用 `IngestionProcessor`，但状态编排不同；不能把 processing core 误说成任务队列。
- Qdrant Local 只供 V1 同步单进程开发和单进程测试；API + Worker 的真实双进程运行必须使用 Qdrant Server。
- Job 的 `ready` 和 Document 的 `ready` 在一个 SQLite 事务中提交；Qdrant 本身不参与事务，跨存储仍是补偿式一致性。
- 当前只按部署拓扑保证一个 Worker；不要启动第二个 Worker，也不要宣称已解决 Lease、Fencing、网络分区或旧 Worker 晚到写入。
- `processing` 文档删除固定返回 `409 DOCUMENT_PROCESSING`；P0 没有取消，不要顺手增加另一套状态转换。
- 归档里的 Investigation、Approval、Lease/Fencing 仍只是历史设计；R6 新增的只有 V2 Answer 受限路由和一次检索重试，不能从中恢复或推导那些旧能力。

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
- 2026-09-05 R4 前 Docker Desktop 再次被两个串联的遗留 AF_UNIX socket 阻塞；只停止失败进程并可恢复改名对应运行目录，没有再次 factory reset；
- Docker Engine 29.7.2 恢复后只读确认两个 named volume、镜像和容器仍存在。当前 SQLite 为 0 Document / 0 Job，Qdrant `knowledge_chunks` 为 0 Point，二者是一致的空基线；无法倒推 Reset 前是否曾有数据。
- R4 使用确定性 Fake Embedding 和本机 Qdrant Server，没有读取 `.env`、调用真实 Provider 或产生 API 费用；临时 collection 已清理。
- R5 没有启动 Docker、读取 `.env`、安装依赖或调用真实 Provider；只新增协议、机器清单、离线契约测试和事实文档。
- R6 没有启动 Docker、安装依赖、读取 `.env` 或调用真实 Provider；路由与重试评测全部使用确定性规则和 Fake/探针，报告中的网络、Embedding、LLM 调用与费用均为 0。

## 9. 阶段门禁

R0 的简化版⑤拥有权验证已完成。用户能够区分：

- 归档用于保留旧方案的可追溯记录，同时取消其执行地位；
- 同步摄取等当前能力与异步摄取、Worker、Agent 等计划能力；
- R0 文档完成、⑤验证和下一阶段授权是三个不同门禁。

根据用户最新要求，后续问题以就业和面试价值为准：先讲本阶段知识点，再提出少量、与刚完成阶段直接相关的问题；不为凑数量设置低价值验证。

R1 的代码、运行、测试与知识问答已经完成。用户于 2026-09-01 明确要求取消以后各阶段的本人手动代码修改，只保留知识点和有就业价值的源码问题；该裁决已同步到 `docs/r_protocol.md`。

用户随后明确指示“继续下个阶段”，因此 R23 获得启动授权。R23 完成后仍必须停止，⑤状态保持“未完成”，直到知识讲解与高价值问题验收结束；R4 不得提前开始。

R23 的实现、完整工程测试和事实文档已于 2026-09-02 完成。用户于 2026-09-05 完成⑤问答，能够说明独立 Worker 与 `run_in_threadpool()` 的边界、固定崩溃点后的恢复步骤，以及 WAL、`busy_timeout`、短事务和条件领取各自解决的问题。纠错补充强调：V1 同步接口继续保留并与 Worker 共用 `IngestionProcessor`；当前机制不包含 Lease/Fencing，不能宣称支持多 Worker、旧 Worker 晚到竞争或网络分区。R23 阶段门禁至此关闭；R4 仍必须等待用户明确的新阶段指令。

R4 的协议、基准实现、正式实测和完整质量验证已完成。用户于 2026-09-05 要求直接查看三道题的完整参考答案并开始下一阶段；因此 R4 阶段按用户明确裁决关闭，但这只代表学习交接与阶段转换完成，不声称用户已经独立、无提示回答这些问题。

同日用户明确授权开始下一阶段。R5 只做协议设计；工程交付完成时按阶段规则先将⑤设为“未完成”并停止，R6/R7 不得顺手启动。

2026-09-06，用户要求直接查看 R5 三道题的完整参考答案后继续。参考答案覆盖 Top-10 控制组的归因作用、Jaccard/替换率计算与解释，以及空结果、未授权工具、超轮次和无证据总结的失败分类。R5 学习交接据此关闭，但不记录为用户独立、无提示作答；“继续”只用于阶段状态和 Git 收口，不视为 R6/R7 的范围授权。

2026-09-07，用户在完成一轮设计排查后明确授权启动 R6，并确认 R6、R7 分阶段验收。该新裁决晚于上一段：R6 现已获准；R7 仍必须等待 R6 实现、测试、独立评测和拥有权验证全部完成后再单独批准。

R6 的实现、首次冻结评测和本地完整质量门禁已完成，工程门槛通过；⑤仍标记为“未完成”。必须先完成本阶段知识讲解与就业导向问题，再由用户明确批准，才能开始 R7。当前没有收集学校语料、编写 R7 的 50 题或实现图检索。

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
- 在 R23 验收当时，R4 尚未实测同步/异步延迟与复杂度，因此当时不能提前宣称异步“更快”或已经取代同步主路径；后续 R4 结果见第 13 节；
- 在 R23 验收当时，Agent 未实现且 R5 尚未开始；R5 后续仍只设计协议，不改变“Agent 未实现”的事实。

## 12. R4 预注册（2026-09-05）

- 用户明确指示继续下一阶段，R4 获得启动授权；
- 测量协议：`docs/r4_evaluation_protocol.md`；协议先于基准实现和实验结果提交；
- 固定比较 API 接收延迟、端到端完成时间、处理期间健康响应、连续上传、崩溃恢复、100 ms 受控请求预算和复杂度七项；
- 同步和异步使用对应一致的 8 KiB 合成 TXT、`1000/150` Chunk、固定 200 ms 延迟的 3 维确定性 Embedding 与同一 Qdrant Server；数据库和 collection 隔离；
- 正式基准使用 FastAPI ASGI 应用层请求和独立 Python Worker 子进程，不调用真实 Provider；
- 结论只能决定作品集“长耗时摄取演示首选路径”，不会删除 V1、修改生产 API 或声称生产吞吐；
- 本节记录预注册时点，当时尚未运行正式实验；结果见下一节，判断规则没有事后修改；
- 本节是 R4 预注册时点记录：当时 R5、R6、R7、R8 和 R2.5 均未开始。

## 13. R4 实施、实测与验证（2026-09-05）

### 实验结果

- 正式报告：`evaluation/ingestion_benchmark_report.json`；分析：`docs/r4_sync_async_evaluation.md`；
- 单次 API 接收 P95：同步 340.65 ms，异步 49.32 ms，异步低 85.52%；
- 单次端到端 P95：同步 340.65 ms，异步 775.81 ms，异步约为 2.28 倍；
- 连续 5 份全部响应 P95：同步 1559.06 ms，异步 121.00 ms；
- 连续 5 份全部 ready P95：同步 1559.06 ms，异步 3192.49 ms；
- 处理期间 `/health` P95：同步 23.08 ms，异步 23.43 ms，双方 5/5 均为 200；
- 异步固定崩溃点恢复通过：2645.38 ms、`attempt_count=2`、11 个可见 Chunk 无重复；同步 V1 没有持久化 Job，记为不支持/不适用；
- 预注册判断条件全部满足，因此只建议 V2 作为长耗时摄取的作品集演示首选，V1 继续兼容；不宣称异步端到端更快或已经生产验证。

### 实现与排障证据

- 基准在隔离 SQLite、上传目录和临时 Qdrant collection 中运行；使用 ASGI 应用层请求和独立 Python Worker 子进程；
- 第一次正式运行因长驻 Worker stdout 的未消费 PIPE 写满而超时，该运行无效且没有生成报告；
- 修复改为临时日志文件并新增回归测试，没有放宽 60 秒超时；修复提交 `c5faa054b93e8053a1f0f3c62347dd95da7af8a3`；
- GitHub Actions `33946956840` 通过：191 tests + 34 subtests、branch-aware coverage 87.59%、Ruff、依赖、字节码和离线评测全部通过；
- 加入两条机器报告与文档一致性测试后，最终完整门禁为 193 tests + 34 subtests；
- 真实 Provider 未调用；本机 100 ms 边界不是 SLA，3 轮连续上传不是并发压测。

### 学习交接与阶段转换

- R4 三道题的完整参考答案已提供，覆盖演示路径选择、连续上传的排队含义和长驻 Worker `PIPE` 死锁；
- 用户选择参考答案学习方式并明确要求开始下一阶段。R4 据此关闭，但不记录为独立作答通过；
- R6、R7、R8 和 R2.5 不属于九月主分支承诺范围。

## 14. R5 协议设计与验证（2026-09-05）

### 启动裁决

- R0、R1、R23、R4 的工程交付与远端 CI 已通过；
- 用户在阅读 R4 完整参考答案后明确要求开始下一阶段，授权提前于 v6 的 9 月 26 日名义检查点；
- 提前只影响开始日期，不改变 R5 条件加注、协议-only、无 Agent 实现的边界。

### 本阶段交付

- `docs/r5_agentic_retrieval_evaluation_protocol.md`：三组对照、公平性、轨迹、排序去重、失败分类、对抗场景、指标和未来执行门禁；
- `evaluation/agentic_retrieval_protocol.json`：机器可校验的协议不变量，显式记录 `agent_implemented=false`、`experiment_executed=false`；
- `tests/evaluation/test_agentic_retrieval_protocol.py`：验证三组预算、协议边界、轨迹/失败分类以及当前 10 文档/50 题事实；
- README 与 evaluation README：显眼区分“设计了 Agent 评测协议”和“实现/运行了 Agent”。

### 冻结的实验口径

- 三组必须同时存在：Dense Top-5、Dense Top-10、Agentic 5×2；
- Agentic 整个问题最多两次检索、每次最多 5 条、总返回预算 10；重复项不补抽第三次；
- 三组固定同一文档、题目、Embedding、最终生成模型、温度、最终回答 Prompt 和 Evidence 格式；规划 Prompt 允许不同但必须版本化并计入 Agent 成本；
- 第二轮同时报告 Jaccard、替换率和新增 gold Evidence，不能把预算增加全部归因于策略；
- 当前 50 道题缺少第二轮、停止原因和 Agent failure gold，只有候选来源地位；R5 没有创建或声称已冻结 Agent 题集。

### 本地验证

- R5 协议定点测试：5 项通过；
- 完整离线质量门禁：195 项通过、3 个需要 Qdrant Server 的测试按环境跳过、34 个参数化子测试通过；
- branch-aware 覆盖率：87.59%，门槛 85%；
- Ruff lint/format、依赖、字节码和固定 10 文档/50 题离线评测通过；
- 初次运行暴露本机系统临时目录和旧 `__pycache__` 的 Windows ACL 问题；把 Pytest 临时根目录和 Python bytecode cache 定向到 Git 忽略的隔离目录后，同一源码与断言完整通过，没有删除旧缓存或放宽门槛；
- GitHub Actions `33970197146` 通过：198 项测试、34 个参数化子测试、branch-aware coverage 87.59%、Ruff、依赖、字节码和离线评测全部通过；CI 的无 API Key Qdrant Server 覆盖了本地跳过的 3 项。

### 阶段收口

- R5 工程协议、质量验证和参考答案学习交接均已完成，阶段关闭；
- 没有 Agent 实现、固定轨迹回放、Agent 实验数据或真实 Provider 结果；
- 本节描述 R5 关闭时的历史状态；R6 后续于 2026-09-07 获得窄范围补充授权并实施，见第 15、16 节。R7 仍未开始。

## 15. R6 启动与实现前冻结（2026-09-07，历史时点）

### 补充授权

- R6：三分类 `retrieve / direct_answer / refuse`，允许 Evidence 不足时做一次查询改写和一次额外 Dense 检索；
- `direct_answer` 只处理问候、系统能力和使用方法，事实问题不得绕开 Evidence；
- 使用基础控制流，不引入 LangGraph、Memory、Multi-Agent 或多轮循环；
- R7 的学校公开语料、冻结 50 题、Property Graph 和 Graph+Dense 实验必须等待 R6 验收后另行启动；
- 真实 Provider 调用前仍须提交调用量、token 上限和预算并获得批准。

### 实现前冻结工件

- `docs/r6_routing_agent_design.md`：API 兼容、路由顺序、一次重试、停止原因、测试和阶段门禁；
- `evaluation/r6_routing_protocol.json`：机器可校验的边界、指标和通过阈值；
- `evaluation/r6_routing_questions.json`：独立 36 题三分类冻结集，每类 12 题；
- `evaluation/r6_retry_cases.json`：12 个证据充分性和重试判定案例；
- `tests/evaluation/test_r6_routing_protocol.py`：验证冻结状态、文件哈希、类别平衡、预算和安全门槛。

### 当前状态

- 本节只记录预注册时点：当时生产路由代码尚未开始；
- 当时 R6 评测尚未执行，没有结果结论；
- 没有调用真实 Provider，也没有产生费用；
- R7 尚未开始。

## 16. R6 实现、首次评测与工程收口（2026-09-07）

### 当前新增能力

- 保留 `POST /api/v1/answers` 的单轮 Dense 行为与响应契约；
- 新增 `POST /api/v2/answers`，返回 answer/citations 以及 `route`、
  `route_reason`、`retrieval_attempts`、`rewritten_query`、`stop_reason`；
- 路由顺序固定为高置信拒答、直接回答白名单、其他默认检索；
- `direct_answer` 只使用固定模板处理问候、能力与使用帮助，不调用 LLM；
- 事实问题没有 document scope 时拒答；有 scope 时最多两次 Dense 检索，第二次
  只允许一次确定性查询改写，且 `document_ids` 不变；
- Evidence 充分后复用 `AnswerService.answer_from_evidence()` 生成，避免再次隐式检索。

### 实现与提交证据

- `7e0f895`：实现前设计、36 条路由题、12 条重试题、SHA256 和门槛冻结；
- `d0ebcea`：领域模型、规则路由、改写、证据充分性、V2 Router/Schema、服务编排
  及单元/集成测试；
- `238370e`：冻结评测计算器与命令入口；
- `fed96d7`：首次正式报告与报告完整性测试；
- 关键类：`RuleBasedQuestionRouter`、`RuleBasedQueryRewriter`、
  `EvidenceSufficiencyPolicy`、`RoutedAnswerService`。

### 首次冻结评测

- `evaluation/r6_routing_report.json` 绑定两个预注册文件哈希和被测提交；
- 路由 36/36，accuracy 100%，macro F1 1.0000；
- 重试 12/12，accuracy、正类 precision 和 recall 均为 100%；
- 事实问题误走直接回答、超过两次检索、文档范围越界均为 0；
- 网络、Embedding、LLM 调用、router token 和估算费用均为 0；
- 该 100% 只适用于小型人工边界 fixture，不代表开放域泛化、真实学校文档效果
  或生产 Agent 能力。

### 本地质量与当前门禁

- 定点实现测试：39 项通过、31 个参数化子测试通过；
- R6 协议、评测工具与报告完整性定点测试：14 项通过；
- 完整本地质量门禁：240 项通过、3 项 Qdrant Server 条件测试按当前环境跳过、
  65 个参数化子测试通过；branch-aware 覆盖率 88.90%，门槛 85%；
- Ruff lint/format、依赖、字节码和原有 10 文档/50 题离线评测均通过；
- ⑤拥有权验证仍未完成；R7 尚未开始，也未获得本轮自动启动授权。
