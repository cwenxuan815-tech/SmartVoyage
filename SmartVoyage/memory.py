"""对话记忆模块：短期对话、用户偏好、任务上下文、实体历史 + MySQL/SQLite 持久化。

数据库连接由 ChatService 通过 set_db_connection() 注入，未注入时静默降级为纯内存，
保证单元测试无需数据库也可运行。
"""
import json
from datetime import datetime

import pytz

from SmartVoyage.create_logger import logger

TZ = pytz.timezone('Asia/Shanghai')


class ConversationMemory:
    """管理对话记忆的类，包括短期对话、用户偏好和任务上下文。"""

    def __init__(self, short_term_limit: int = 10):
        self.short_term_messages = []
        self.user_profile = {}
        self.current_task = {}
        self.short_term_limit = short_term_limit
        self.entity_history = []
        self._db_conn = None

    # ---------------- 连接管理 ----------------
    def set_db_connection(self, db_conn):
        self._db_conn = db_conn

    def _ensure_db(self):
        if self._db_conn is None:
            raise RuntimeError("数据库连接未初始化")
        try:
            self._db_conn.ping(reconnect=True)
        except Exception:
            from SmartVoyage.db import get_connection
            self._db_conn = get_connection()
            self._db_conn.ping(reconnect=True)

    # ---------------- 内存读写 ----------------
    def add_message(self, role: str, content: str):
        self.short_term_messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(TZ).strftime('%H:%M:%S'),
        })
        if len(self.short_term_messages) > self.short_term_limit:
            self.short_term_messages = self.short_term_messages[-self.short_term_limit:]
        self.save_messages_to_db()

    def get_short_term_text(self) -> str:
        lines = []
        for msg in self.short_term_messages:
            label = "User" if msg["role"] == "user" else "Assistant"
            lines.append(f"{label}: {msg['content']}")
        return '\n'.join(lines)

    def update_profile(self, profile_update: dict):
        self.user_profile.update(profile_update or {})
        self.save_profile_to_db()

    def update_task_context(self, task_update: dict):
        self.current_task.update(task_update or {})

    def extract_entities(self, intent_type: str, query: str):
        self.entity_history.append({
            "type": intent_type,
            "query": query if isinstance(query, str) else json.dumps(query, ensure_ascii=False),
            "timestamp": datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S'),
        })
        if len(self.entity_history) > 20:
            self.entity_history = self.entity_history[-20:]
        self.save_entity_to_db(intent_type, query)

    def get_profile_text(self) -> str:
        if not self.user_profile:
            return "无已知的用户偏好"
        return "，".join(f"{k}: {v}" for k, v in self.user_profile.items())

    def get_entity_text(self) -> str:
        if not self.entity_history:
            return "无历史查询实体"
        return "；".join(f"{item['type']}:{item['query']}" for item in self.entity_history[-5:])

    def clear(self):
        self.short_term_messages = []
        self.user_profile = {}
        self.current_task = {}
        self.entity_history = []
        self.clear_all_from_db()

    # ---------------- 序列化 ----------------
    def to_dict(self) -> dict:
        return {
            "short_term_messages": self.short_term_messages,
            "user_profile": self.user_profile,
            "current_task": self.current_task,
            "entity_history": self.entity_history[-5:],
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ConversationMemory':
        memory = cls()
        memory.short_term_messages = data.get("short_term_messages", [])
        memory.user_profile = data.get("user_profile", {})
        memory.current_task = data.get("current_task", {})
        memory.entity_history = data.get("entity_history", [])
        return memory

    # ---------------- 数据库持久化 ----------------
    def save_profile_to_db(self):
        if self._db_conn is None:
            return
        try:
            self._ensure_db()
            cursor = self._db_conn.cursor()
            for key, value in self.user_profile.items():
                cursor.execute(
                    "INSERT INTO user_profiles (profile_key, profile_value) "
                    "VALUES (%s, %s) ON DUPLICATE KEY UPDATE profile_value = %s",
                    (key, str(value), str(value)),
                )
            self._db_conn.commit()
            cursor.close()
        except Exception as exc:
            logger.warning(f"保存用户偏好失败: {exc}")

    def load_profile_from_db(self):
        if self._db_conn is None:
            return
        try:
            self._ensure_db()
            cursor = self._db_conn.cursor(dictionary=True)
            cursor.execute("SELECT profile_key, profile_value FROM user_profiles")
            rows = cursor.fetchall()
            cursor.close()
            self.user_profile = {row["profile_key"]: row["profile_value"] for row in rows}
        except Exception as exc:
            logger.warning(f"加载用户偏好失败: {exc}")

    def save_entity_to_db(self, intent_type: str, query: str):
        if self._db_conn is None:
            return
        try:
            self._ensure_db()
            cursor = self._db_conn.cursor()
            cursor.execute(
                "INSERT INTO query_history (intent_type, query_content, query_time) VALUES (%s, %s, %s)",
                (intent_type, json.dumps({"query": query}, ensure_ascii=False, default=str),
                 datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')),
            )
            self._db_conn.commit()
            cursor.close()
        except Exception as exc:
            logger.warning(f"保存查询历史失败: {exc}")

    def load_entities_from_db(self, limit: int = 20):
        if self._db_conn is None:
            return
        try:
            self._ensure_db()
            cursor = self._db_conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT intent_type, query_content, query_time FROM query_history "
                "ORDER BY query_time DESC LIMIT %s", (limit,)
            )
            rows = list(reversed(cursor.fetchall()))
            cursor.close()
            self.entity_history = []
            for row in rows:
                try:
                    query_text = json.loads(row["query_content"]).get("query", "")
                except (TypeError, ValueError, json.JSONDecodeError):
                    query_text = ""
                value = row["query_time"]
                timestamp = value.strftime('%Y-%m-%d %H:%M:%S') if hasattr(value, "strftime") else str(value or "")
                self.entity_history.append({
                    "type": row["intent_type"], "query": query_text, "timestamp": timestamp,
                })
        except Exception as exc:
            logger.warning(f"加载查询历史失败: {exc}")

    def save_messages_to_db(self):
        if self._db_conn is None:
            return
        try:
            self._ensure_db()
            cursor = self._db_conn.cursor()
            cursor.execute("DELETE FROM short_term_messages")
            for index, msg in enumerate(self.short_term_messages):
                cursor.execute(
                    "INSERT INTO short_term_messages (role, content, message_time, message_order) "
                    "VALUES (%s, %s, %s, %s)",
                    (msg["role"], msg["content"], msg["timestamp"], index),
                )
            self._db_conn.commit()
            cursor.close()
        except Exception as exc:
            logger.warning(f"保存短期对话失败: {exc}")

    def load_messages_from_db(self):
        if self._db_conn is None:
            return
        try:
            self._ensure_db()
            cursor = self._db_conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT role, content, message_time FROM short_term_messages ORDER BY message_order ASC"
            )
            rows = cursor.fetchall()
            cursor.close()
            self.short_term_messages = [
                {"role": row["role"], "content": row["content"], "timestamp": row["message_time"]}
                for row in rows
            ]
        except Exception as exc:
            logger.warning(f"加载短期对话失败: {exc}")

    def clear_all_from_db(self):
        if self._db_conn is None:
            return
        try:
            self._ensure_db()
            cursor = self._db_conn.cursor()
            cursor.execute("DELETE FROM short_term_messages")
            cursor.execute("DELETE FROM query_history")
            cursor.execute("DELETE FROM user_profiles")
            self._db_conn.commit()
            cursor.close()
        except Exception as exc:
            logger.warning(f"清空记忆数据失败: {exc}")
