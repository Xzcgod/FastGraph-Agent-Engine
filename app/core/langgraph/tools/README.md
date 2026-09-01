# app/core/langgraph/tools/ — Agent 工具集

本目录是 **LLM 可调用的工具集合**，通过 Feature Flag 动态挂载（最小权限原则）。工具由 `graph.py` 的 `_call_model` 按需 `bind_tools` 注入 LLM，由 `ToolNode` 执行。

## 目录结构

```
tools/
├── __init__.py            # 工具注册中心：base_tools + all_tools_map
├── duckduckgo_search.py   # DuckDuckGo 搜索（基础工具，无需 Key）
├── tavily_search.py       # Tavily 搜索（无 Key 自动降级 DuckDuckGo）
├── memory_tools.py        # 长期记忆：save_memory / search_memory
├── email_tools.py         # 邮件助手：prepare_email / send_email（HITL）
├── rag_tool.py            # 知识库检索：knowledge_base_search
└── code_interpreter.py    # Python 代码沙盒（可选依赖）
```

## 工具与 Feature Flag 映射

| Feature Flag | 工具 | 说明 |
|---|---|---|
| （基础工具） | `duckduckgo_search_tool` | 始终可用，不依赖任何 API Key |
| `web_search` | `tavily_search_tool` | 联网搜索，无 Key 降级 DuckDuckGo |
| `memory_tools` | `save_memory_tool` + `search_memory_tool` | 长期记忆存取 |
| `email_assistant` | `prepare_email_tool` + `send_email_tool` | 邮件，含 interrupt 审批 |
| `knowledge_base` | `knowledge_base_tool` | 知识库检索（kbIds 通过 InjectedState 注入） |
| `code_interpreter` | `python_repl_tool` | Python 沙盒（需 `langchain-experimental`） |

## 阅读理解路线

1. **`__init__.py`** — 先看注册中心：`base_tools`（始终可用）与 `all_tools_map`（feature → 工具列表）。这是「动态挂载」的枢纽。
2. **`duckduckgo_search.py` + `tavily_search.py`** — 看搜索工具，理解无 Key 降级模式。
3. **`memory_tools.py`** — 看长期记忆：`@tool` 装饰器，直接读写 `memory` 表。
4. **`email_tools.py`** — 看 HITL：`prepare_email` 触发 `interrupt()` 暂停，`send_email` 走 SMTP。这是「人工审批」机制的实现。
5. **`rag_tool.py`** — 看知识库检索：`@tool` + `InjectedState("knowledge_kb_ids")` 从图状态注入检索范围（kbIds 对 LLM 不可见），调 knowledge-service 检索。
6. **`code_interpreter.py`** — 看代码沙盒：可选依赖，`try/except ImportError` 降级。

> 关键点：`rag_tool.py` 的 `InjectedState` 参数（kbIds/topK/minScore）不会出现在 LLM 的工具 schema 里，而是由 `ToolNode` 执行时从 `GraphState` 注入——这是「按 Agent 绑定知识库 + 工具调用检索」的核心机制。
