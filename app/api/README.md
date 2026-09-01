# app/api/ — HTTP 路由层

本目录（含 `v1/`）是平台的**对外 REST API 层**，负责接收 HTTP 请求、做参数校验、调用服务层，并返回响应。所有路由统一挂载在 `/api/v1` 前缀下。

## 目录结构

```
api/
└── v1/
    ├── api.py        # 路由聚合中心（挂载各子路由到统一前缀）
    ├── auth.py       # 认证：注册/登录/当前用户/会话管理
    ├── agents.py     # 普通用户：Agent 目录 + 流式调用
    ├── admin.py      # 平台管理员：Agent Catalog + knowledge-service 代理
    └── chatbot.py    # 旧通用聊天：chat/stream/history/resume（含 HITL）
```

## 各文件职责

| 文件 | 前缀 | 职责 |
|---|---|---|
| `api.py` | `/api/v1` | 路由聚合器，`include_router` 挂载下面四个子路由 |
| `auth.py` | `/api/v1/auth` | 注册、登录（OAuth2 表单）、`/me`、会话 CRUD |
| `agents.py` | `/api/v1/agents` | 已发布 Agent 列表、`/{agentId}/chat/stream` 流式调用 |
| `admin.py` | `/api/v1/admin/platform` | 平台 Agent 配置、知识库/文档/入库任务代理 |
| `chatbot.py` | `/api/v1/chatbot` | 旧通用聊天路径，保留向后兼容（含邮件审批 resume） |

## 阅读理解路线

1. **`api.py`** — 先看路由如何聚合，建立「四个子路由 + 各自前缀」的整体地图。
2. **`auth.py`** — 看认证基础：注册/登录返回 JWT，`/me` 返回当前用户角色（管理员/普通用户），会话管理。
3. **`agents.py`** — 看普通用户主流程：如何调用 `agent_config_service.prepare_runtime_messages` 再进入 `chatbot.astream_response` 流式返回。
4. **`admin.py`** — 看平台管理员：Agent Catalog 的 CRUD，以及大量 `knowledge_service_client` 的代理端点（知识库/文档/任务/检索）。
5. **`chatbot.py`** — 看旧路径：它与 `agents.py` 的区别是不经过 Agent 配置，直接用 `FeatureFlags` 开关调用 `Chatbot`。

> 路由层是「薄」的：它们只做参数校验和转发，真正的逻辑在 `app/services/`。阅读时重点关注「每个端点调用了哪个 service」即可。
