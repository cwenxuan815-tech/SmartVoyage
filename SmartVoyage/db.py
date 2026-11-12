"""统一数据访问层：MySQL 优先，连接不可用时自动降级 SQLite。

业务层统一使用 ``cursor.execute(sql, params)`` 形式的参数化查询，SQL 过滤条件下推到数据库，
避免把全表数据捞到应用层再过滤。降级时对 MySQL 方言做最小转换，业务代码无需改动。
"""
import re
import sqlite3
import threading
from pathlib import Path

import mysql.connector

from SmartVoyage.config import Config
from SmartVoyage.create_logger import logger

_SQLITE_LOCK = threading.RLock()
_SQLITE_READY: set = set()

DDL_PATH = Path(__file__).resolve().parent / "sql" / "create_all_tables.sql"


class MySQLConnection:
    """包装 mysql.connector 连接，统一 dialect 属性。"""

    dialect = "mysql"

    def __init__(self, raw):
        self._conn = raw

    def cursor(self, dictionary: bool = False):
        return self._conn.cursor(dictionary=dictionary)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def ping(self, reconnect: bool = True):
        self._conn.ping(reconnect=reconnect, attempts=3, delay=1)

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def is_connected(self) -> bool:
        return self._conn.is_connected()


class _SQLiteCursor:
    """让 sqlite cursor 具备与 mysql dictionary cursor 一致的接口。"""

    def __init__(self, cursor):
        self._cur = cursor

    @staticmethod
    def _translate(sql: str) -> str:
        # MySQL UPSERT → SQLite REPLACE（依赖相同唯一键）
        if re.search(r"ON\s+DUPLICATE\s+KEY\s+UPDATE", sql, re.I):
            sql = re.split(r"ON\s+DUPLICATE\s+KEY\s+UPDATE", sql, flags=re.I)[0]
            sql = re.sub(r"^\s*INSERT\s+INTO", "INSERT OR REPLACE INTO", sql, flags=re.I)
        sql = re.sub(r"\bNOW\(\)", "CURRENT_TIMESTAMP", sql, flags=re.I)
        return sql.replace("%s", "?")

    def execute(self, sql: str, params=None):
        sql = self._translate(sql)
        if params:
            params = tuple(params)
            # UPSERT 转 REPLACE 后占位符变少，需同步裁剪绑定参数
            expected = sql.count("?")
            if len(params) > expected:
                params = params[:expected]
        with _SQLITE_LOCK:
            self._cur.execute(sql, params or ())
        return self

    def executemany(self, sql: str, seq_of_params):
        with _SQLITE_LOCK:
            self._cur.executemany(self._translate(sql), [tuple(p) for p in seq_of_params])
        return self

    @property
    def description(self):
        return self._cur.description

    def _to_dict(self, row):
        if row is None or not self._cur.description:
            return row
        return {col[0]: value for col, value in zip(self._cur.description, row)}

    def fetchall(self):
        return [self._to_dict(r) for r in self._cur.fetchall()]

    def fetchone(self):
        return self._to_dict(self._cur.fetchone())

    @property
    def rowcount(self):
        return self._cur.rowcount

    def close(self):
        self._cur.close()


class SQLiteConnection:
    dialect = "sqlite"

    def __init__(self, path: str):
        self.path = path
        self._conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._conn.execute("PRAGMA foreign_keys=ON")

    def cursor(self, dictionary: bool = False):
        return _SQLiteCursor(self._conn.cursor())

    def commit(self):
        with _SQLITE_LOCK:
            self._conn.commit()

    def rollback(self):
        with _SQLITE_LOCK:
            self._conn.rollback()

    def ping(self, reconnect: bool = True):
        # sqlite 为本地文件，无需重连
        return True

    def close(self):
        self._conn.close()

    def is_connected(self) -> bool:
        return True


def mysql_to_sqlite_script(mysql_sql: str) -> str:
    """把项目 MySQL DDL/DML 转成 SQLite 可执行脚本，保证单一数据源定义。"""
    lines = [ln for ln in mysql_sql.splitlines() if not ln.strip().startswith("--")]
    text = "\n".join(lines)
    statements = []
    for raw_stmt in text.split(";"):
        s = raw_stmt.strip()
        if not s:
            continue
        if re.match(r"^(DROP\s+DATABASE|CREATE\s+DATABASE|USE\s|SET\s|START\s+TRANSACTION|COMMIT\s*$)", s, re.I):
            continue
        s = re.sub(r"\bCOMMENT\s*=?\s*'[^']*'", "", s, flags=re.I)
        s = re.sub(r"\s+CHARACTER\s+SET\s+\w+", "", s, flags=re.I)
        s = re.sub(r"\s+COLLATE\s+\w+", "", s, flags=re.I)
        s = re.sub(r"\bINT\s+AUTO_INCREMENT\s+PRIMARY\s+KEY\b", "INTEGER PRIMARY KEY AUTOINCREMENT", s, flags=re.I)
        s = re.sub(r"\bAUTO_INCREMENT\b", "", s, flags=re.I)
        s = re.sub(r"\bUNIQUE\s+KEY\s+\w+\s*\(", "UNIQUE (", s, flags=re.I)
        s = re.sub(r",?\s*\b(?:INDEX|KEY)\s+\w+\s*\([^)]*\)", "", s, flags=re.I)
        s = re.sub(r"\s+ENGINE\s*=\s*\w+[^;]*", "", s, flags=re.I)
        s = re.sub(r"\s+DEFAULT\s+CHARSET\s*=\s*\w+", "", s, flags=re.I)
        s = re.sub(r"\s+ON\s+UPDATE\s+CURRENT_TIMESTAMP", "", s, flags=re.I)
        s = s.replace("DEFAULT FALSE", "DEFAULT 0").replace("DEFAULT TRUE", "DEFAULT 1")
        s = s.replace("`", "")
        if re.search(r"ON\s+DUPLICATE\s+KEY\s+UPDATE", s, re.I):
            s = re.split(r"ON\s+DUPLICATE\s+KEY\s+UPDATE", s, flags=re.I)[0]
            s = re.sub(r"^\s*INSERT\s+INTO", "INSERT OR REPLACE INTO", s, flags=re.I)
        s = re.sub(r",\s*\)", ")", s)
        if s:
            statements.append(s + ";")
    if "query_history" in text:
        statements.append("CREATE INDEX IF NOT EXISTS idx_time ON query_history(query_time);")
    return "\n".join(statements)


def ensure_sqlite_schema(path: str, force: bool = False) -> None:
    """确保 SQLite 降级库已建表并载入了模拟数据。"""
    if path in _SQLITE_READY and not force:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='train_tickets'"
        ).fetchone()
        if not exists or force:
            if not DDL_PATH.exists():
                raise FileNotFoundError(f"缺少建表脚本: {DDL_PATH}")
            conn.executescript(mysql_to_sqlite_script(DDL_PATH.read_text(encoding="utf-8")))
            seed = DDL_PATH.parent / "insert_may01_data.sql"
            if seed.exists():
                conn.executescript(mysql_to_sqlite_script(seed.read_text(encoding="utf-8")))
            conn.commit()
            logger.info(f"SQLite 降级库已初始化: {path}")
        _SQLITE_READY.add(path)
    finally:
        conn.close()


def get_connection(force_sqlite: bool = False):
    """获取数据库连接；MySQL 不可用时按配置降级到 SQLite。"""
    conf = Config()
    if not force_sqlite:
        try:
            raw = mysql.connector.connect(
                host=conf.host,
                port=conf.port,
                user=conf.user,
                password=conf.password,
                database=conf.database,
                charset="utf8mb4",
                connection_timeout=5,
            )
            return MySQLConnection(raw)
        except Exception as exc:
            if not conf.db_fallback_sqlite:
                raise
            logger.warning(f"MySQL 连接失败，降级到 SQLite: {exc}")
    ensure_sqlite_schema(conf.sqlite_path)
    return SQLiteConnection(conf.sqlite_path)


def json_ready(rows) -> list:
    """把查询结果中的非 JSON 类型转成字符串/数值（配合 utils.format）。"""
    from SmartVoyage.utils.format import default_encoder
    from datetime import date, datetime, timedelta
    from decimal import Decimal

    for row in rows or []:
        if isinstance(row, dict):
            for key, value in row.items():
                if isinstance(value, (date, datetime, timedelta, Decimal)):
                    row[key] = default_encoder(value)
    return rows
