"""说明本模块存放助手提示词相关功能"""

import os
from datetime import datetime

from app.core.config import settings


def load_system_prompt(**kwargs):
    """加载系统提示模板并用传入的参数进行格式化。"""
    with open(os.path.join(os.path.dirname(__file__), "system.md"), "r", encoding="utf-8") as f:
        template = f.read()

        # 准备默认参数
        default_kwargs = {
            "agent_name": f"{settings.PROJECT_NAME} Agent",
            "current_date_and_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user_id": "unknown",
            "summary": "",
            # ✅ 新增默认值，防止报错
            "custom_instructions": ""
        }

        # 合并传入的参数
        format_kwargs = {**default_kwargs, **kwargs}

        return template.format(**format_kwargs)