# Evaluation tests

这些测试验证 `evaluation/` 中的合成语料结构，并运行完整的离线 RAG 评估门槛。评估使用临时 SQLite、Qdrant 和上传目录，不读取真实 `.env`，也不调用云端 API。
