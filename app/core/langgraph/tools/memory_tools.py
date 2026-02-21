import json
from typing import List, Optional
from langchain_core.tools import tool
from sqlmodel import Session, select
from app.services.database import database_service
from app.models.memory import Memory
from app.core.logging import logger

@tool
def save_memory_tool(content: str, user_id: str) -> str:
    """将重要信息保存到用户的长期记忆中。"""
    try:
        # 兼容处理：尝试转 int，失败则保留原值（适应不同 ID 类型）
        try:
            uid = int(user_id)
        except ValueError:
            uid = user_id

        with Session(database_service.engine) as session:
            memory = Memory(user_id=uid, content=content.strip())
            session.add(memory)
            session.commit()
            
            logger.info("memory_saved_to_db", user_id=uid, content=content[:50])
            return f"✅ 记忆已成功保存：'{content}'"
    except Exception as e:
        logger.error("save_memory_failed", error=str(e), user_id=user_id)
        return f"❌ 保存失败：{str(e)}"

@tool
def search_memory_tool(query: str, user_id: str) -> str:
    """在用户的长期记忆中搜索相关信息。"""
    try:
        try:
            uid = int(user_id)
        except ValueError:
            uid = user_id

        with Session(database_service.engine) as session:
            # 简单查全量，确保能搜到
            statement = select(Memory).where(Memory.user_id == uid)
            results = session.exec(statement).all()
            
            if not results:
                return "没有找到相关的历史记忆。"

            memory_texts = [m.content for m in results]
            formatted_results = "\n".join([f"- {text}" for text in memory_texts])
            return f"找到以下相关记忆：\n{formatted_results}"
            
    except Exception as e:
        logger.error("search_memory_failed", error=str(e), user_id=user_id)
        return f"检索记忆时出错：{str(e)}"