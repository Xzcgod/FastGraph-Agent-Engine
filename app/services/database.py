"""数据库服务层 - 封装所有 CRUD 操作

修复记录：
- [Fix-Table] 显式导入 Memory 和 KnowledgeChunk 模型。
  确保 create_db_and_tables() 能自动创建 'memory' 和 'knowledge_chunk' 表。
"""

from typing import (
    List,
    Optional,
)

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import QueuePool
from sqlmodel import (
    Session,
    SQLModel,
    create_engine,
    select,
)

from app.core.config import settings
from app.core.logging import logger
# ✅ [Fix] 显式导入 KnowledgeChunk 以便建表
from app.models.knowledge import KnowledgeChunk
# ✅ [Fix] 显式导入 Memory 以便建表
from app.models.memory import Memory
from app.models.session import Session as ChatSession
from app.models.thread import Thread
from app.models.user import User


class DatabaseService:
    def __init__(self):
        # 初始化数据库引擎
        database_url = (
            f"postgresql+psycopg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
            f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
        )
        self.engine = create_engine(
            database_url,
            pool_size=settings.POSTGRES_POOL_SIZE,
            max_overflow=settings.POSTGRES_MAX_OVERFLOW,
            poolclass=QueuePool,
        )

    def create_db_and_tables(self):
        """创建数据库表"""
        SQLModel.metadata.create_all(self.engine)

    # ---------- User Operations ----------
    async def get_user_by_email(self, email: str) -> Optional[User]:
        with Session(self.engine) as session:
            statement = select(User).where(User.email == email)
            return session.exec(statement).first()

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        with Session(self.engine) as session:
            return session.get(User, user_id)

    async def create_user(self, user: User) -> User:
        try:
            with Session(self.engine) as session:
                session.add(user)
                session.commit()
                session.refresh(user)
                return user
        except SQLAlchemyError as e:
            logger.error("create_user_failed", error=str(e))
            raise HTTPException(
                status_code=400, detail="User already exists or database error"
            )

    # ---------- Session Operations ----------
    async def create_session(
        self, user_id: int, name: str, session_id: str
    ) -> ChatSession:
        with Session(self.engine) as session:
            # 1. 创建会话记录
            chat_session = ChatSession(id=session_id, user_id=user_id, name=name)
            session.add(chat_session)

            # 2. 同时创建 LangGraph 需要的 Thread 记录
            thread = Thread(id=session_id)
            session.add(thread)

            session.commit()
            session.refresh(chat_session)
            return chat_session

    async def get_user_sessions(self, user_id: int) -> List[ChatSession]:
        with Session(self.engine) as session:
            statement = (
                select(ChatSession)
                .where(ChatSession.user_id == user_id)
                .order_by(ChatSession.created_at.desc())
            )
            return session.exec(statement).all()

    async def get_session(self, session_id: str) -> Optional[ChatSession]:
        with Session(self.engine) as session:
            return session.get(ChatSession, session_id)

    async def delete_session(self, session_id: str):
        with Session(self.engine) as session:
            chat_session = session.get(ChatSession, session_id)
            if chat_session:
                session.delete(chat_session)
                session.commit()

    async def health_check(self) -> bool:
        try:
            with Session(self.engine) as session:
                session.exec(select(1)).first()
            return True
        except Exception:
            return False


# 单例实例
database_service = DatabaseService()