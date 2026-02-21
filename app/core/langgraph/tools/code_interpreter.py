"""Python 代码解释器工具 - 允许 Agent 编写并执行 Python 代码。

使用场景：
- 复杂数学计算
- 数据处理与分析
- 代码验证与调试

安全注意：
- 当前在 Docker 容器内运行，需确保容器网络隔离
- 后续可升级为 E2B 沙盒以获得更强的安全隔离
"""

from app.core.logging import logger

try:
    from langchain_experimental.tools import PythonREPLTool

    python_repl_tool = PythonREPLTool(
        description=(
            "Python 代码解释器。用于执行 Python 代码来完成数学计算、数据处理等任务。"
            "输入：Python 代码字符串。输出：代码执行结果。"
            "⚠️ 注意：仅用于合法的计算和数据处理，不执行网络请求或文件操作。"
        )
    )
    logger.info("python_repl_tool_initialized")
    PYTHON_REPL_AVAILABLE = True

except ImportError:
    logger.warning(
        "langchain_experimental_not_installed_python_repl_unavailable",
    )
    python_repl_tool = None
    PYTHON_REPL_AVAILABLE = False
