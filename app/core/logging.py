"""Logging configuration and setup for the application.
# 文件说明：应用的日志配置和设置。该模块使用 structlog 提供结构化日志，
# 支持不同环境的格式化和处理器：开发环境下提供友好的控制台输出，
# 生产环境下使用 JSON 格式日志。
"""
#实现了完整的结构化日志配置，包括请求上下文绑定、每日 JSONL 文件输出、开发/生产不同格式，并创建了全局 logger 实例。它同样依赖 settings 获取日志目录、环境、日志格式等配置。

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Optional,
)

import structlog

from app.core.config import (
    Environment,
    settings,
)

# 确保日志目录存在
settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
# 从 settings 中获取 LOG_DIR 路径（例如 "logs"），并创建该目录（如果不存在）。
# parents=True 表示如果父目录也不存在，一并创建；exist_ok=True 表示目录已存在时不报错。
# 这样后续写入日志文件时无需担心目录不存在。

# 用于存储请求特定数据的上下文变量
_request_context: ContextVar[Dict[str, Any]] = ContextVar("request_context", default={})
# ContextVar 是 Python 的上下文变量，用于在异步任务中存储请求级别的上下文。
# 这里用来存储当前请求的额外字段（如 user_id, session_id），以便在日志记录时自动添加。
# 默认值为空字典，每个请求可以独立设置和获取，不会相互干扰。

def bind_context(**kwargs: Any) -> None:
    """将键值对绑定到当前请求的上下文中
    """
    current = _request_context.get()# 获取当前上下文字典
    _request_context.set({**current, **kwargs})# 合并新键值对并设置回上下文
    # 例如在中间件中调用 bind_context(user_id=123)，之后所有日志都会自动包含 user_id=123 字段。


def clear_context() -> None:
    """清空当前请求的上下文，通常在一个请求结束时调用，避免数据泄露到下一个请求。"""
    _request_context.set({})


def get_context() -> Dict[str, Any]:
    """返回当前上下文字典，供其他函数使用。
    """
    return _request_context.get()


def add_context_to_event_dict(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """这是一个 structlog 处理器（processor），用于将绑定的上下文变量合并到每个日志事件的字典中
    """
    context = get_context()
    if context:
        event_dict.update(context)
    return event_dict


def get_log_file_path() -> Path:
    """ 根据当前日期和环境生成日志文件路径。
    """
    env_prefix = settings.ENVIRONMENT.value
    # 文件名格式：{环境前缀}-YYYY-MM-DD.jsonl，例如 "development-2025-01-15.jsonl"
    return settings.LOG_DIR / f"{env_prefix}-{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    # 这样每天会生成一个新的文件，方便按日期归档。


class JsonlFileHandler(logging.Handler):
    """自定义 logging 处理器，用于将日志以 JSON 行（JSONL）格式写入每日文件。"""

    def __init__(self, file_path: Path):
        """Initialize the JSONL file handler.

        Args:
            file_path: Path to the log file where entries will be written.
        """
        super().__init__()
        self.file_path = file_path #日志文件路径

    def emit(self, record: logging.LogRecord) -> None:
        """#将单个日志记录写入文件。"""
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),  # 记录创建时间（ISO格式）
                "level": record.levelname,                                         # 日志级别
                "message": record.getMessage(),                                    # 日志消息
                "module": record.module,                                           # 模块名
                "function": record.funcName,                                       # 函数名
                "filename": record.pathname,                                       # 文件路径
                "line": record.lineno,                                             # 行号
                "environment": settings.ENVIRONMENT.value,                         # 当前环境
            }
            # 如果 record 有 extra 属性（包含自定义字段），则更新到条目中
            if hasattr(record, "extra"):
                log_entry.update(record.extra)
            # 以追加模式打开文件，写入 JSON 字符串并换行
            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        """Close the handler."""
        super().close()


def get_structlog_processors(include_file_info: bool = True) -> List[Any]:
    """Get the structlog processors based on configuration.

    Args:
        include_file_info: Whether to include file information in the logs

    Returns:
        List[Any]: List of structlog processors
    """
    # 设置共享的 structlog 处理器列表（用于所有输出）。
    processors = [
        structlog.stdlib.filter_by_level,  # 根据日志级别过滤
        structlog.stdlib.add_logger_name,  # 添加 logger 名称
        structlog.stdlib.add_log_level,  # 添加日志级别
        structlog.stdlib.PositionalArgumentsFormatter(),  # 格式化位置参数
        structlog.processors.TimeStamper(fmt="iso"),  # 添加 ISO 格式的时间戳
        structlog.processors.StackInfoRenderer(),  # 渲染堆栈信息
        structlog.processors.format_exc_info,  # 格式化异常信息
        structlog.processors.UnicodeDecoder(),  # 确保字符串为 Unicode
        # 添加上下文变量（如 user_id, session_id）到每个日志事件
        add_context_to_event_dict,
    ]

    # 如果需要包含文件信息（模块、函数、行号等），添加 CallsiteParameterAdder 处理器
    if include_file_info:
        processors.append(
            structlog.processors.CallsiteParameterAdder(
                {
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                    structlog.processors.CallsiteParameter.MODULE,
                    structlog.processors.CallsiteParameter.PATHNAME,
                }
            )
        )

    # 添加环境信息到每个日志事件（使用 lambda 处理器）
    processors.append(lambda _, __, event_dict: {**event_dict, "environment": settings.ENVIRONMENT.value})

    return processors


def setup_logging() -> None:
    """Configure structlog with different formatters based on environment.

    In development: pretty console output
    In staging/production: structured JSON logs
    """
    # Determine log level based on DEBUG setting
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    
    # Create file handler for JSON logs
    file_handler = JsonlFileHandler(get_log_file_path())
    file_handler.setLevel(log_level)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Get shared processors
    shared_processors = get_structlog_processors(
        # Include detailed file info only in development and test
        include_file_info=settings.ENVIRONMENT
        in [Environment.DEVELOPMENT, Environment.TEST]
    )

    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=[file_handler, console_handler],
    )

    # Configure structlog based on environment
    if settings.LOG_FORMAT == "console":
        # Development-friendly console logging
        structlog.configure(
            processors=[
                *shared_processors,
                # Use ConsoleRenderer for pretty output to the console
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        # Production JSON logging
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )


# Initialize logging
setup_logging()

# Create logger instance
logger = structlog.get_logger()
log_level_name = "DEBUG" if settings.DEBUG else "INFO"
logger.info(
    "logging_initialized",
    environment=settings.ENVIRONMENT.value,
    log_level=log_level_name,
    log_format=settings.LOG_FORMAT,
    debug=settings.DEBUG,
)
