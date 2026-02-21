"""作用：定义数据库模型的基类。设计目的：
1. 减少重复代码：所有模型都需要 created_at 字段，不如统一写在这里。
2. 统一标准：强制所有时间使用 UTC 时区，防止服务器跨时区导致时间混乱"""

from datetime import datetime, UTC
from typing import List, Optional
from sqlmodel import Field, SQLModel, Relationship #导入类型提示，用于声明字段可能为列表或可选值，SQLModel的基类，所有数据库模型都要继承他，field用于定义字段的属性，最后用于定义模型之间的关系


class BaseModel(SQLModel):
    """Base model with common fields."""

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))