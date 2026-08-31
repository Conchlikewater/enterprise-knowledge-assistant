# V3 阶段 0 API 契约

> 状态：范围对齐修订完成，等待阶段 0 最终验收；接口尚未实现。
> 兼容原则：现有 `/api/v1` 同步语义不变；异步摄取使用 `/api/v2`；调查使用 `/api/v3`。

## 1. V1 兼容基线

### `POST /api/v1/documents`

- 继续同步摄取；
- 成功返回 `201 Created` 和现有 `DocumentResponse`；
- 不要求 `Idempotency-Key`；
- 不向调用方暴露 V2 Job 字段；
- 切换到 Qdrant Server 后，上传、Search、Answer、Citation、拒答和删除必须完成回归。

## 2. V2 异步摄取

### `POST /api/v2/documents`

- 请求：`multipart/form-data` 文件和必填请求头 `Idempotency-Key`；
- 成功：`202 Accepted`；
- 响应头：`Location: /api/v2/ingestion-jobs/{job_id}`；
- 幂等重放额外返回 `Idempotency-Replayed: true`。

```json
{
  "document_id": "uuid",
  "job_id": "uuid",
  "document_status": "processing",
  "job_status": "queued",
  "status_url": "/api/v2/ingestion-jobs/uuid"
}
```

只有临时文件、SQLite 记录、规范文件和 Job 状态已经由上传 Saga 收敛到可执行状态后才返回 202。Job 处于 staging 时不得提前返回成功响应。

### 2.1 幂等与重复文件

| 情况 | 返回 | 稳定行为 |
| --- | --- | --- |
| 首次 Key + 新 SHA | 202 | 创建一个 Document 和一个 Job |
| 同 Key + 同一文件指纹 | 202 | 返回原 ID 和当前状态，不创建新记录 |
| 同 Key + 不同文件 | 409 | `IDEMPOTENCY_KEY_REUSED` |
| 不同 Key + 相同 SHA | 409 | `DOCUMENT_ALREADY_EXISTS` |
| 缺少 Key | 422 | `IDEMPOTENCY_KEY_REQUIRED` |

文件指纹至少包含内容 SHA-256、规范媒体类型和大小。`documents.sha256 UNIQUE` 保持不变。当前本地单用户范围允许在重复文件错误中返回已有 `document_id`；P1 引入身份后必须先做权限检查。

### `GET /api/v2/ingestion-jobs/{job_id}`

返回 Job ID、Document ID、状态、attempt、当前安全步骤、稳定错误码、安全摘要和创建/开始/完成时间。

不得返回进程锁信息、内部路径、数据库语句、密钥、Prompt 或文档原文。

### `GET /api/v2/documents/{document_id}`

返回公开文档元数据、Document 状态、当前或最近 Job ID、chunk count 和安全错误。`stored_path` 不对外返回。

### `POST /api/v2/documents/{document_id}/ingestion-jobs`

用于显式重试：

- 只允许 failed Document；
- 必须使用新的 `Idempotency-Key` 并重新上传文件；
- SHA、媒体类型和大小必须与原 Document 指纹一致；
- 在 SQLite 事务中把 Document 恢复为 processing 并创建新的 staging Job；
- 文件原子恢复到规范路径后，Job 才能从 staging 进入 queued；
- 成功返回 202、新 Job ID，Document ID 不变；
- 文件不一致返回 `409 RETRY_FILE_MISMATCH`；
- ready、processing、deleting/deleted 或存在活跃 Job 时返回 `409 INVALID_STATE_TRANSITION`。

旧 Job 保持终态，不能把 failed Job 改回 queued。

## 3. 删除文档

### `DELETE /api/v2/documents/{document_id}`

| 情况 | 返回 | 稳定行为 |
| --- | --- | --- |
| Document=processing | 409 | `DOCUMENT_PROCESSING` |
| 关联 Job=staging/queued/processing | 409 | `DOCUMENT_PROCESSING` |
| 被 created/running/needs_clarification Investigation 引用 | 409 | `DOCUMENT_IN_USE` |
| ready/failed 且可同步清理 | 204 | 删除文件和 Qdrant 数据，保留 deleted 墓碑 |
| ready/failed 且需异步清理 | 202 | Document=deleting，通过 GET 查询 |
| 已删除 | 204 | 幂等返回 |

P0 不提供取消、force 删除或“删除时自动取消 Job”。不存在以下接口：

```text
POST /api/v2/ingestion-jobs/{job_id}/cancel
```

Investigation 已完成后，其结果和 Citation 快照可以保留，但这不是正式归档保证；Document 删除后对外结果应标明来源已删除。完整报告保留政策延期到 P1。

## 4. Investigation REST 契约

### 4.1 状态枚举

唯一合法状态：

```text
created / running / needs_clarification / completed / failed
```

P0 没有 waiting_approval、rejected、cancelled、Draft 版本或归档状态。

### `POST /api/v3/investigations`

请求：

```json
{
  "question": "比较选定制度中的年假与审批责任。",
  "document_ids": ["uuid-a", "uuid-b"]
}
```

约束：

- `question` 非空且有长度上限；
- `document_ids` 非空、去重且不超过配置上限；
- 所有 Document 必须存在并处于 ready；
- 服务端将这组 ID 固化为唯一允许范围；模型和工具不能扩大。

成功返回 `202 Accepted`：

```json
{
  "investigation_id": "uuid",
  "status": "created",
  "state_version": 1,
  "status_url": "/api/v3/investigations/uuid"
}
```

响应头包含 `Location: /api/v3/investigations/{id}`。

### `GET /api/v3/investigations/{id}`

这是创建后的统一查询入口：

```json
{
  "investigation_id": "uuid",
  "status": "running",
  "state_version": 2,
  "question": "...",
  "document_ids": ["uuid-a", "uuid-b"],
  "subquestions": [],
  "retrieval_rounds_used": 1,
  "unique_candidate_count": 5,
  "coverage": null,
  "stop_reason": null,
  "clarification_request": null,
  "evidence_table": null,
  "result": null,
  "error": null
}
```

字段规则：

- `needs_clarification`：返回安全的 `clarification_request`；
- `completed`：返回 Evidence Table、`answer` 或 `refusal`、调查报告和 claim-level Citations；
- `failed`：只返回稳定错误码和安全摘要；
- Citation 至少返回 claim ID、document ID、chunk ID、文件名和可用页码；
- Document 已删除时，历史 Citation 增加 `source_available=false`；
- 不返回完整内部 Prompt、原始模型响应、数据库字段、本地路径、密钥或堆栈；
- 不存在返回 `404 INVESTIGATION_NOT_FOUND`。

### `POST /api/v3/investigations/{id}/clarifications`

仅允许 `needs_clarification`：

```json
{
  "clarification": "只比较澳大利亚办公室政策。",
  "expected_state_version": 3
}
```

成功时进行条件更新，`state_version + 1`、状态回到 running 并返回 202。过期版本返回 `409 STALE_INVESTIGATION`；其他状态返回 `409 INVALID_STATE_TRANSITION`。

P0 不定义以下 Investigation 接口：

```text
POST /api/v3/investigations/{id}/cancel
POST /api/v3/investigations/{id}/revise
POST /api/v3/investigations/{id}/approve
POST /api/v3/investigations/{id}/reject
POST /api/v3/investigations/{id}/archive
```

## 5. Agent 结果语义

`result` 只能在 completed 时存在：

```json
{
  "response_label": "answer",
  "report": {
    "summary": "...",
    "comparisons": [],
    "uncertainties": []
  },
  "citations": [],
  "evaluation_metadata": {
    "decision_config_version": "v3-p0-pending-calibration",
    "final_answer_prompt_version": "v3-final-answer-v1"
  }
}
```

`response_label` 只能是 `answer` 或 `refusal`。证据不足达到终止条件时，可以 completed + refusal；需要用户补充时使用 needs_clarification；Provider 或内部不可恢复错误使用 failed。

## 6. 稳定错误码

| HTTP | 错误码 | 含义 |
| --- | --- | --- |
| 404 | `DOCUMENT_NOT_FOUND` | Document 不存在 |
| 404 | `JOB_NOT_FOUND` | Job 不存在 |
| 404 | `INVESTIGATION_NOT_FOUND` | Investigation 不存在 |
| 409 | `DOCUMENT_PROCESSING` | 文档或关联 Job 正在处理，不能删除 |
| 409 | `DOCUMENT_IN_USE` | 活跃 Investigation 正在引用 |
| 409 | `DOCUMENT_ALREADY_EXISTS` | 相同 SHA 已存在 |
| 409 | `IDEMPOTENCY_KEY_REUSED` | Key 被用于不同文件 |
| 409 | `RETRY_FILE_MISMATCH` | 重试文件与原指纹不同 |
| 409 | `INVALID_STATE_TRANSITION` | 当前状态不允许该动作 |
| 409 | `STALE_INVESTIGATION` | 澄清请求基于旧状态版本 |
| 422 | `IDEMPOTENCY_KEY_REQUIRED` | 缺少幂等键 |
| 422 | `EMPTY_DOCUMENT_SCOPE` | Investigation 未选择文档 |
| 422 | `DOCUMENT_NOT_READY` | 选择了非 ready 文档 |
| 500 | `DOCUMENT_SCOPE_VIOLATION` | Agent 轨迹出现范围越界，任务失败关闭 |
| 502 | `PROVIDER_OUTPUT_INVALID` | Provider 输出经受控处理后仍无效 |
| 503 | `DATABASE_BUSY` | SQLite 锁等待与有限重试已耗尽 |
| 503 | `DEPENDENCY_UNAVAILABLE` | SQLite、Qdrant 或 Provider 不可用 |

继续使用统一错误包：

```json
{
  "error": {
    "code": "STABLE_CODE",
    "message": "Safe public message.",
    "request_id": "uuid"
  }
}
```

## 7. 隐私与健康检查

日志、Trace 和错误不得包含 API Key、完整 Prompt、完整文档/Chunk 原文、内部路径、数据库语句或原始异常堆栈。

容器健康检查至少区分进程存活与依赖可用。SQLite 或 Qdrant 不可用时 API 不能报告完全健康；Worker 健康信息只报告进程锁、任务循环和依赖状态，不泄露路径或业务内容。
