"""定义用户表的数据库结构，并处理密码安全，这个对应数据库中的'user'表格"""

from typing import (
    TYPE_CHECKING,
    List,
)

import bcrypt #专门用于哈希密码加密的库
from sqlmodel import (
    Field,
    Relationship,
)

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.session import Session


class User(BaseModel, table=True):
    """
    # 定义 User 类，继承自 BaseModel，并且设置 table=True 表示这是一个 SQLModel 的数据库表模型。
    # 文档字符串说明了模型的用途和各个属性：
    # - id: 主键，用户的唯一标识。
    # - email: 用户的邮箱，必须唯一。
    # - hashed_password: 经过 bcrypt 哈希加密后的密码（绝不存储明文密码）。
    # - created_at: 用户账户创建时间（从 BaseModel 继承而来）。
    # - sessions: 与该用户关联的所有聊天会话（一对多关系）。
    """

    id: int = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str# 存储经过 bcrypt 哈希后的密码字符串。注意：这里直接存储哈希值，而不是明文密码。
    sessions: List["Session"] = Relationship(back_populates="user")

    # 定义与 Session 模型的一对多关系：
    # - List["Session"] 表示该用户可以有多个会话对象。
    # - Relationship(back_populates="user") 指定反向关系，即在 Session 模型中会有一个名为 "user" 的属性指向所属的 User 对象。
    # 这样，通过 user.sessions 可以获取该用户的所有会话，通过 session.user 可以获取会话对应的用户。
    def verify_password(self, password: str) -> bool:
        """用于验证用户输入的明文密码是否与存储的哈希值匹配"""
        return bcrypt.checkpw(password.encode("utf-8"), self.hashed_password.encode("utf-8"))

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
 # 静态方法：用于对明文密码进行 bcrypt 哈希加密，通常在用户注册或修改密码时调用。
    # - bcrypt.gensalt() 生成一个随机的盐值（salt），增加哈希的强度，防止彩虹表攻击。
    # - bcrypt.hashpw(password.encode("utf-8"), salt) 使用盐值对密码进行哈希，返回一个字节串。
    # - 最后通过 decode("utf-8") 将字节串转换为字符串，以便存储到数据库的 hashed_password 字段。
    # 注意：每次调用 gensalt() 都会生成不同的盐，因此即使两个用户密码相同，最终哈希值也不同，提高了安全性。

# Avoid circular imports
from app.models.session import Session  # noqa: E402