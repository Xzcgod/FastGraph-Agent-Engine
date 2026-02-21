"""这个对应了应用的会话模型"""

from typing import (
    TYPE_CHECKING,#一特殊的变量，只在类型检查时候为True,运行时候为false,避免循环导入
    List,
)

from sqlmodel import (
    Field,
    Relationship,#用于定义模型之间的关系，1对多，多对1等
)

from app.models.base import BaseModel
# 仅在类型检查时导入 User 模型，避免运行时循环导入。
# 因为 Session 中使用了 User 类型（在 Relationship 和类型注解中），
# 而 User 模型也可能引用了 Session，如果直接在文件顶部导入 User，会造成循环依赖。
# 使用 TYPE_CHECKING 条件导入，可以在类型检查时获得正确的类型提示，但运行时不会真正导入，
# 从而避免了循环导入错误。
if TYPE_CHECKING:
    from app.models.user import User


class Session(BaseModel, table=True):
    """# 定义 Session 类，继承自 BaseModel，并设置 table=True 表示这是一个 SQLModel 的数据库表模型。
    # 文档字符串说明了模型的用途和各个属性：
    Attributes:
        id: 主键
        user_id: 外键，关联到用户表的id,表示改会话属于哪个用户
        name: 会话名称，默认为空字符串，可以由用户自定义
        created_at: 会话创建时间
        messages: 与该会话关联的消息列表（一对多关系，本文件中未定义）
        user: 反向关系，拥有改会话的用户对象
    """

    id: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    name: str = Field(default="")
    user: "User" = Relationship(back_populates="sessions")
    # - "User" 是类型注解，指向 User 模型。
    # - Relationship(back_populates="sessions") 表示在 User 模型中有一个名为 "sessions" 的属性，
    #   它包含了该用户的所有会话（一对多关系中的“多”方）。
    # 通过这个关系，可以方便地从会话对象访问其所属的用户：session.user
    # 同时，通过 user.sessions 可以获取该用户的所有会话。