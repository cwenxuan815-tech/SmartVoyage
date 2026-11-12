"""全局配置：环境变量驱动，避免硬编码密钥与地址。

本地开发默认值对齐课件；Docker 部署时通过同名环境变量覆盖（见 .env.example）。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


def _env(name: str, default: str = "", legacy: str = "") -> str:
    """读取环境变量：SV_ 前缀优先，其次兼容历史 MYSQL_ 等通用变量名。

    本机可能同时存在其他项目的 MYSQL_DATABASE/MYSQL_USER，SV_ 前缀可避免串库。
    """
    value = os.getenv(name)
    if value not in (None, ""):
        return value
    if legacy:
        value = os.getenv(legacy)
        if value not in (None, ""):
            return value
    return default


class Config:
    """统一管理 LLM、数据库、服务地址与日志配置。"""

    def __init__(self):
        # 大模型
        self.base_url = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.model_name = os.getenv("LLM_MODEL_NAME", "qwen3.6-plus")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.1"))

        # MySQL（SV_MYSQL_* 优先，兼容 MYSQL_*，避免与其他项目的同名变量冲突）
        self.host = _env("SV_MYSQL_HOST", "127.0.0.1", "MYSQL_HOST")
        self.port = int(_env("SV_MYSQL_PORT", "3306", "MYSQL_PORT"))
        self.user = _env("SV_MYSQL_USER", "smart_yoyage", "MYSQL_USER")
        # 仅本地演示用的占位口令，真实口令一律通过 .env / 环境变量注入
        self.password = _env("SV_MYSQL_PASSWORD", "changeme", "MYSQL_PASSWORD")
        self.database = _env("SV_MYSQL_DATABASE", "travel_rag", "MYSQL_DATABASE")

        # 日志
        self.log_file = os.getenv("LOG_FILE", str(PROJECT_ROOT / "logs" / "app.log"))

        # 天气数据源
        self.weather_source = os.getenv("WEATHER_SOURCE", "database")
        self.weather_api_key = os.getenv("HEFENG_WEATHER_API_KEY", "")
        self.qweather_api_key = self.weather_api_key
        self.weather_base_url = os.getenv("HEFENG_API_HOST", "").rstrip("/")

        # RAG / 向量库
        self.milvus_host = os.getenv("MILVUS_HOST", "127.0.0.1")
        self.milvus_port = int(os.getenv("MILVUS_PORT", "19530"))
        self.embedding_url = os.getenv(
            "EMBEDDING_URL", f"{self.base_url}/embeddings"
        )
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")
        self.embedding_dim = int(os.getenv("EMBEDDING_DIM", "1024"))
        self.tour_group_collection = os.getenv("TOUR_GROUP_COLLECTION", "tour_groups")

        # 意图 → 子代理映射
        self.intent = {
            "weather": "WeatherQueryAssistant",
            "flight": "TicketAssistant",
            "train": "TicketAssistant",
            "concert": "TicketAssistant",
            "order": "TicketAssistant",
            "car_rental": "TripAssistant",
            "tour_group": "TripAssistant",
            "insurance": "TripAssistant",
            "trip_order": "TripAssistant",
        }

        # 服务地址（Docker 下改为容器服务名）
        self.agent_urls = {
            "WeatherQueryAssistant": os.getenv("WEATHER_A2A_URL", "http://127.0.0.1:5005"),
            "TicketAssistant": os.getenv("TICKET_A2A_URL", "http://127.0.0.1:5006"),
            "TripAssistant": os.getenv("TRIP_A2A_URL", "http://127.0.0.1:5007"),
        }
        self.mcp_urls = {
            "weather": os.getenv("WEATHER_MCP_URL", "http://127.0.0.1:8002/mcp"),
            "ticket": os.getenv("TICKET_MCP_URL", "http://127.0.0.1:8001/mcp"),
            "trip": os.getenv("TRIP_MCP_URL", "http://127.0.0.1:8003/mcp"),
        }

        # 运行开关
        self.offline = _bool("SV_OFFLINE", False)
        self.db_fallback_sqlite = _bool("SV_DB_FALLBACK", True)
        self.sqlite_path = os.getenv("SV_SQLITE_PATH", str(PROJECT_ROOT / "data" / "smartvoyage.db"))
        self.url_123 = os.getenv("TICKET_12306_URL", "")

    def get_mysql_config(self, env: str = "test"):
        """按环境名返回数据库配置（保留课件的多环境切换能力）。

        各环境凭据不再内置明文，统一从 `<ENV>_MYSQL_*` 环境变量读取，
        例如生产环境读取 PROD_MYSQL_HOST / PROD_MYSQL_PASSWORD 等；
        缺失时回落到当前 Config 的通用配置，不写入源码。
        """
        if env == "test":
            return self.host, self.user, self.password, self.database

        prefix = f"{env.upper()}_MYSQL_"
        host = os.getenv(prefix + "HOST", self.host)
        user = os.getenv(prefix + "USER", self.user)
        password = os.getenv(prefix + "PASSWORD", self.password)
        database = os.getenv(prefix + "DATABASE", self.database)
        return host, user, password, database

    def as_dict(self) -> dict:
        """返回可安全打印的配置（隐藏密钥）。"""
        return {
            "model_name": self.model_name,
            "base_url": self.base_url,
            "api_key": "***" if self.api_key else "(未设置)",
            "mysql": f"{self.host}:{self.port}/{self.database}",
            "weather_source": self.weather_source,
            "offline": self.offline,
        }
