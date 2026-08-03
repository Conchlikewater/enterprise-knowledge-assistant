# Enterprise Knowledge Assistant（RAG V1）

这是一个面向学习和本地演示的企业知识助手后端。V1 将通过 FastAPI 提供 TXT/PDF 同步摄取、限定文档范围的向量检索，以及由检索结果生成的结构化引用。

## 当前阶段：Day 7 同步摄取事务

目前已建立模块边界、类型化配置、统一错误格式、健康检查、核心领域模型、SQLite 文档仓库、安全的 TXT/PDF 文档处理层、本地持久化 Qdrant、OpenAI embedding provider，以及带补偿回滚的同步摄取服务。HTTP 上传接口和 LLM 实现尚未接入。

```text
app/api              HTTP 路由与应用入口
app/core             配置、异常和全局错误处理
app/domain           与框架无关的核心数据模型
app/providers        OpenAI embedding 实现与 LLM 接口
app/storage          SQLite 文档仓库与本地 Qdrant 向量存储
app/services         同步摄取与后续业务流程编排
app/document_processing  文件校验、哈希、TXT/PDF 解析与切块
tests                单元、集成和评估测试
data                 本地运行数据（不提交数据库内容）
```

## API 骨架

- `GET /health`：返回服务名称、版本，以及应用和 SQLite 文档仓库的健康状态。
- 其余 `/api/v1` 接口将在后续阶段按 `docs/architecture_log.md` 实现。

所有应用错误使用以下稳定结构：

```json
{
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "The requested document was not found.",
    "request_id": "..."
  }
}
```

## 环境说明

- 当前 Python：3.12，项目专用环境为 `.venv`
- 不复用 `02_foundations` 的虚拟环境
- 已安装轻量 Web、测试、文本型 PDF、Qdrant 和 OpenAI 官方 SDK
- embedding 使用云端 API；本机未安装模型，LLM provider 尚未接入
- 尚未安装 OCR 或大型 RAG 框架
- `.env.example` 只包含非敏感默认值；真实 `.env` 不提交 Git
- API Key 只从环境或 `.env` 读取，不进入日志、响应或 Settings 的字符串表示
- 摄取失败会删除该次写入的向量和上传文件，并保留状态为 `failed` 的文档记录用于排查

依赖清单写在 `requirements.txt` 和 `requirements-dev.txt`，新增依赖前必须先说明用途和范围。

## 架构约束

- 路由只负责 HTTP；业务流程进入 services。
- domain 不依赖 FastAPI、Qdrant 或模型 SDK。
- providers/storage 通过小接口隔离具体实现。
- 不向响应或日志泄露文档内容、问题、提示词、密钥或本地路径。
- V1 不包含 Docker、任务队列、认证、多租户、OCR、Agent、MCP 或前端。
