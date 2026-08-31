# V3 P0 评测与真实 Provider 协议

> 状态：阶段 0 候选冻结；24 道题尚未建立，真实 Provider 尚未授权和运行。
> 边界：所有结果只代表当前小规模合成企业文档集和冻结配置，不代表真实企业环境。

## 1. 评测目标

V3 评测分别回答：

1. 检索是否找到了正确 Evidence；
2. 子问题是否覆盖完整；
3. 第二轮是否在应该发生时发生；
4. 第二轮是否增加了有效证据；
5. 是否始终遵守顶层 Document 范围；
6. 证据不足时是否正确拒答或请求澄清；
7. Citation 是否指向正确 Chunk、来源/页码并真正支持结论；
8. Agent 收益是否只是来自更大的候选预算；
9. 离线回放与真实 Provider 结果是否被清楚区分。

## 2. 数据分层

1. **既有回归集**：10 文档/50 题，只检查 V1 Dense/Answer 回归，不参与 V3 参数反复选择；
2. **Agent 开发 fixtures**：用于选择 score/coverage/min-evidence 参数和纯函数测试；
3. **24 道 Agent 题**：用于 P0 对照评测和盲审；
4. **固定轨迹 fixtures**：由结构化 Provider/检索轨迹脱敏生成，CI 可离线回放；
5. **真实 Provider 运行记录**：单独目录和显式命令，经用户授权后产生，不进入默认 CI。

24 题中用于参数选择的开发题与最终报告题必须明确列出。第二次盲审结果不得反向用于调参；歧义题不进入硬门禁。

## 3. 24 道题标注 Schema

每题至少包含：

```json
{
  "question_id": "agent-q001",
  "question_type": "multi_document_comparison",
  "question": "...",
  "allowed_document_ids": ["..."],
  "expected_subquestions": [
    {
      "subquestion_id": "sq1",
      "text": "...",
      "required": true
    }
  ],
  "expected_evidence": [
    {
      "subquestion_id": "sq1",
      "document_id": "...",
      "chunk_id": "...",
      "page_number": 1,
      "support_label": "supports"
    }
  ],
  "expected_conclusions": ["..."],
  "should_run_second_round": true,
  "expected_stop_reason": "SUFFICIENT_EVIDENCE",
  "response_label": "answer",
  "citation_requirements": ["claim-1"],
  "ambiguity_status": "clear"
}
```

允许题型至少覆盖：单文档事实、多文档比较、冲突证据、信息缺失、需要澄清、应拒答和 Prompt Injection 干扰。

## 4. 标注与盲审流程

- Week 1：冻结 Schema、标签枚举和评分规则；
- Week 2：完成第一批题目；
- Week 3：完成剩余题目；
- Week 4：与第一次标注间隔数日，隐藏第一次理由，重新判断期望结论、Evidence、是否第二轮和停止原因；
- 对两次不一致题目逐题处理：修改题干/证据、删除，或标记 `ambiguous`；
- ambiguous 题可以进入人工分析，但不能用于阻止 CI 或生成主指标；
- 每次修改增加 dataset version，并保存修改原因。

AI 可以辅助草拟标签，但最终 Evidence、结论和 Citation 支持关系由人工核对。

## 5. 三组公平对照

### A：现有单轮 Dense Top-5

- 使用原始问题执行一次 Dense 检索；
- 候选预算最多 5；
- 使用统一最终回答指令和 Evidence 格式。

### B：预算匹配单轮 Dense Top-10

- 使用同一原始问题执行一次 Dense 检索；
- 候选预算最多 10；
- 用于区分“Agent 策略收益”和“候选预算翻倍收益”。

### C：两轮 Agentic 5×2

- 每个逻辑轮次最多接纳 5 个全局去重候选；
- 全局最多两轮，总候选预算最多 10；
- 子问题多查询必须共享每轮预算，不是每个子问题 Top-5；
- 第二轮只能由版本化纯决策规则触发。

## 6. 控制变量

三个方案必须使用相同：

- 题集版本与纳入/排除题目；
- 文档文件、SHA 和 Chunk 数据；
- Embedding Provider、模型和版本；
- 生成 Provider、模型、温度和 token 上限；
- 最终回答/拒答指令版本；
- Evidence 和 Citation 输出 Schema；
- score threshold 配置；
- 运行机器/容器配置或明确记录差异。

Prompt 不强求完全相同：

- 单轮回答 Prompt 单独版本化；
- Agent 子问题规划 Prompt 单独版本化；
- 第二轮查询 Prompt 单独版本化；
- 最终回答指令保持一致；
- 结果记录 Prompt 版本、文件哈希和配置快照。

## 7. 参数选择方法

正式评测臂的候选预算固定为 Top-5、Top-10、5×2。进入 Agent 实现前，只在开发 fixtures 上比较：

- score threshold：`None / 0.20 / 0.25 / 0.30 / 0.35 / 0.40`；
- coverage threshold：`0.60 / 0.75 / 1.00`；
- 每个 covered 子问题最低 Evidence：`1 / 2`。

选择顺序：

1. 排除导致明显范围错误或大量空检索的配置；
2. 比较 Evidence Recall、拒答混淆矩阵和第二轮触发正确率；
3. 在质量接近时选择规则更简单、调用更少的配置；
4. 将最终配置、指标和未选择原因写入版本化报告；
5. 不使用最终盲审题继续调参。

旧语义实验报告出现的 `0.37` 只是一项历史数据点，不自动采用。

## 8. 指标定义

### 8.1 Evidence Recall@K

```text
Evidence Recall@K = 检索到的唯一 gold Evidence 数 / gold Evidence 总数
```

K 对应每个对照臂的总候选预算。多轮结果按首次出现顺序合并并去重。

### 8.2 MRR

```text
RR(question) = 1 / 第一个 gold Evidence 的排名
MRR = 所有有效题 RR 的平均值
```

没有检索到 gold Evidence 时 RR=0。两轮排序为第一轮候选在前、第二轮新增候选在后，并保留轮内顺序。

### 8.3 子问题覆盖率

使用 `v3_agent_decision_contract.md` 的公式。评测时将生成子问题映射到人工 expected subquestions；无法可靠映射的题不进入硬门禁。

### 8.4 第二轮新增有效证据数

```text
round2_new_useful_evidence =
第二轮首次出现且属于 gold/supporting Evidence 的唯一 Chunk 数
```

同时报告第二轮新增候选数，防止只展示有效部分。

### 8.5 第二轮触发正确率

将实际布尔值与人工 `should_run_second_round` 比较，报告准确率和混淆矩阵。不能只报告“触发了多少次”。

### 8.6 停止原因正确率

实际 stop reason 与 gold 枚举完全匹配才计为正确。歧义题单独报告。

### 8.7 文档范围越界率

同时报告：

```text
越界工具/检索调用数 / 总工具/检索调用数
发生至少一次越界的任务数 / 总任务数
```

P0 安全门禁要求两者都为 0。

### 8.8 应答/拒答混淆矩阵

gold 与实际标签均为 answer/refusal，报告 TP、TN、FP、FN。needs_clarification 作为单独流程结果报告，不强行合并为 answer。

### 8.9 Citation 三层评分

每个 claim 的每条 Citation 分别检查：

1. **Chunk identity**：chunk ID 是否属于 gold/可接受支持集合；
2. **Source location**：document、文件名和页码/来源是否正确；
3. **Semantic support**：原文是否真正支持该 claim，而不是主题相关但无法推出结论。

三项都通过才记为 fully correct Citation。另行报告：

- identity accuracy；
- source/page accuracy；
- semantic support accuracy；
- fully correct accuracy；
- claim citation completeness：需要 Citation 的 claim 中，至少有一条 fully correct Citation 的比例。

语义支持以人工 gold 为主，不能只依赖模型自评。

### 8.10 成本与性能

每个对照臂记录：

- 去重候选数和总候选预算；
- 逻辑轮次和物理检索次数；
- Embedding/LLM 调用次数；
- 输入/输出 token；
- Provider 估算成本；
- 检索延迟、生成延迟和总延迟；
- 至少报告平均值，并在样本量允许时报告 P50/P95。

## 9. CI 离线层

CI 不设置 OpenAI/DeepSeek Key，运行：

- Fake/确定性 Provider 单元测试；
- 固定轨迹回放；
- coverage、第二轮触发、停止原因、scope、Evidence Table 纯函数测试；
- 固定 24 题 fixtures 的指标计算回归；
- 异步 Job 状态、SQLite 并发和故障注入；
- 无 Key Qdrant Server 的少量集成测试。

固定轨迹包含结构化输出和哈希，不包含完整私密原文、Key 或不必要的完整 Prompt。CI 报告必须标记 `execution_mode=offline_replay`。

## 10. 真实 Provider 层

真实评测使用单独显式命令，不能被默认 test、CI、pre-commit 或 Compose 启动隐式触发。运行前向用户展示：

- Provider 和模型；
- 数据集和题目数量；
- 三个对照臂；
- 预计请求次数；
- 输入/输出 token 上限；
- 单价来源和估算预算；
- 最大可接受预算；
- 输出文件位置和隐私边界。

获得明确批准后才运行。报告必须标记 `execution_mode=real_provider`，记录开始时间、Provider、模型、Prompt/config/dataset 版本、实际请求数、token、成本、延迟、失败和重试。

若只运行24题子集，必须写出分母和题目 ID，不能称为完整24题结果。

## 11. DeepSeek 结构化输出小型冒烟

### 11.1 状态与门禁

当前状态：**待验证**。阶段 0 只冻结协议，不执行真实调用，不阻塞文档冻结。进入 Agent 实现前单独申请授权。

### 11.2 冻结配置

```text
provider: deepseek
model: deepseek-v4-flash（与当前仓库适配器一致）
prompt_version: v3-structured-plan-smoke-v1
temperature: 0（若 Provider/API 支持；否则记录实际值）
max_requests: 2（首次 + 最多一次受控重试）
max_input_tokens: 2000
max_output_tokens_per_request: 800
budget_cap_usd: 运行前填写，且不得超过 1.00 美元
documents: 许可清楚或仓库已跟踪的合成公开测试材料
```

模型或 API 能力可能变化，执行前必须核对官方能力；发生变化时更新协议版本，不能静默换模型。

### 11.3 Pydantic Schema

```text
StructuredPlanSmoke
├── question_summary: str
├── subquestions: 1..6 个
│   ├── subquestion_id: str
│   ├── text: str
│   └── required: bool
├── needs_clarification: bool
└── clarification_request: str | null
```

跨字段校验：`needs_clarification=true` 时 clarification 非空；为 false 时必须为 null。subquestion ID 唯一，文本非空，不接受额外字段。

### 11.4 解析链路

1. 优先使用执行时确认受支持的原生结构化/JSON能力；
2. 兼容解析只允许去除单层 Markdown code fence、提取唯一顶层 JSON object 和规范换行；
3. 使用标准 JSON parser 后立即进行 Pydantic 严格校验；
4. 首次失败时只允许一次重试，重试 Prompt 包含安全、压缩后的字段级校验错误，不包含密钥或整份私密原文；
5. 再次失败时使用服务端模板化降级结果，并标记 `generation_mode=template_fallback`；
6. 降级不是“模型结构化输出成功”，必须单独计数。

禁止使用 `eval`、执行模型返回代码、宽松吞错或无限重试。

### 11.5 验收记录模板

```text
user_authorization_reference:
executed_at:
provider/model:
prompt_version/hash:
schema_version:
request_count:
input/output_tokens:
estimated/actual_cost_usd:
latency_ms:
native_parse_result:
compat_parse_result:
pydantic_result:
retry_used:
fallback_used:
safe_error_codes:
conclusion: pass / conditional / fail
limitations:
```

未运行前这些字段保持空白，并在 README 中标注待验证。

## 12. 结果表述边界

所有报告必须注明：

> 结果来自当前小规模合成企业文档集、24 道人工标注 Agent 题及冻结配置，只能证明固定评测范围内的行为，不代表真实企业语料、并发流量或生产安全效果。

不得把离线回放称为真实 LLM 运行，不得把一次真实冒烟称为稳定性评测，不得把 Top-10 或两轮带来的预算增加全部归因于 Agent 策略。
