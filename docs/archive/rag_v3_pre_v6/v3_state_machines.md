# V3 阶段 0 状态机

> 状态：范围对齐修订完成，等待阶段 0 最终验收；尚未实现。
> 真相源：SQLite。非法转换返回稳定错误，不由 Router 或模型临时决定。

## 1. DocumentStatus

```text
processing ──(摄取全部成功)──> ready
     │                         │
     └─(补偿完成)────────────> failed
                               │
ready / failed ──(允许删除)──> deleting ──(清理完成)──> deleted

failed ──(重新上传同指纹 + 新 Job)──> processing
```

状态含义：

- `processing`：Document 已建立，但文件 Saga 或摄取 Job 尚未完成；不可检索、不可删除；
- `ready`：文件存在、Qdrant Chunk 完整、chunk count 已提交；允许检索；
- `failed`：不完整文件和 Qdrant 残留已经补偿；可显式重试或删除；
- `deleting`：ready/failed Document 的删除已接受，正在幂等清理；
- `deleted`：删除墓碑；不得检索或重用 Document ID。

如果 Document=processing，或关联 Job=staging/queued/processing，DELETE 固定返回 `409 DOCUMENT_PROCESSING`。P0 不通过删除触发取消。

`stored_path` 始终是规范目标路径，不是文件存在性承诺：ready 时文件必须存在；failed/deleted 时文件应不存在；processing/staging 时可能尚未完成原子重命名。

## 2. IngestionJobStatus

```text
staging ──(规范文件就绪)──> queued ──(原子 claim)──> processing
    │                         │                         │
    └─(不可恢复)────────────> failed <────────────────┤
                                                      │
                           succeeded <──(完整写入并提交)┘
```

唯一状态为：`staging / queued / processing / succeeded / failed`。

- staging 文件未就绪时不能被 claim；
- queued→processing 必须使用 SQLite 条件更新；
- succeeded/failed 是终态；显式 retry 创建新 Job；
- processing 失败时先完成补偿，再进入 failed；
- P0 没有 cancelling/cancelled，也没有 processing→queued 的 Lease 超时接管。

## 3. 单 Worker 崩溃恢复

```text
Worker A 持有 OS 独占锁
  -> 原子 claim Job
  -> Job=processing / Document=processing
  -> 写入部分 Qdrant Point
  -> 进程崩溃，OS 自动释放锁

Worker B 启动
  -> 成功取得同一 OS 独占锁
  -> 启动恢复器发现遗留 processing Job
  -> 校验原文件与数据库记录
  -> 按 document_id 清理 Qdrant 残留
  -> 使用确定性 Chunk ID 重放
  -> 成功：Job=succeeded + Document=ready
     失败：补偿完成后 Job/Document=failed
```

只有取得独占锁的进程可以运行恢复器或领取任务。第二个 Worker 不能取得锁时必须退出，不能进入降级双活。

P0 不处理两个仍存活 Worker、网络分区或旧 Worker 晚到竞争；这些场景需要 P1 Lease/Heartbeat/Generation/Fencing。

## 4. 上传 Saga

```text
temporary file complete
  -> SQLite transaction:
       Idempotency + Document(processing) + Job(staging)
  -> atomic rename to canonical path
  -> conditional Job(staging -> queued)
  -> return 202
```

恢复规则：

- final 存在且指纹正确：staging→queued；
- temporary 存在、final 不存在：完成原子重命名后 queued；
- 文件均不存在或指纹错误：补偿后 Job/Document failed；
- 无数据库记录的过期 temporary：按保留窗口清理；
- 所有操作可重复执行且不得产生第二个 Document/Job。

## 5. 删除状态机

```text
ready / failed
  -> 检查无活跃 Job、无活跃 Investigation
  -> deleting
  -> 清理文件和 document_id 对应 Qdrant Point
  -> deleted
```

若能在请求内完成清理，API 返回 204；若采用异步清理，返回 202 并通过 Document GET 查询。processing 与活跃 Job 一律在转换前返回 409。

## 6. InvestigationStatus

```text
created ─────> running ─────> completed
                  │
                  ├────> needs_clarification ─────> running
                  │
                  └────> failed

created ────────────────────────────────────────> failed
needs_clarification ───────────────────────────> failed
```

完整枚举固定为：

```text
created / running / needs_clarification / completed / failed
```

合法转换：

- `created -> running`：执行器开始；
- `created -> failed`：启动前校验或依赖失败；
- `running -> needs_clarification`：需要用户补充关键信息；
- `needs_clarification -> running`：提交匹配 `state_version` 的澄清；
- `running -> completed`：生成 answer 或 refusal 类型结果；
- `running/needs_clarification -> failed`：范围越界、Provider持续无效或内部不可恢复错误。

completed/failed 为终态。P0 不允许取消、拒绝、审批、归档或 Draft 修订。

## 7. 两轮检索状态

检索轮次不是独立业务状态，而是 Investigation 轨迹字段：

```text
rounds_used=0
  -> round 1（本轮最多接纳 5 个去重候选）
  -> 决策内核
       ├─ evidence sufficient -> stop=SUFFICIENT_EVIDENCE
       ├─ need clarification -> status=needs_clarification
       ├─ no valid next query -> stop=NO_NEW_EVIDENCE / completed refusal
       └─ round 2 required -> round 2（最多再接纳 5 个候选）
             -> 决策内核
                  ├─ sufficient -> completed answer
                  └─ insufficient -> completed refusal
```

整个 Investigation 的 `rounds_used <= 2`，接纳候选总数 `<= 10`。每个子问题不能各自获得两轮预算。

## 8. 轨迹与业务状态

SQLite 保存 Investigation 状态和最终结果。轨迹/Checkpoint 保存计划、检索调用、候选、纯函数输入输出和 Prompt 版本，用于恢复、调试与离线回放。

恢复时必须先读取 SQLite：completed/failed 终态不能被旧轨迹重新打开。P0没有需要审批的外部副作用，也不宣称正式报告归档能力。
