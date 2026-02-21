"""它把 `services` 文件夹变成了一个 **Python Package (包)**，并显式地导出了我们希望外部使用的工具。"""

from app.services.database import database_service
from app.services.llm import (
    LLMRegistry,
    llm_service,
)

__all__ = ["database_service", "LLMRegistry", "llm_service"]#数据库服务单例，模型注册表类，模型服务单例