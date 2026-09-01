# app/services/ — 业务服务层

本目录是**业务逻辑核心**：数据库访问、LLM 模型路由、平台 Agent 配置、knowledge-service 代理。路由层（`api/`）是薄壳，真正的逻辑都在这里。

## 目录结构

```
services/
├── __init__.py         # 导出 database_service、llm_service 等
├── database.py         # 数据库服务：建表 + 用户/会话 CRUD
├── llm.py              # LLM 注册表与服务：模型路由、重试、故障切换
├── agent_config.py     # 平台 Agent 配置服务：读写 + 运行时准备
└── knowledge_client.py # knowledge-service 客户端：HTTP 代理适配层
```

## 各文件职责

| 文件 | 单例 | 作用 |
|---|---|---|
| `database.py` | `database_service` | SQLModel 引擎、`create_db_and_tables`、用户/会话 CRUD、健康检查 |
| `llm.py` | `llm_service` / `LLMRegistry` | 注册表管理可用模型，服务层负责调用 + tenacity 重试 + 故障切换 |
| `agent_config.py` | `agent_config_service` | 平台 Agent 的 CRUD、状态流转、`prepare_runtime_messages`（运行时准备） |
| `knowledge_client.py` | `knowledge_service_client` | 访问独立 knowledge-service 的唯一适配层（Token/操作人/Trace 透传） |

## 阅读理解路线

1. **`database.py`** — 先看数据访问层：建表、用户/会话 CRUD，理解同步引擎 + 异步方法的模式。
2. **`llm.py`** — 看 LLM 模型路由：`LLMRegistry`（模型名 → 实例）与 `LLMService`（调用/重试/切换）。理解 `LLMRegistry.get(model_name)` 的「查表 + 动态创建」逻辑。
3. **`agent_config.py`** — 看平台 Agent 核心：配置读写、状态流转，重点是 `prepare_runtime_messages` 如何把 Agent 配置（features/knowledge/model_name）整理成运行时参数。
4. **`knowledge_client.py`** — 看 knowledge-service 代理：理解 `X-KB-Service-Token`、操作人透传、错误收敛。

> 关键串联点：`agent_config.py:prepare_runtime_messages` 返回的 `model_name` 会流向 `llm.py` 的 `LLMRegistry.get()` 解析成具体模型实例（中间经 `core/langgraph/graph.py`）。`knowledge_client.py` 则被 `agent_config.py`（校验知识库）和 `core/langgraph/tools/rag_tool.py`（检索工具）共同调用。
