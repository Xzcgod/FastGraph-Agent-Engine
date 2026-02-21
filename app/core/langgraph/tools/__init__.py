from langchain_core.tools import BaseTool
from app.core.logging import logger

# 导入具体的工具实例
from .tavily_search import tavily_search_tool
from .duckduckgo_search import duckduckgo_search_tool
from .memory_tools import save_memory_tool, search_memory_tool
from .email_tools import prepare_email_tool, send_email_tool
from .rag_tool import knowledge_base_tool
from .code_interpreter import python_repl_tool, PYTHON_REPL_AVAILABLE

# 定义基础工具（默认开启）
base_tools = [duckduckgo_search_tool]

# ========================
# 完整工具注册表
# key = feature flag 名称（与 FeatureFlags schema 字段名一一对应）
# value = 该 feature 激活时挂载的工具列表
# ========================
all_tools_map: dict[str, list[BaseTool]] = {
    # 联网搜索（Tavily，内部已实现无 Key 自动降级 DuckDuckGo）
    "web_search": [tavily_search_tool],

    # 长期记忆工具（Agent 主动保存 / 检索）
    "memory_tools": [save_memory_tool, search_memory_tool],

    # 邮件助手（含 Human-in-the-loop 审批）
    "email_assistant": [prepare_email_tool, send_email_tool],

    # 知识库检索（RAG 2.0 混合检索 + Rerank）
    "knowledge_base": [knowledge_base_tool],
}

# 代码沙盒：可选依赖，安装后自动注册
if PYTHON_REPL_AVAILABLE and python_repl_tool is not None:
    all_tools_map["code_interpreter"] = [python_repl_tool]
    logger.info("code_interpreter_registered_in_tool_map")
else:
    logger.warning(
        "code_interpreter_not_available",
        hint="pip install langchain-experimental to enable",
    )

logger.info(
    "tool_registry_initialized",
    base_tool_count=len(base_tools),
    feature_keys=list(all_tools_map.keys()),
)

__all__ = ["base_tools", "all_tools_map"]