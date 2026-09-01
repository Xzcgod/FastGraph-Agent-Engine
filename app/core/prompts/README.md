# app/core/prompts/ — 提示词模板

本目录是**系统提示词（System Prompt）**的模板与加载器，负责把模板文件格式化并注入动态参数。

## 目录结构

```
prompts/
├── system.md     # 系统提示词模板（含占位符）
└── __init__.py   # load_system_prompt 加载器
```

## 各文件职责

| 文件 | 作用 |
|---|---|
| `system.md` | Markdown 格式的模板，含 `{agent_name}`、`{current_date_and_time}`、`{user_id}`、`{summary}`、`{custom_instructions}` 占位符 |
| `__init__.py` | `load_system_prompt(**kwargs)`：读取模板 → 合并默认参数 → `format()` 替换占位符 |

## 阅读理解路线

1. **`system.md`** — 先看模板：定义了角色、核心指令、可用工具说明、用户信息、历史摘要、动态指令区。
2. **`__init__.py`** — 看加载器：理解默认参数兜底（防止占位符缺失报错）和动态参数覆盖。

> 关键点：`system.md` 的「可用工具说明」列出了所有工具（包括 `knowledge_base_search`），与 `tools/__init__.py` 的注册表对应。`load_system_prompt` 在 `graph.py:_call_model` 里被调用，`custom_instructions` 参数承载了 Agent 指令（AGENT PROFILE + KNOWLEDGE POLICY）和动态指令。
