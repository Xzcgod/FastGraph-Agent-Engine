# app/utils/ — 通用工具

本目录是**无状态的通用工具函数**，供路由层和服务层复用。不依赖 FastAPI 请求上下文，多为纯函数。

## 目录结构

```
utils/
├── __init__.py      # 导出
├── auth.py          # JWT 认证：令牌创建/验证 + FastAPI 依赖项
├── graph.py         # 消息处理：标准化、裁剪、System Prompt 注入、Token 计数
└── sanitization.py  # 数据净化：XSS/注入防护、邮箱/密码校验
```

## 各文件职责

| 文件 | 作用 |
|---|---|
| `auth.py` | `create_access_token`、`verify_token`，以及 `get_current_user`、`verify_session_access`、`require_platform_admin` 依赖项 |
| `graph.py` | `prepare_messages`（消息标准化 → Token 裁剪 → 注入 System Prompt）、`get_token_count`、`process_llm_response`、`dump_messages` |
| `sanitization.py` | `sanitize_string`/`sanitize_dict`/`sanitize_list`（XSS/注入防护）、`sanitize_email`、`validate_password_strength` |

## 阅读理解路线

1. **`auth.py`** — 先看认证核心：JWT 的 `sub` 字段既可以是 `user_id`（纯数字）也可以是 `session_id`，`get_current_user` 智能处理两种 token。`require_platform_admin` 是管理员白名单检查。
2. **`graph.py`** — 看消息处理：`prepare_messages` 是 LangGraph 调用 LLM 前的关键预处理，理解「标准化 → 裁剪 → 注入 System Prompt」三步。
3. **`sanitization.py`** — 看安全工具：递归净化字符串/字典/列表，防止 XSS 和注入。

> 记忆点：`utils/auth.py` 的 `require_platform_admin` 与 `api/auth.py` 的 `_is_platform_admin` 都基于 `settings.PLATFORM_ADMIN_EMAILS` 白名单，是「管理员/普通用户」角色的唯一判定来源。
