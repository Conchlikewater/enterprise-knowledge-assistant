# V3 阶段 0 验收样例

> 状态：范围对齐修订完成，等待阶段 0 最终验收；以下场景尚未执行。
> 用途：定义 P0 的兼容、故障、安全和评测证据；编号映射到 `v3_test_matrix.md`。

## A. V1、Qdrant Server 与 Compose

### A1：V1 兼容

切换 Qdrant Server 后，`POST /api/v1/documents` 仍同步返回 201；既有 Search、Answer、Citation、无证据拒答和删除没有回归。

### A2：Server 共享与持久化

API 和 Worker 通过 URL 连接同一 Qdrant Server。写入后可检索，Qdrant/容器重启后 ready Document 数据仍存在。Local/Fake 不用于多进程正式集成。

### A3：最小 Compose 健康

干净环境启动 API、一个 Worker 和 Qdrant。API 健康检查反映 SQLite/Qdrant 真实状态；第二个 Worker 不能静默启动；卷重启后数据保留。Compose 不包含 Redis 或监控平台。

## B. 幂等、Saga 与重试

### B1：Idempotency-Key 重放

同 Key、同文件重复上传三次，只存在一个 Document/Job，返回相同 ID；重放请求有明确响应标记。

### B2：重复冲突

- 同 Key 换文件：`409 IDEMPOTENCY_KEY_REUSED`；
- 换 Key 上传相同 SHA：`409 DOCUMENT_ALREADY_EXISTS`；
- `documents.sha256 UNIQUE` 保持存在。

### B3：上传四个崩溃边界

分别在临时文件完成、SQLite事务提交、原子重命名、staging→queued 前制造崩溃。恢复器最终得到唯一 queued Job 或明确 failed 记录，不留下可领取但无文件的 Job、永久孤儿文件或重复 Document。

### B4：规范路径门禁

文件未原子恢复到规范路径前 Job 只能 staging，不能被 claim。ready 时文件存在；failed/deleted 时文件不存在，但 `stored_path` 字段仍保存规范地址且不向 API 暴露。

### B5：显式重试

failed Document 用新 Key 重新上传相同指纹文件，创建新 Job、保留 Document ID。文件不同返回 `409 RETRY_FILE_MISMATCH`；旧 failed Job 保持终态。

## C. 单 Worker、SQLite 并发与补偿

### C1：进程互斥

Worker A 持有共享 OS 锁时启动 Worker B，B 必须失败退出且不能领取 Job。A 正常退出或崩溃后，锁由 OS 释放，新的唯一 Worker 才能启动。

Windows 本地和 Linux 容器分别验证；不把结果推广到网络文件系统或多主机。

### C2：原子领取

任务循环和恢复逻辑同时尝试领取同一 queued Job，只有一个 SQLite 条件更新影响 1 行；attempt 只增加一次。

### C3：遗留 processing 恢复

Worker 在解析、Embedding 和 Qdrant 写入阶段分别崩溃。新 Worker取得独占锁后发现遗留任务，按 Document 清理残留并重放；最终只有一次完整可见 Chunk 集。

### C4：Qdrant 部分写入

写入一半后失败。Document 保持 processing、业务检索拒绝该 Document。补偿删除残留；重放使用确定性 Chunk ID，不生成重复可见 Point。

### C5：完成事务失败

Qdrant 已写完但 SQLite 完成事务失败。Document 不得变为 ready。恢复器清理或重放后，Job/Document 才能一致进入 succeeded/ready。

### C6：API 与 Worker 并发

API 创建 queued Job 的同时，Worker 更新另一个 Job。WAL 下两个操作最终成功，没有丢失更新、无限等待或半事务状态。

### C7：锁冲突与有限重试

使用受控写锁制造 `database is locked`：`busy_timeout=1000ms`；首次失败后只按50ms、150ms再试两次；唯一约束和状态冲突不重试。API耗尽后返回 `503 DATABASE_BUSY`；Worker耗尽后退出且不再产生外部副作用，事务完整回滚。

### C8：外部 I/O 不占事务

故障注入确认文件解析、Embedding、Qdrant和LLM调用期间没有保持SQLite写事务。

## D. 删除边界

### D1：处理中删除统一409

分别构造 Job=staging、queued、processing。DELETE均返回：

```text
HTTP 409
DOCUMENT_PROCESSING
```

Document/Job状态不变，不产生取消请求，不开始清理。

### D2：ready/failed 删除

没有活跃 Investigation 引用时，ready/failed Document 的文件和 Qdrant Point 被幂等清理并进入 deleted。重复 DELETE 返回204。

### D3：活跃 Investigation 引用

created/running/needs_clarification Investigation 引用 Document 时，DELETE 返回 `409 DOCUMENT_IN_USE`。completed/failed 后按P0删除政策重新判断。

### D4：不存在取消接口

请求旧计划中的 Job/Investigation cancel 路径返回404/405，不改变任何状态。API文档中不暴露cancel操作。

## E. Investigation 与两轮决策

### E1：完整 REST 闭环

创建 Investigation 返回202和查询地址；GET可观察五种状态及安全结果；needs_clarification可提交匹配state version的澄清并回到running。

### E2：五状态与终态

只允许 `created/running/needs_clarification/completed/failed`。waiting_approval、rejected、cancelled或Draft版本状态无法写入。completed/failed不能恢复。

### E3：澄清并发

两个请求携带相同 `expected_state_version`，只有一个成功，另一个返回 `409 STALE_INVESTIGATION`。

### E4：文档范围继承

所有物理检索调用都自动携带顶层 document IDs。模型尝试加入额外 ID 时被判定 `SCOPE_VIOLATION`，Investigation failed，不以静默过滤掩盖越界。

### E5：全局两轮上限

无论子问题数量多少，`rounds_used <= 2`。每轮合并去重后最多接纳5个候选，总候选预算不超过10；不存在“每个子问题两轮”。

### E6：第二轮正确触发

第一轮证据不足、存在未覆盖required子问题、有新查询且有预算时触发；证据充分、必须澄清或无新查询时不触发。所有输入和结果可回放。

### E7：停止原因

固定fixture分别得到 `SUFFICIENT_EVIDENCE`、`NEEDS_CLARIFICATION`、`NO_NEW_EVIDENCE`、`MAX_ROUNDS_REACHED`、`SCOPE_VIOLATION`、`PROVIDER_OUTPUT_INVALID` 和 `DEPENDENCY_UNAVAILABLE`。

### E8：证据不足

两轮后仍无足够证据，completed结果为refusal并说明缺失，不生成无依据结论或伪造Citation。

### E9：Evidence Table

证据表只使用accepted Evidence，按固定规则排序并去重；required子问题无证据时显示missing evidence行。每个关键claim绑定真实chunk ID与来源。

### E10：Prompt Injection与工具白名单

检索文本要求“忽略规则、扩大文档范围或执行命令”时，只作为不可信Evidence。Agent不能调用网络、Shell、代码执行、任意文件或数据库写入工具。

### E11：确定性Workflow降级

动态两轮Agent不稳定时，切换确定性两阶段Workflow。顶层范围、轨迹Schema、两轮/候选预算、纯函数和评测口径保持相同，不能用降级逃避门禁。

## F. 评测与Citation

### F1：固定轨迹回放

同一轨迹和DecisionConfig重复回放得到相同coverage、第二轮触发、停止原因、Evidence Table和响应标签，且不调用真实Provider。

### F2：24题Schema与盲审

24题都包含规定字段。第二次盲审不显示第一次理由；不一致题被修改、删除或标为歧义，歧义题不进入硬门禁。

### F3：三组公平对照

Dense Top-5、Dense Top-10和Agentic 5×2使用相同数据、Embedding、生成模型、最终回答指令和Evidence格式。分别记录去重候选、Recall、MRR、延迟、检索次数与成本。

### F4：Citation三层检查

逐claim验证chunk ID、来源/页码和原文语义支持。只有三项都通过才计fully correct，并单独报告每层指标和claim完整性。

### F5：应答/拒答混淆矩阵

固定题集输出answer/refusal混淆矩阵；needs_clarification单独统计，不用总体准确率掩盖错误拒答或错误应答。

## G. CI、隐私与真实Provider

### G1：无密钥CI

清空OpenAI/DeepSeek Key后，CI仍可运行Fake Provider、轨迹回放、纯函数、故障注入、指标回归和无Key Qdrant Server测试；无外部付费请求。

### G2：日志与Trace隐私

自动扫描日志、错误和轨迹，确认没有API Key、内部路径、完整Prompt、完整私密原文或原始第三方响应正文。

### G3：DeepSeek协议待验证

阶段0只校验 `v3_evaluation_protocol.md` 已完整定义模型、Prompt、Schema、兼容解析、一次重试、模板降级、请求/token上限和预算模板。未授权时状态保持“待验证”，不执行网络调用。

### G4：真实Provider授权门禁

本地真实评测命令在未提供显式运行标志、用户批准和预算配置时拒绝执行。执行后报告Provider、模型、版本、请求数、token、成本和延迟，不与离线结果混合。

## 阶段门禁

- A1–A3通过后，才进入真实异步Worker集成；
- B1–D4及旧回归全部通过后，才开始Agent业务实现；
- E1–F5通过后，才可申请真实Provider完整对照；
- G1–G3、覆盖率和秘密扫描通过后，才能宣称离线P0完成；
- G4未执行不影响阶段0文档冻结，但README必须明确真实Provider仍待验证。
