from datetime import UTC, datetime
from typing import List, Optional

from pgvector.sqlalchemy import Vector
from sqlmodel import (
    Field,
    SQLModel,
)


class KnowledgeChunk(SQLModel, table=True):
    """知识库切片表：存储文档被切分后的片段及其向量"""

    __tablename__ = "knowledge_chunk"

    id: Optional[int] = Field(default=None, primary_key=True)
    content: str = Field(nullable=False)  # 切片文本内容
    source: str = Field(nullable=False)  # 来源文件名 (e.g. "manual.pdf")

    # 向量字段 (假设使用 BAAI/bge-m3，维度为 1024)
    # 如果你使用其他 embedding 模型，请调整维度 (如 OpenAI text-embedding-3-small 是 1536)
    embedding: List[float] = Field(sa_type=Vector(1024))

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), nullable=False
    )