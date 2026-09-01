# app/core/langgraph/ — Agent 执行引擎

本目录是 **AI Agent 的「大脑」**：基于 LangGraph 构建状态图，管理 LLM 调用、工具循环、对话状态持久化（Checkpoint）和 Human-in-the-loop（人工审批）。

## 目录结构

```
langgraph/
├── graph.py  # Chatbot 状态图：agent ⇄ tools 循环、流式、恢复、历史
└── tools/    # 工具集合（见子目录 README）
```

## graph.py 核心内容

| 组件 | 作用 |
|---|---|
| `Chatbot` 类 | Agent 执行引擎（全局单例 `chatbot`），管理图构建、连接池、编译 |
| `_call_model` | agent 节点：按 `active_features` 动态组装工具 + 注入指令 + 调用 LLM |
| `create_graph` | 构建 `StateGraph`：`START → agent → (tools ⇄ agent) → END`，绑定 Checkpointer |
| `astream_response` | 流式输出：逐块 yield AI 回复 + 工具调用提示 + 中断信号 |
| `get_response` | 普通（非流式）对话 |
| `resume_graph` | HITL 恢复：发送 `Command(resume=...)` 继续被中断的图 |
| `get/clear_chat_history` | 读写/清空 Checkpoint 中的历史 |

## 阅读理解路线

1. **`Chatbot.__init__` 与 `initialize`** — 看延迟初始化和连接池/Checkpointer 的建立。
2. **`_call_model`** — 核心：理解「动态组装工具 → 注入知识库/代码指令 → `prepare_messages` → `model.invoke`」的完整 LLM 调用链。注意 `model_name` 如何用 `LLMRegistry.get()` 解析。
3. **`create_graph`** — 看图结构：`should_continue` 根据最后一条消息是否含 `tool_calls` 决定「继续调工具」还是「结束」。
4. **`astream_response`** — 看流式：阶段 1 逐块输出，阶段 2 检查 `snapshot.next` 判断是否被 interrupt 中断。
5. **`resume_graph`** — 看 HITL：邮件审批后如何恢复执行。

> 关键串联点：`graph.py` 是 `api/agents.py`、`services/agent_config.py`、`services/llm.py`、`utils/graph.py`、`tools/` 的汇合处——它接收 Agent 配置（features/knowledge/model_name），组装工具，调用 LLM。
