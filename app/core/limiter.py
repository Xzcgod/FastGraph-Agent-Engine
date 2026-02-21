"""Rate limiting configuration for the application.
# 文件说明：应用限流配置。该模块使用 slowapi 库配置限流，默认限流规则在应用设置中定义。
# 限流基于客户端的远程 IP 地址进行。
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=settings.RATE_LIMIT_DEFAULT)
#此文件只做了一件事：创建 limiter 实例并导出，供其他模块（如路由、中间件）导入使用。它依赖于 config.settings 获取默认限流值