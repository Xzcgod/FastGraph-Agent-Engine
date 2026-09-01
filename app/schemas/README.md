# app/schemas/ — API 数据契约（Pydantic）

本目录是**请求/响应的数据契约**定义层，使用 Pydantic 做入参校验、出参序列化。与 `app/models/`（数据库表）分离，专注于「API 长什么样」。

## 目录结构

```
schemas/
├── __init__.py  # 导出常用 schema
├── auth.py      # 认证相关：Token、UserCreate、UserResponse、MeResponse、SessionResponse
├── chat.py      # 聊天相关：Message、FeatureFlags、ChatRequest、ChatResponse、EmailApprovalRequest
├── graph.py     # 图状态：GraphState（LangGraph 状态 Schema）
└── agent.py     # Agent 配置：AgentFeatureConfig、AgentKnowledgeConfig、PlatformAgentWrite 等
```

## 各文件职责

| 文件 | 关键类 | 作用 |
|---|---|---|
| `auth.py` | `TokenResponse`/`UserResponse`/`MeResponse`/`SessionResponse` | 认证与用户信息契约，含 `is_admin` 角色标记 |
| `chat.py` | `Message`/`FeatureFlags`/`ChatRequest` | 聊天请求契约，`FeatureFlags` 是旧通用聊天的工具开关 |
| `graph.py` | `GraphState` | LangGraph 状态定义：消息、摘要、功能开关、Agent 指令、知识库配置 |
| `agent.py` | `AgentFeatureConfig`/`AgentKnowledgeConfig`/`PlatformAgentWrite` | 平台 Agent 配置契约，定义工具开关与知识库绑定 |

## 阅读理解路线

1. **`auth.py`** — 看认证契约：`UserResponse` 的 `token` 是 `Token` 对象，`is_admin` 标记管理员/普通用户。
2. **`chat.py`** — 看消息模型（`Message`）和旧聊天开关（`FeatureFlags`），注意 `Message.content` 有 XSS 防护校验。
3. **`graph.py`** — 看 `GraphState`：这是 LangGraph 图的状态 Schema，`knowledge_kb_ids`/`knowledge_top_k`/`knowledge_score_threshold` 承载知识库检索配置。
4. **`agent.py`** — 看 Agent 配置契约：`AgentKnowledgeConfig`（`enabled`/`kb_ids`/`top_k`/`score_threshold`）是知识库绑定的核心，`PlatformAgentWrite` 是管理端创建/编辑的请求体。

> 记忆点：`schemas/agent.py` 的 `AgentKnowledgeConfig` 与 `models/agent.py` 的 `config_json.knowledge` 对应——一个定义契约，一个存数据库。
