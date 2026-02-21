"""这个是对应的对话线程模型"""

from datetime import (
    UTC,
    datetime,
)

from sqlmodel import (
    Field,
    SQLModel,
)


class Thread(SQLModel, table=True):
    """定义了Thread类，继承自SQLModel,并设置table=true表示这是一个数据库表模型
    """

    id: str = Field(primary_key=True)#这个是主键，唯一一个对话线程
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))#线程的创建时间