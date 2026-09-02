# R23 异步摄取最小完整设计

> 状态：2026-09-02 已按本设计完成实现和工程验收；⑤拥有权验证仍未完成，R4 尚未开始。能力边界以本文件、源码、测试和 Git 证据共同为准。

## 1. 范围与兼容边界

R23 只完成 v6 定义的最小闭环：

- 保留 `POST /api/v1/documents` 同步摄取和 `201 Created`；
- 新增 `POST /api/v2/documents`，只完成文件校验、落盘及 Document/Job 创建，返回 `202 Accepted`；
- 新增 Job 状态查询；
- 使用一个独立 Python Worker 进程处理持久化 Job；
- 明确定义一个 Worker 崩溃点，并验证重启后恢复；
- Compose 从 R1 两服务扩展为 API + Worker + Qdrant 三服务。

R23 不实现取消、自动业务重试、Idempotency-Key、Redis/Celery、多 Worker、Lease/Fencing、网络分区处理或 Agent。重复文件继续沿用现有 `sha256 UNIQUE`，返回 409。

## 2. API 契约

### `POST /api/v2/documents`

- 请求：与 V1 相同的 TXT/PDF multipart 文件；
- 成功：`202 Accepted`；
- 返回：`document_id`、`job_id`、`document_status=processing`、`job_status=pending`、相对 `status_url`；
- API 返回前只做有界文件保存和一个短 SQLite 事务，不执行解析、Chunk、Embedding 或 Qdrant 写入；
- 文件保存后若数据库事务失败，API 删除本次文件；同 SHA 冲突继续返回 `409 DOCUMENT_CONFLICT`。

### `GET /api/v2/jobs/{job_id}`

返回 Job 的公开状态、尝试次数和时间戳。失败时只返回稳定 `error_code`，不返回异常文本、文档内容、路径、Prompt 或密钥。不存在返回 `404 JOB_NOT_FOUND`。

现有 `GET /api/v1/documents/{document_id}` 继续作为 Document 状态查询接口，不新增重复的 V2 Document 查询。

## 3. 状态机

Job：

```text
pending --原子领取--> running --成功--> ready
                           |
                           +--受控失败与补偿--> failed

running --Worker 进程消失、下次启动恢复--> pending
```

Document：

```text
processing --Job 成功--> ready
processing --Job 失败--> failed
```

约束：

- Job 与 Document 的终态更新在同一个 SQLite 短事务中完成；
- 只有 `pending` Job 可以被领取；
- 领取使用 `BEGIN IMMEDIATE` 和条件更新，`attempt_count` 每次领取加一；
- P0 只有一个 Worker，不支持两个 Worker、旧 Worker 晚到或网络分区。

## 4. SQLite 并发

- Schema 使用 `PRAGMA user_version` 从现有 V1 数据库兼容增加 `ingestion_jobs` 表，不删除或重建已有 Document；
- 每个连接启用 `foreign_keys=ON`、`journal_mode=WAL` 和可配置 `busy_timeout`，默认 5000 ms；
- API 文件 I/O、PDF 解析、Embedding、Qdrant 网络调用和 Worker 轮询睡眠均不放进数据库事务；
- 原子操作只覆盖 Document/Job 创建、Job 领取、终态更新和恢复状态转换；
- 锁冲突测试同时覆盖“锁在超时前释放后成功”和“超过有限等待后安全失败”。

## 5. 共享摄取核心

同步 V1 与异步 Worker 复用同一个 processing core：

```text
既有 Document + 受控 stored_path
→ 校验路径和文件存在
→ 按 document_id 清理可能残留的 Qdrant Point
→ parse
→ chunk
→ embedding
→ Qdrant upsert
→ 返回 chunk_count
```

processing core 不创建 Document/Job，也不决定 HTTP 响应。V1 orchestration 和 Worker 分别负责自己的状态提交与失败补偿，避免复制两套解析/切分/Embedding 逻辑。

## 6. 固定崩溃点与恢复

唯一演示崩溃点：

```text
Qdrant upsert 已成功
→ [在 SQLite Job/Document 更新为 ready 之前强制结束 Worker 进程]
```

此时 Job 保持 `running`、Document 保持 `processing`，Qdrant 可能已有 Point。Worker 重启后：

1. 将遗留 `running` Job 恢复为 `pending`；
2. 再次原子领取，`attempt_count` 增加；
3. processing core 先按 `document_id` 删除残留 Point；
4. 重新解析、Embedding 和写入；
5. 同一事务把 Job/Document 更新为 `ready`。

这是单 Worker 前提下的补偿式幂等。R23 不声称解决仍存活旧 Worker 的晚到写入；该问题需要 Lease/Fencing，属于后续阶段。

## 7. 删除—摄取竞态

- Document 为 `processing` 时，现有 DELETE 返回 HTTP 409 和 `DOCUMENT_PROCESSING`；
- 不删除文件、Document、Job 或 Qdrant Point；
- P0 不提供取消；
- Job 到达 `ready` 或 `failed` 后，继续使用现有同步删除编排；关联 Job 由 SQLite 外键级联清理。

由于 P0 状态只允许 `processing → ready/failed` 单向转换，Document 进入终态后不会重新变为活动摄取状态。

## 8. 最小验收

- V1 同步上传仍返回 201 且全量回归通过；
- V2 上传返回 202/job_id，不在请求内调用 Embedding；
- 独立 Worker 将 Job/Document 从 pending/processing 推进到 ready/ready；
- Job 查询能观察状态与 attempt；
- Worker 固定崩溃点退出后，第二个进程恢复同一 Job 且没有重复可见 Chunk；
- processing Document 删除返回 `409 DOCUMENT_PROCESSING`；
- SQLite WAL、busy_timeout、原子领取和事务回滚测试通过；
- Qdrant 部分写入和 Worker 受控失败执行补偿；
- Compose 三服务可启动；
- CI 不依赖真实 Provider Key，不产生费用；
- branch-aware 覆盖率不低于 85%，README 不把 R23 写成高并发生产任务系统。

## 9. 实现与验收记录（2026-09-02）

关键实现映射：

- `app/api/routers/ingestion_jobs.py`：V2 `202` 接收与 Job 查询；
- `app/services/async_ingestion_service.py`：有界文件保存和 Document/Job 原子创建；
- `app/services/ingestion_processor.py`：V1 与 Worker 共用的解析、切块、Embedding 和向量写入核心；
- `app/services/ingestion_worker.py`：原子领取、成功/失败收敛、启动恢复及补偿；
- `app/storage/sqlite_document_repository.py`：schema v2、WAL、5000 ms `busy_timeout`、短事务和条件更新；
- `app/worker.py`：独立 Worker 进程入口；
- `compose.yaml`：API + Worker + Qdrant 三服务，共享 `app_data`、独立 `qdrant_data`。

SQLite 锁冲突采用 SQLite 自带的 `busy_timeout` 做有限等待，不在应用层盲目重放整个事务。这样既覆盖短锁竞争，又避免在“提交结果不确定”时重复业务操作；超过 5000 ms 后返回安全存储错误或让 Worker 退出，由进程重启恢复遗留 `running` Job。

除固定强制崩溃点外，Worker 还处理两类终态边界：

- 若 `complete_job()` 报错但回读确认 Job/Document 已共同成为 `ready`，保留文件和向量，按已成功处理；
- 若无法确认 ready，不执行破坏性补偿，Worker 退出，保留 `running/processing` 供启动恢复；
- 若处理失败后的失败状态写入也失败，Worker 不继续空转，而是退出并让启动恢复收敛。

最终完整质量门禁结果：

- 182 项自动化测试通过，另有 34 个参数化子测试通过；
- branch-aware 总覆盖率 87.59%，高于 85% 门槛；
- Ruff lint/format、依赖检查、字节码检查和固定离线评测全部通过；
- 真实 Qdrant Server 临时 collection 集成测试通过；
- 两个独立 Python 进程完成“第一次在固定点退出、第二次恢复”的测试，最终 `attempt_count=2` 且无重复可见 Chunk；
- 10 份合成文档、50 道题的离线评测口径和结果未改变；
- 全部测试使用 Fake/确定性 Provider，没有调用 OpenAI、DeepSeek 或产生费用。

未覆盖边界保持不变：部署只声明一个 Worker；若人为启动第二个 Worker，启动恢复可能把仍在执行的 Job 重新排队。多 Worker 所有权、Lease/Fencing、业务重试队列、取消和长期 reconciler 均不属于 R23。
