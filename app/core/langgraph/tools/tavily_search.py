"""
Tavily 搜索工具 - 专为 AI Agent 设计的高质量联网搜索。

本模块为 Agent 提供高级的联网搜索能力：

Tavily 相比 DuckDuckGo 的优势：
    - 专为 AI 设计：返回结构化的搜索结果，噪声更少。
    - 内容解析：自动提取网页正文内容，而非仅提供摘要。
    - 上下文搜索：支持深度搜索（包括子页面内容）。
    - 稳定性更好：不容易被搜索引擎封锁。

降级策略：
    如果 TAVILY_API_KEY 环境变量未配置，自动降级为 DuckDuckGo 搜索。
    这确保即使没有 API Key，Agent 仍然具备基础搜索能力。

获取 API Key：
    访问 https://tavily.com/ 注册并获取免费额度。
"""

from langchain_community.tools.tavily_search import TavilySearchResults

from app.core.config import settings
from app.core.logging import logger


# ============================================================================
# Tavily 搜索工具初始化（带自动降级）
# ============================================================================

if settings.TAVILY_API_KEY:
    # 配置了 API Key → 使用 Tavily 搜索（高质量模式）
    tavily_search_tool = TavilySearchResults(
        max_results=5,
        tavily_api_key=settings.TAVILY_API_KEY,
        description=(
            "使用 Tavily 搜索引擎查询最新的互联网信息。"
            "当需要了解最新事件、实时数据或验证信息时使用此工具。"
            "输入：搜索查询字符串。输出：相关网页内容摘要列表。"
        ),
    )
    logger.info("tavily_search_tool_initialized")
else:
    # 未配置 API Key → 降级为 DuckDuckGo 搜索（免费模式）
    logger.warning("tavily_api_key_not_configured_falling_back_to_duckduckgo")
    from langchain_community.tools import DuckDuckGoSearchResults

    tavily_search_tool = DuckDuckGoSearchResults(
        num_results=5,
        handle_tool_error=True,
        description=(
            "使用 DuckDuckGo 搜索引擎查询互联网信息（降级方案）。"
            "输入：搜索查询字符串。输出：相关网页摘要列表。"
        ),
    )
