# app/models/ — 数据模型（ORM）

本目录是**数据库表结构**的定义层，使用 SQLModel（Pydantic + SQLAlchemy）。每个类对应一张 PostgreSQL 表。与 `app/schemas/`（API 契约）分离，两者可独立演化。

## 目录结构

```
models/
├── base.py      # BaseModel 基类（公共 created_at 字段，非表）
├── user.py      # 用户表 user
├── session.py   # 会话表 session
├── thread.py    # LangGraph 线程表 thread
├── memory.py    # 长期记忆表 memory
└── agent.py     # 平台 Agent 表 platform_agent
```

## 各文件职责

| 文件 | 表名 | 作用 |
|---|---|---|
| `base.py` | （基类） | `BaseModel` Mixin，提供 `created_at` 公共字段 |
| `user.py` | `user` | 用户：`email`（唯一）+ `hashed_password`，含 bcrypt 哈希/校验 |
| `session.py` | `session` | 会话：关联 user，`id` 同时作为 LangGraph `thread_id` |
| `thread.py` | `thread` | 线程：与 session 一一对应，供 LangGraph Checkpoint 持久化 |
| `memory.py` | `memory` | 长期记忆：`user_id` + `content`（Agent 主动存取） |
| `agent.py` | `platform_agent` | 平台 Agent：`agent_code`、`model_name`、`features_json`、`config_json`、`status`（draft/published/offline） |

## 阅读理解路线

1. **`base.py`** — 先看公共基类（只有 `created_at`）。
2. **`user.py`** — 看用户模型，理解密码哈希与验证（bcrypt + 盐）。
3. **`session.py` + `thread.py`** — 一起看：`session.id` 与 `thread.id` 相同，建立「会话 ↔ LangGraph 线程」的对应关系。
4. **`memory.py`** — 看长期记忆的简单表结构。
5. **`agent.py`** — 看平台 Agent 表：这是三层架构的核心表，`features_json` 存工具开关、`config_json` 存知识库配置（`config_json.knowledge`）。

> 记忆点：`models/` 关注「数据库怎么存」，`schemas/` 关注「API 怎么传」。Agent 的 `features_json`/`config_json` 是 JSON 列，承载了动态配置，理解它们是理解 Agent 配置的关键。
