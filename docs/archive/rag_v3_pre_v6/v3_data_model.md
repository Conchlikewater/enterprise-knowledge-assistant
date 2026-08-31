# V3 P0 数据模型

> 状态：范围对齐修订完成，等待阶段 0 最终验收；尚未实现。
> 目标：只定义单机单 Worker 异步摄取和两轮 Investigation 所需的最小数据，不设计审批、归档、多租户或分布式 Worker。

## 1. 存储职责

- **SQLite**：Document、Idempotency、IngestionJob、Investigation、Evidence、Citation 和轨迹的业务真相源；
- **Qdrant Server**：可由原文件和 SQLite 状态重建的 Chunk、向量与来源 metadata；
- **文件系统**：上传临时文件、规范原文件和 Worker 进程锁文件；
- **轨迹/Checkpoint**：执行恢复与离线回放材料，不覆盖 SQLite 终态。

所有时间保存为 UTC。SQLite 每个连接必须启用外键；写入使用 WAL、短事务和有上限的锁重试。

## 2. Schema 版本

### `schema_migrations`

| 字段 | 约束 | 含义 |
| --- | --- | --- |
| `version` | PK | 单调递增版本 |
| `name` | NOT NULL | 迁移名称 |
| `applied_at` | NOT NULL | UTC 时间 |

计划迁移：

1. 识别并保留 V1 schema 与数据；
2. 扩展 Document 状态并增加 Idempotency/Job；
3. 增加 Investigation、范围、子问题、Evidence、Citation 和 Trace；
4. 迁移在临时数据库演练，校验行数、唯一约束和回滚路径。

P0 不移除 `sha256 UNIQUE`，也不增加 Lease、Heartbeat、Generation、Approval 或 Draft 表。

## 3. 文档与摄取

### `documents`

保留现有字段并增加必要字段：

| 字段 | 约束 | 含义 |
| --- | --- | --- |
| `document_id` | PK | Document UUID |
| `filename` | NOT NULL | 安全展示文件名 |
| `media_type` | NOT NULL | 规范媒体类型 |
| `size_bytes` | `>= 0` | 文件大小 |
| `sha256` | NOT NULL, UNIQUE | 内容 SHA-256 |
| `status` | CHECK | processing/ready/failed/deleting/deleted |
| `chunk_count` | `>= 0` | ready 时可见 Chunk 数 |
| `stored_path` | NOT NULL | 内部规范路径，不向 API 暴露 |
| `error_code/error_summary` | NULL | 稳定错误与安全摘要 |
| `created_at/updated_at` | NOT NULL | UTC 时间 |
| `deleted_at` | NULL/UTC | 删除墓碑时间 |

不变量：

- 只有 ready Document 可检索；
- ready 时文件存在且 `chunk_count` 与 Qdrant 可见 Point 数一致；
- processing 时 Qdrant 即使存在部分 Point，也不能通过业务检索访问；
- failed 前已经完成不完整文件和 Qdrant 残留补偿；
- deleted 不复用 Document ID。

索引：`sha256 UNIQUE`、`status`。

### `idempotency_keys`

| 字段 | 约束 | 含义 |
| --- | --- | --- |
| `key_hash` | PK | Idempotency-Key 的 SHA-256，不保存原 Key |
| `file_sha256` | NOT NULL | 上传内容摘要 |
| `media_type` | NOT NULL | 规范媒体类型 |
| `size_bytes` | NOT NULL | 文件大小 |
| `document_id` | FK, NOT NULL | 绑定 Document |
| `job_id` | FK, NOT NULL | 绑定首次 Job |
| `created_at` | NOT NULL | UTC 时间 |

同 Key 通过完整文件指纹区分安全重放和冲突。不同 Key 的相同 SHA 由 Document 唯一约束拒绝。

### `ingestion_jobs`

| 字段 | 约束 | 含义 |
| --- | --- | --- |
| `job_id` | PK | Job UUID |
| `document_id` | FK, NOT NULL | 所属 Document |
| `status` | CHECK | staging/queued/processing/succeeded/failed |
| `attempt` | `>= 0` | 原子领取次数 |
| `max_attempts` | `> 0` | 受控自动重试上限 |
| `current_step` | NULL/CHECK | parse/chunk/embed/qdrant/commit/cleanup |
| `error_code/error_summary` | NULL | 安全错误信息 |
| `staging_path` | NULL | 恢复器内部使用，不向外暴露 |
| `created_at/started_at/finished_at/updated_at` | UTC | 生命周期时间 |

索引与约束：

- `(status, created_at)` 支持领取；
- `(document_id, created_at)` 支持历史查询；
- partial unique index 保证每个 Document 最多一个 staging/queued/processing Job；
- succeeded/failed 为终态；显式 retry 创建新 Job；
- P0 不包含 owner、token、Lease、Heartbeat、Generation 或 cancel 字段。

## 4. Worker 进程互斥

进程互斥使用共享数据目录中的独占 OS 文件锁，不使用带过期时间的数据库 Lease。锁文件只保存非敏感诊断标识，不作为业务状态，也不进入 API。

规则：

1. Worker 在恢复和轮询前取得锁；
2. 取得失败立即退出，不启动第二任务循环；
3. OS 在进程退出或崩溃时释放锁；
4. 只有持锁 Worker 可以恢复遗留 processing Job；
5. 不支持网络文件系统、多主机或网络分区。

Windows 本地开发与 Linux 容器需要分别验证锁语义。若跨平台实现需要新依赖，必须在阶段 2 前说明并获得安装批准。

## 5. Qdrant Point 契约

每个 Point 至少保存：

```text
chunk_id
document_id
global_chunk_index
page_number
filename
text
chunk_content_sha256
chunker_version
chunker_config_hash
```

Point ID 使用 UUIDv5：

```text
document_id
+ chunker_version
+ chunker_config_hash
+ page_number
+ global_chunk_index
+ chunk_content_sha256
```

清理至少支持按 `document_id` 删除全部 Point。由于 P0 只有一个 Worker且 Document=processing 不可检索，恢复遗留任务前可以安全删除该 Document 的部分 Point，再完整重放。

## 6. 事务边界

### 6.1 上传事务

SQLite 在一个短事务中创建 Idempotency、Document(processing) 和 Job(staging)。文件写入、哈希计算与原子重命名不在数据库事务内。重命名成功后使用条件更新把 staging 改为 queued。

### 6.2 原子 claim

一个短写事务执行等价条件更新：

```text
UPDATE ingestion_jobs
SET status='processing', attempt=attempt+1, started_at=?, updated_at=?
WHERE job_id=? AND status='queued'
```

影响 1 行才领取成功；0 行表示已被处理或状态变化。单 Worker锁是第一层，条件更新是防止恢复器和任务循环逻辑重入的第二层。

### 6.3 完成提交

Qdrant 全部写入并核对 Chunk 数后，在一个短事务中条件检查 Job=processing、Document=processing，然后同时提交：

```text
Job -> succeeded
Document -> ready
Document.chunk_count -> 实际写入数
```

事务失败时 Document 仍不可检索；Worker 进入补偿或安全重放。

### 6.4 失败补偿

解析、Embedding 或 Qdrant 发生永久失败/重试耗尽时：

1. 在事务外幂等删除该 Document 的 Qdrant Point 和不完整文件；
2. 清理失败可保留 processing 并记录内部步骤，由唯一 Worker 下次恢复；
3. 清理成功后在短事务中提交 Job=failed、Document=failed；
4. 错误摘要不得包含路径、原文、Key 或第三方响应正文。

## 7. SQLite 并发配置契约

每个连接：

```text
PRAGMA foreign_keys = ON
PRAGMA journal_mode = WAL
PRAGMA busy_timeout = 1000
```

写操作规则：

- 不在事务内调用文件解析、Embedding、Qdrant 或 LLM；
- 只对可识别的 SQLite locked/busy 错误重试；
- 首次失败后最多重试 2 次，退避为 50ms、150ms；
- 唯一约束、状态冲突和业务校验错误不重试；
- API 超过上限返回 `503 DATABASE_BUSY`；
- Worker 超过上限停止任务循环并退出，不继续外部副作用；下一唯一 Worker恢复遗留任务；
- 阶段 2 fixture 若证明默认值不合适，必须先修改 ADR 和配置版本，不能静默调参。

## 8. Investigation 数据

### `investigations`

| 字段 | 约束 | 含义 |
| --- | --- | --- |
| `investigation_id` | PK | Investigation UUID |
| `question` | NOT NULL | 规范化问题 |
| `status` | CHECK | created/running/needs_clarification/completed/failed |
| `state_version` | `>= 1` | 澄清和恢复的乐观并发版本 |
| `rounds_used` | `0..2` | 全局检索轮次 |
| `unique_candidate_count` | `0..10` | 接纳的去重候选总数 |
| `coverage` | NULL 或 `0..1` | 决策内核覆盖率 |
| `stop_reason` | NULL/CHECK | 决策契约停止原因 |
| `response_label` | NULL/CHECK | answer/refusal |
| `clarification_request` | NULL | 安全澄清提示 |
| `result_json` | NULL | completed 时的结构化报告结果 |
| `decision_config_version` | NOT NULL | 纯函数配置版本 |
| `prompt_versions_json` | NOT NULL | 规划/查询/最终回答 Prompt 版本 |
| `error_code/error_summary` | NULL | failed 安全错误 |
| `created_at/updated_at/finished_at` | UTC | 生命周期时间 |

completed/failed 是终态。调查报告保存在 `result_json` 中，是任务结果，不是审批后的正式归档对象。

### `investigation_documents`

复合主键 `(investigation_id, document_id)`。创建时只允许 ready Document；它是所有检索工具的唯一范围。活跃状态用于阻止 Document 删除。

### `investigation_subquestions`

| 字段 | 含义 |
| --- | --- |
| `subquestion_id` | 稳定 ID |
| `investigation_id` | 所属任务 |
| `text` | 规范化子问题 |
| `required` | 是否必须覆盖 |
| `order_index` | 展示和重放顺序 |

### `investigation_evidence`

保存 investigation/subquestion、round、document/chunk ID、页码、文件名、检索分数、内容哈希、短 Evidence 摘要、是否被接纳及拒绝原因。唯一约束防止同一 Investigation 重复接纳同一 Chunk。

不在普通 Trace 中保存完整私密 Chunk；需要生成时通过受控 Citation/Chunk读取接口取得。

### `investigation_citations`

保存 claim ID、document/chunk ID、文件名、页码、内容哈希和必要的短快照。Document 删除后记录仍可保留，但查询结果标记 `source_available=false`。这不等同于合规归档。

### `investigation_traces`

append-only 保存事件序号、节点/工具、输入输出摘要哈希、范围、候选 ID、轮次、纯函数决定、Provider/模型、Prompt 版本、token、估算成本、延迟、状态和安全错误。

轨迹可序列化为固定 fixture，在 CI 中不调用真实 Provider地回放。Repository 不提供修改历史事件正文的业务方法，但不宣称密码学不可篡改。

## 9. P0 明确不存在的表与字段

P0 不建立：

- Draft、Approval、正式 Archive/Report 独立业务表；
- 审批凭据和 approver 身份字段；
- cancel 请求或 cancelled 状态字段；
- Worker owner/token/Lease/Heartbeat/Generation/Fencing 字段；
- 用户、租户、RBAC、Redis 队列或监控平台表。

对应设计全部进入 `PARKING_LOT.md`，不能被实现顺手加入。

## 10. 核心不变量

1. 相同 SHA 不创建第二个 Document；
2. 同一 Document 最多一个活跃 Job；
3. 同一主机只运行一个异步 Worker；
4. 只有 ready Document 可检索；
5. processing Document 可按 ID 清理残留，但不能对用户可见；
6. Job succeeded 与 Document ready/chunk count 同事务提交；
7. failed 表示补偿已经完成；
8. processing/活跃 Job 删除返回 409，不能隐式取消；
9. Investigation 只能使用创建时锁定的 document IDs；
10. 每个 Investigation 最多两轮、每轮最多 5 个接纳候选、总数最多 10；
11. completed/failed 不能被旧轨迹重新打开；
12. 轨迹和结果不得泄露密钥、路径、完整 Prompt 或完整私密原文。
