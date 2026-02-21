from datetime import UTC, datetime
from typing import Optional
from sqlmodel import Field, SQLModel

class Memory(SQLModel, table=True):
    """用户长期记忆表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)  # 与 User.id 对应
    content: str = Field(nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False
    )