"""定义用户认证、注册、会话相关的 Pydantic 模型，用于请求/响应数据验证和序列化"""

import re
from datetime import datetime

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
)


class Token(BaseModel):
    """用于表示一个 JWT 访问令牌及其元数据，可嵌入其他响应模型中使用。

    Attributes:
        access_token: JWT 访问令牌字符串
        token_type: 令牌类型，固定为 "bearer"
        expires_at: 令牌过期时间戳
    """

    access_token: str = Field(..., description="JWT 访问令牌字符串")
    token_type: str = Field(default="bearer", description="令牌类型，目前仅支持 bearer")
    expires_at: datetime = Field(..., description="令牌过期时间（UTC 时间）")


class TokenResponse(BaseModel):
    """登录接口的响应模型

    与 Token 模型字段相同，但专门用于登录端点返回，便于未来独立调整。

    Attributes:
        access_token: JWT 访问令牌
        token_type: 令牌类型，固定为 "bearer"
        expires_at: 令牌过期时间
    """

    access_token: str = Field(..., description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型，固定为 bearer")
    expires_at: datetime = Field(..., description="令牌过期时间（UTC）")


class UserCreate(BaseModel):
    """用户注册请求模型

    用于接收客户端提交的注册信息，并进行初步格式和强度校验。

    Attributes:
        email: 用户邮箱地址，使用 Pydantic 的 EmailStr 自动校验格式
        password: 用户密码，使用 SecretStr 隐藏原始值，并自定义强度校验
    """

    email: EmailStr = Field(..., description="用户邮箱地址，需符合 Email 格式")
    password: SecretStr = Field(..., description="用户密码，长度 8~64 位，必须包含大小写字母、数字和特殊字符", min_length=8, max_length=64)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: SecretStr) -> SecretStr:
        """自定义密码强度校验器

        在校验器中，从 SecretStr 中取出原始密码字符串，检查其是否满足安全要求。

        Args:
            v: 包装在 SecretStr 中的密码

        Returns:
            验证通过后原样返回 SecretStr 对象

        Raises:
            ValueError: 当密码不满足任何一条强度规则时抛出
        """
        password = v.get_secret_value()# 获取明文密码用于检查

        # 长度检查（虽然 Field 已有 min_length，但此处作为二次保障，并给出具体错误信息）
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")
        # 至少一个大写字母
        if not re.search(r"[A-Z]", password):
            raise ValueError("Password must contain at least one uppercase letter")
        # 至少一个小写字母
        if not re.search(r"[a-z]", password):
            raise ValueError("Password must contain at least one lowercase letter")
        # 至少一个数字
        if not re.search(r"[0-9]", password):
            raise ValueError("Password must contain at least one number")
        # 至少一个特殊字符（这里定义了一组常见特殊字符）
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            raise ValueError("Password must contain at least one special character")

        return v


class UserResponse(BaseModel):
    """"用户操作响应模型（常用于注册或登录成功后的返回）

    包含用户的基本信息和认证令牌，方便客户端后续请求携带认证信息。

    Attributes:
        id: 用户唯一标识（通常为数据库自增 ID）
        email: 用户邮箱
        token: 完整的认证令牌对象（内含 access_token、token_type、expires_at）
    """

    id: int = Field(..., description="用户唯一标识 ID")
    email: str = Field(..., description="用户邮箱地址")
    token: Token = Field(..., description="认证令牌信息，包含 access_token、token_type 和过期时间")


class SessionResponse(BaseModel):
    """会话创建响应模型

    当用户创建新的聊天会话时，返回会话的唯一标识及对应的认证令牌（用于后续消息交互）。

    Attributes:
        session_id: 会话的唯一标识符（例如 UUID 字符串）
        name: 会话名称，默认为空字符串，且经过净化处理
        token: 该会话关联的认证令牌
    """

    session_id: str = Field(..., description="会话的唯一标识符，通常为 UUID")
    name: str = Field(default="", description="会话名称，最长 100 字符，将自动去除可能引起注入的字符", max_length=100)
    token: Token = Field(..., description="该会话的认证令牌，用于后续消息请求的身份验证")

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        """对会话名称进行净化处理

        移除可能用于 XSS 或注入攻击的字符，如尖括号、方括号、引号等。

        Args:
            v: 原始会话名称

        Returns:
            净化后的名称字符串
        """
        #使用正则表达式移除 HTML/XML 标签相关的危险字符
        sanitized = re.sub(r'[<>{}[\]()\'"`]', "", v)
        return sanitized