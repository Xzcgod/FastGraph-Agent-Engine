"""Tavily 搜索工具 - 替代 DuckDuckGo，专为 AI 设计，返回干净结构化文本。

优势：
- 不容易被封锁
- 返回内容经过解析，噪声更少
- 支持上下文搜索
"""

from langchain_community.tools.tavily_search import TavilySearchResults

from app.core.config import settings
from app.core.logging import logger

# 初始化 Tavily 搜索工具
# 如果没有配置 API Key，记录警告但不崩溃
if settings.TAVILY_API_KEY:
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
    # 降级方案：如果没有 Tavily Key，使用 DuckDuckGo
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