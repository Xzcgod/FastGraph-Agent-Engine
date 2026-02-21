"""DuckDuckGo search tool for LangGraph.
# 模块文档字符串：描述该模块提供了一个 DuckDuckGo 搜索工具，
# 可用于 LangGraph 执行网络搜索，最多返回 10 条结果，并能优雅处理错误。
"""

from langchain_community.tools import DuckDuckGoSearchResults
# 从 langchain_community.tools 导入 DuckDuckGoSearchResults 类，
# 这是一个预构建的 DuckDuckGo 搜索工具，封装了搜索逻辑。
duckduckgo_search_tool = DuckDuckGoSearchResults(num_results=10, handle_tool_error=True)
# 创建 DuckDuckGoSearchResults 的实例，并配置：
# - num_results=10：每次搜索最多返回 10 条结果。
# - handle_tool_error=True：当工具调用出错时，自动处理异常并返回错误信息，而不是抛出异常。
# 这个实例将作为导出的工具供其他模块使用。