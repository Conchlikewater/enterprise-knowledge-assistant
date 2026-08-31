# V3 P0 测试矩阵

> 状态：范围对齐修订完成，等待阶段 0 最终验收；仅定义计划，尚未新增或执行测试。
> 原则：每条关键规则都要有自动化证据；真实 Provider 不进入 CI。

## 1. 测试分层

- **现有回归**：V1 API、Service、Provider和10文档/50题离线评测；
- **纯函数单测**：状态转换、范围、coverage、第二轮、停止原因、Evidence Table和指标；
- **SQLite集成**：migration、WAL、原子claim、锁冲突、回滚和Saga；
- **Qdrant Server集成**：真实Server写入、删除、不可用和重启；
- **进程测试**：单Worker互斥、崩溃、重启恢复；
- **故障注入**：Fake Provider/Fake Storage在受控步骤抛错；
- **Agent回放**：固定轨迹和24题fixtures，不使用API Key；
- **Compose冒烟**：clean-start、健康和持久卷；
- **真实Provider**：单独命令、单独授权和预算，不属于CI。

## 2. 需求—测试—证据映射

| ID | 阶段 | 规则/风险 | 计划证据 | 样例 |
| --- | --- | --- | --- | --- |
| COMP-001 | 1 | V1上传仍同步201 | documents API回归 | A1 |
| COMP-002 | 1 | Search/Answer/Citation/拒答不回归 | 既有Service/API/评测回归 | A1 |
| QD-001 | 1 | 正式运行使用Qdrant Server | Server写入、检索、删除 | A2 |
| QD-002 | 1 | Server重启数据保留 | 持久卷重启测试 | A2 |
| COMPOSE-001 | 1 | API/一个Worker/Qdrant可干净启动 | Compose冒烟 | A3 |
| COMPOSE-002 | 1 | 健康检查反映真实依赖 | 停止Qdrant/Worker检查 | A3 |
| IDEM-001 | 2 | 同Key同文件不重复创建 | API+SQLite重放 | B1 |
| IDEM-002 | 2 | 同Key不同文件稳定409 | API契约测试 | B2 |
| IDEM-003 | 2 | 不同Key同SHA稳定409且保留UNIQUE | migration/API测试 | B2 |
| SAGA-001 | 2 | 上传四边界崩溃可恢复 | 故障注入+恢复器 | B3 |
| FILE-001 | 2 | 文件就绪前只能staging | 文件/Saga集成 | B4 |
| RETRY-001 | 2 | failed重传同指纹，新Job旧Document | API/Repository测试 | B5 |
| MUTEX-001 | 2 | 同一主机只有一个Worker | 双进程锁测试 | C1 |
| MUTEX-002 | 2 | 崩溃后OS锁释放 | 杀死进程后重启测试 | C1 |
| CLAIM-001 | 2 | queued→processing条件更新原子 | Repository重入测试 | C2 |
| RECOVER-001 | 2 | 解析阶段崩溃恢复 | Fake parser故障 | C3 |
| RECOVER-002 | 2 | Embedding阶段崩溃恢复 | Fake embedding故障 | C3 |
| RECOVER-003 | 2 | Qdrant阶段崩溃恢复 | Fake/Server部分写入 | C3–C4 |
| CHUNK-001 | 2 | 确定性UUIDv5输入稳定 | Chunk ID单测 | C4 |
| VIS-001 | 2 | processing Document不可检索 | Retrieval/API集成 | C4–C5 |
| COMMIT-001 | 2 | Job succeeded与Document ready同事务 | 提交故障测试 | C5 |
| DB-001 | 2 | WAL下API/Worker并发无丢失更新 | 双连接并发fixture | C6 |
| DB-002 | 2 | busy/locked有限重试 | 受控写锁测试 | C7 |
| DB-003 | 2 | 非busy业务错误不重试 | 唯一/状态冲突测试 | C7 |
| DB-004 | 2 | 外部I/O不持有写事务 | 探针/锁断言 | C8 |
| DELETE-001 | 2 | processing或活跃Job删除返回409 | 参数化API测试 | D1 |
| DELETE-002 | 2 | ready/failed删除幂等 | API+Qdrant+文件测试 | D2 |
| DELETE-003 | 3 | 活跃Investigation阻止删除 | API/Repository竞态 | D3 |
| CANCEL-ABSENT-001 | 2–3 | P0无取消接口/状态 | OpenAPI/API合同测试 | D4 |
| INV-001 | 3 | 创建202与GET完整查询 | API合同测试 | E1 |
| INV-002 | 3 | 五状态及合法转换 | 参数化状态机 | E2 |
| INV-003 | 3 | completed/failed终态不可恢复 | Repository/API测试 | E2 |
| CLARIFY-001 | 3 | 澄清匹配state version | API条件更新 | E3 |
| SCOPE-001 | 3 | 所有工具继承顶层document IDs | Fake轨迹断言 | E4 |
| SCOPE-002 | 3 | 越界导致failed且比率为0门禁 | 恶意轨迹测试 | E4 |
| ROUND-001 | 3 | 全局最多两轮 | 纯函数/轨迹回放 | E5 |
| BUDGET-001 | 3 | 每轮5、总候选10 | 多子问题轨迹测试 | E5 |
| TRIGGER-001 | 3 | 第二轮触发规则正确 | 参数化纯函数 | E6 |
| STOP-001 | 3 | 停止原因枚举与优先级 | 参数化纯函数 | E7 |
| REFUSAL-001 | 3 | 无证据不生成无依据报告 | 固定无证据fixture | E8 |
| EVIDENCE-001 | 3 | Evidence Table确定构造 | snapshot/属性测试 | E9 |
| SEC-001 | 3 | Prompt Injection不能改变范围/工具 | 恶意文档fixture | E10 |
| SEC-002 | 3 | 禁止工具不可调用 | allowlist轨迹断言 | E10 |
| FALLBACK-001 | 3 | 确定性Workflow保持同一契约 | 双实现契约测试 | E11 |
| REPLAY-001 | 3–4 | 相同轨迹得到相同决定 | 离线重复回放 | F1 |
| DATASET-001 | 4 | 24题字段完整 | Schema校验 | F2 |
| DATASET-002 | 4 | 二次盲审和歧义排除 | 标注审计脚本/报告 | F2 |
| EVAL-001 | 4 | 三组对照控制变量一致 | run manifest校验 | F3 |
| EVAL-002 | 4 | 报告候选/Recall/MRR/延迟/调用/成本 | 指标单测+报告Schema | F3 |
| CITE-001 | 4 | Citation三层评分 | gold fixture指标测试 | F4 |
| LABEL-001 | 4 | answer/refusal混淆矩阵 | 指标测试 | F5 |
| CI-001 | 4 | CI无Key无付费请求 | 空Key+网络Provider禁用 | G1 |
| PRIV-001 | 1–4 | 日志/Trace/错误不泄密 | 捕获输出敏感扫描 | G2 |
| DEEPSEEK-001 | 0 | 冒烟协议完整且状态待验证 | 文档Schema检查 | G3 |
| PROVIDER-001 | 4 | 真实Provider必须显式授权 | 命令门禁/运行清单 | G4 |
| QUALITY-001 | 1–4 | 旧指标无无解释下降 | 10文档/50题回归 | A1 |
| COVERAGE-001 | 1–4 | branch-aware覆盖率不低于85% | CI覆盖率门禁 | G1 |

## 3. 建议测试文件

实现时按现有目录风格微调，职责保持分离：

```text
tests/unit/test_ingestion_state_machines.py
tests/unit/test_chunk_identity.py
tests/unit/test_agent_decision_kernel.py
tests/unit/test_agent_metrics.py
tests/integration/test_schema_migrations.py
tests/integration/test_async_documents_api.py
tests/integration/test_ingestion_saga.py
tests/integration/test_sqlite_concurrency.py
tests/integration/test_single_worker_recovery.py
tests/integration/test_qdrant_server.py
tests/integration/test_investigations_api.py
tests/security/test_agent_scope_and_tools.py
tests/security/test_trace_privacy.py
tests/evaluation/test_agent_fixtures.py
tests/evaluation/test_trajectory_replay.py
tests/system/test_compose_smoke.py
```

故障注入优先使用Fake Provider/Fake Storage。只保留少量真实进程退出、Worker重启和Qdrant Server集成测试，避免测试体系过度复杂。

## 4. 阶段门禁

### 阶段0

- 10份V3文档一致；
- API、状态机、数据模型、验收样例与测试矩阵可互相映射；
- P0不存在Approval、Draft、归档、取消、Lease/Heartbeat/Generation/Fencing实现要求；
- DeepSeek真实冒烟标记待验证；
- 文档秘密扫描和`git diff --check`通过。

### 阶段1：Qdrant Server与Compose

- COMP、QD、COMPOSE通过；
- V1状态码和响应不变；
- Compose只有API、一个Worker和Qdrant；
- 不调用真实Provider。

### 阶段2：异步摄取

- IDEM、SAGA、FILE、RETRY、MUTEX、CLAIM、RECOVER、CHUNK、VIS、COMMIT、DB、DELETE-001/002、CANCEL-ABSENT全部通过；
- 旧回归和覆盖率门禁通过；
- 通过后才允许阶段3 Agent开发。

### 阶段3：两轮Agent

- INV、CLARIFY、SCOPE、ROUND、BUDGET、TRIGGER、STOP、REFUSAL、EVIDENCE、SEC、REPLAY通过；
- 范围越界率为0；
- 若使用确定性Workflow降级，FALLBACK也必须通过。

### 阶段4：评测与交付

- DATASET、EVAL、CITE、LABEL、CI、PRIV、QUALITY、COVERAGE通过；
- 24题标注、二次盲审和歧义处理完成；
- 三组对照报告含完整分母和配置；
- PROVIDER可在单独授权后执行；未执行时README明确边界。

## 5. P1测试，不阻塞P0

- 多Worker所有权、Lease过期、Heartbeat和晚到Worker Fencing；
- Generation可见性和网络分区；
- Job/Investigation协作式取消；
- Draft、Approval、正式归档和身份保护；
- Redis/PostgreSQL、多租户和完整并发性能；
- Reranker、GraphRAG和长期监控。
