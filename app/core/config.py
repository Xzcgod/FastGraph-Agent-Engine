"""本文件地址空间app/core/config.py
基础的配置类型内容
"""

import os
from enum import Enum
from pathlib import Path
from typing import List

from dotenv import load_dotenv


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


def get_environment() -> Environment:
    match os.getenv("APP_ENV", "development").lower():
        case "production" | "prod":
            return Environment.PRODUCTION
        case "staging" | "stage":
            return Environment.STAGING
        case "test":
            return Environment.TEST
        case _:
            return Environment.DEVELOPMENT


def load_env_file():
    env = get_environment()
    print(f"Loading environment: {env}")
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    env_files = [
        os.path.join(base_dir, f".env.{env.value}.local"),
        os.path.join(base_dir, f".env.{env.value}"),
        os.path.join(base_dir, ".env.local"),
        os.path.join(base_dir, ".env"),
    ]
    for env_file in env_files:
        if os.path.isfile(env_file):
            load_dotenv(dotenv_path=env_file)
            print(f"Loaded environment from {env_file}")
            return env_file
    return None


ENV_FILE = load_env_file()


def parse_list_from_env(env_key, default=None):
    value = os.getenv(env_key)
    if not value:
        return default or []
    value = value.strip("\"'")
    if "," not in value:
        return [value]
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings:
    """å…¨å±€é…ç½®ç±» - å®Œæ•´ç‰ˆ"""

    def __init__(self):
        self.ENVIRONMENT = get_environment()

        # åŸºç¡€ä¿¡æ¯
        self.PROJECT_NAME = os.getenv("PROJECT_NAME", "FastAPI LangGraph Template")
        self.VERSION = os.getenv("VERSION", "1.0.0")
        self.DESCRIPTION = os.getenv("DESCRIPTION", "A production-ready FastAPI template with LangGraph")
        self.API_V1_STR = os.getenv("API_V1_STR", "/api/v1")
        self.DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "t", "yes")

        # CORS
        self.ALLOWED_ORIGINS = parse_list_from_env("ALLOWED_ORIGINS", ["*"])

        # Langfuse ç›‘æŽ§
        self.LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        self.LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
        self.LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

        # âœ… LLMï¼ˆç¡…åŸºæµåŠ¨å¹³å°ï¼‰
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        self.OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")
        self.DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "deepseek-ai/DeepSeek-V3")
        self.DEFAULT_LLM_TEMPERATURE = float(os.getenv("DEFAULT_LLM_TEMPERATURE", "0.2"))
        self.MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4000"))
        self.MAX_LLM_CALL_RETRIES = int(os.getenv("MAX_LLM_CALL_RETRIES", "3"))

        # âœ… Tavily æœç´¢ï¼ˆæ–°å¢žï¼‰
        self.TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

        # âœ… é•¿æœŸè®°å¿†ï¼ˆmem0 + pgvectorï¼‰
        self.LONG_TERM_MEMORY_MODEL = os.getenv("LONG_TERM_MEMORY_MODEL", "deepseek-ai/DeepSeek-V3")
        self.LONG_TERM_MEMORY_EMBEDDER_MODEL = os.getenv("LONG_TERM_MEMORY_EMBEDDER_MODEL", "BAAI/bge-m3")
        self.LONG_TERM_MEMORY_COLLECTION_NAME = os.getenv("LONG_TERM_MEMORY_COLLECTION_NAME", "longterm_memory")

        # âœ… çŸ­æœŸè®°å¿†æ»šåŠ¨æ‘˜è¦é˜ˆå€¼
        self.SUMMARY_THRESHOLD = int(os.getenv("SUMMARY_THRESHOLD", "10"))

        # âœ… é‚®ä»¶ SMTP é…ç½®ï¼ˆæ–°å¢žï¼‰- æ”¯æŒ QQ é‚®ç®±
        # QQé‚®ç®±ï¼šè®¾ç½® â†’ è´¦æˆ· â†’ å¼€å¯POP3/SMTP â†’ èŽ·å–æŽˆæƒç 
        self.EMAIL_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "smtp.qq.com")
        self.EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "465"))
        self.EMAIL_SMTP_USER = os.getenv("EMAIL_SMTP_USER", "")          # ä½ çš„QQé‚®ç®±
        self.EMAIL_SMTP_PASSWORD = os.getenv("EMAIL_SMTP_PASSWORD", "")  # QQé‚®ç®±æŽˆæƒç ï¼ˆéžç™»å½•å¯†ç ï¼‰
        self.EMAIL_SMTP_USE_SSL = os.getenv("EMAIL_SMTP_USE_SSL", "true").lower() in ("true", "1", "yes")
        self.EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "æ™ºèƒ½åŠ©æ‰‹")

        # âœ… RAG çŸ¥è¯†åº“é…ç½®ï¼ˆæ–°å¢žï¼‰
        self.RAG_COLLECTION_NAME = os.getenv("RAG_COLLECTION_NAME", "rag_knowledge_base")
        self.RAG_RERANKER_MODEL = os.getenv("RAG_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
        self.RAG_UPLOAD_DIR = Path(os.getenv("RAG_UPLOAD_DIR", "uploads"))
        self.RAG_MAX_FILE_SIZE_MB = int(os.getenv("RAG_MAX_FILE_SIZE_MB", "50"))

        # JWT è®¤è¯
        self.JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
        self.JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
        self.JWT_ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_DAYS", "30"))

        # æ—¥å¿—
        self.LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FORMAT = os.getenv("LOG_FORMAT", "json")

        # PostgreSQL
        self.POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
        self.POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
        self.POSTGRES_DB = os.getenv("POSTGRES_DB", "mydb")
        self.POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
        self.POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
        self.POSTGRES_POOL_SIZE = int(os.getenv("POSTGRES_POOL_SIZE", "20"))
        self.POSTGRES_MAX_OVERFLOW = int(os.getenv("POSTGRES_MAX_OVERFLOW", "10"))
        self.CHECKPOINT_TABLES = ["checkpoint_blobs", "checkpoint_writes", "checkpoints"]

        # é™æµ
        self.RATE_LIMIT_DEFAULT = parse_list_from_env("RATE_LIMIT_DEFAULT", ["200 per day", "50 per hour"])
        default_endpoints = {
            "chat": ["30 per minute"],
            "chat_stream": ["20 per minute"],
            "messages": ["50 per minute"],
            "register": ["10 per hour"],
            "login": ["20 per minute"],
            "root": ["10 per minute"],
            "health": ["20 per minute"],
            "rag_upload": ["20 per hour"],       # RAG æ–‡æ¡£ä¸Šä¼ é™æµ
            "email_resume": ["30 per minute"],   # é‚®ä»¶å®¡æ‰¹ resume æŽ¥å£é™æµ
        }
        self.RATE_LIMIT_ENDPOINTS = default_endpoints.copy()
        for endpoint in default_endpoints:
            env_key = f"RATE_LIMIT_{endpoint.upper()}"
            value = parse_list_from_env(env_key)
            if value:
                self.RATE_LIMIT_ENDPOINTS[endpoint] = value

        # è¯„ä¼°æ¨¡å—
        self.EVALUATION_LLM = os.getenv("EVALUATION_LLM", "Qwen/Qwen3-32B")
        self.EVALUATION_BASE_URL = os.getenv("EVALUATION_BASE_URL", "https://api.siliconflow.cn/v1")
        self.EVALUATION_API_KEY = os.getenv("EVALUATION_API_KEY", self.OPENAI_API_KEY)
        self.EVALUATION_SLEEP_TIME = int(os.getenv("EVALUATION_SLEEP_TIME", "10"))

        self.apply_environment_settings()

    def apply_environment_settings(self):
        """æ ¹æ®å½“å‰çŽ¯å¢ƒè¦†ç›–éƒ¨åˆ†è®¾ç½®"""
        env_settings = {
            Environment.DEVELOPMENT: {
                "DEBUG": True,
                "LOG_LEVEL": "DEBUG",
                "LOG_FORMAT": "console",
                "RATE_LIMIT_DEFAULT": ["1000 per day", "200 per hour"],
            },
            Environment.STAGING: {
                "DEBUG": False,
                "LOG_LEVEL": "INFO",
                "RATE_LIMIT_DEFAULT": ["500 per day", "100 per hour"],
            },
            Environment.PRODUCTION: {
                "DEBUG": False,
                "LOG_LEVEL": "WARNING",
                "RATE_LIMIT_DEFAULT": ["200 per day", "50 per hour"],
            },
            Environment.TEST: {
                "DEBUG": True,
                "LOG_LEVEL": "DEBUG",
                "LOG_FORMAT": "console",
                "RATE_LIMIT_DEFAULT": ["1000 per day", "1000 per hour"],
            },
        }
        current_env_settings = env_settings.get(self.ENVIRONMENT, {})
        for key, value in current_env_settings.items():
            if key.upper() not in os.environ:
                setattr(self, key, value)


settings = Settings()
