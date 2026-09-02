"""
Knowledge-service 配置。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_env_files() -> None:
    root = Path(__file__).resolve().parents[2]
    app_env = os.getenv("APP_ENV", "development")
    for file_name in (f".env.{app_env}.local", f".env.{app_env}", ".env.local", ".env"):
        env_path = root / file_name
        if env_path.is_file():
            load_dotenv(env_path, override=False)


def database_url_from_postgres_env() -> str:
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "agent_db")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


def first_env_value(*keys: str, default: str = "") -> str:
    for key in keys:
        value = os.getenv(key, "").strip().strip("\"'")
        if value:
            return value
    return default


class Settings:
    def __init__(self) -> None:
        load_env_files()
        self.service_name = os.getenv("KNOWLEDGE_SERVICE_NAME", "knowledge-service")
        self.service_token = os.getenv("KNOWLEDGE_SERVICE_TOKEN", "")
        self.database_url = os.getenv("KNOWLEDGE_DATABASE_URL", database_url_from_postgres_env())
        # embedding 提供方：local（本地 Ollama）/ api（外部 API），据此自主选择端点、密钥与模型。
        # 注意：切换提供方后，存量向量失效，需清空 td_knowledge_chunk 重新入库（见部署文档）。
        self.embedding_provider = os.getenv("KNOWLEDGE_EMBEDDING_PROVIDER", "api").strip().lower()

        if self.embedding_provider == "local":
            # 本地 Ollama（OpenAI 兼容端点），默认本机 11434，模型 bge-m3
            self.embedding_base_url = os.getenv("KNOWLEDGE_EMBEDDING_BASE_URL", "http://127.0.0.1:11434/v1")
            self.embedding_api_key = os.getenv("KNOWLEDGE_EMBEDDING_API_KEY", "ollama")
            self.embedding_model = os.getenv("KNOWLEDGE_EMBEDDING_MODEL", "bge-m3")
        else:
            # 外部 API，默认 SiliconFlow；key 缺省时回退到 OPENAI_API_KEY
            self.embedding_base_url = first_env_value(
                "KNOWLEDGE_EMBEDDING_BASE_URL",
                default="https://api.siliconflow.cn/v1",
            )
            self.embedding_api_key = first_env_value("KNOWLEDGE_EMBEDDING_API_KEY", "OPENAI_API_KEY")
            self.embedding_model = os.getenv("KNOWLEDGE_EMBEDDING_MODEL", "BAAI/bge-m3")
        self.reranker_api_key = first_env_value("KNOWLEDGE_RERANKER_API_KEY")
        self.reranker_base_url = first_env_value(
            "KNOWLEDGE_RERANKER_BASE_URL",
            default=self.embedding_base_url if self.reranker_api_key else "",
        )
        self.reranker_model = os.getenv("KNOWLEDGE_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
        self.max_file_bytes = int(os.getenv("KNOWLEDGE_MAX_FILE_SIZE_MB", "50")) * 1024 * 1024
        self.chunk_size = max(100, int(os.getenv("KNOWLEDGE_CHUNK_SIZE", "1200")))
        self.chunk_overlap = max(0, int(os.getenv("KNOWLEDGE_CHUNK_OVERLAP", "100")))
        self.embedding_batch_size = max(1, int(os.getenv("KNOWLEDGE_EMBEDDING_BATCH_SIZE", "16")))
        self.database_pool_size = max(
            1,
            int(os.getenv("KNOWLEDGE_DATABASE_POOL_SIZE", os.getenv("POSTGRES_POOL_SIZE", "20"))),
        )
        self.database_max_overflow = max(
            0,
            int(os.getenv("KNOWLEDGE_DATABASE_MAX_OVERFLOW", os.getenv("POSTGRES_MAX_OVERFLOW", "10"))),
        )
        self.database_pool_timeout = max(
            1.0,
            float(os.getenv("KNOWLEDGE_DATABASE_POOL_TIMEOUT_SECONDS", "60")),
        )
        self.ingest_concurrency = max(1, int(os.getenv("KNOWLEDGE_INGEST_CONCURRENCY", "2")))
        self.ingest_rate_limit = os.getenv("KNOWLEDGE_INGEST_RATE_LIMIT", "10000 per hour")
        self.allowed_namespaces = [
            item.strip()
            for item in os.getenv("KNOWLEDGE_ALLOWED_NAMESPACES", "default,policy,customer_service").split(",")
            if item.strip()
        ]


settings = Settings()
