"""初始化 SmartVoyage 数据库（MySQL 或 SQLite 降级库）。

用法：
    python scripts/init_db.py              # 初始化 MySQL 并载入模拟数据
    python scripts/init_db.py --sqlite     # 强制初始化 SQLite 降级库
    python scripts/init_db.py --force-sqlite-schema
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from SmartVoyage.config import Config
from SmartVoyage.create_logger import logger
from SmartVoyage.db import DDL_PATH, ensure_sqlite_schema

SEED_PATH = DDL_PATH.parent / "insert_may01_data.sql"
TABLES = [
    "train_tickets", "flight_tickets", "concert_tickets", "weather_data",
    "car_rentals", "insurances", "tour_groups", "user_profiles",
    "query_history", "short_term_messages",
]


def _split_statements(script: str):
    for stmt in script.split(";"):
        lines = [ln for ln in stmt.splitlines() if not ln.strip().startswith("--")]
        clean = "\n".join(lines).strip()
        if clean:
            yield clean


def init_mysql(conf: Config) -> bool:
    import mysql.connector

    admin_user = os.getenv("MYSQL_ADMIN_USER", "root")
    admin_password = os.getenv("MYSQL_ADMIN_PASSWORD", conf.password)
    try:
        conn = mysql.connector.connect(
            host=conf.host, port=conf.port, user=admin_user,
            password=admin_password, connection_timeout=8,
        )
    except Exception as exc:
        logger.warning(f"MySQL 管理员连接失败: {exc}")
        return False

    cur = conn.cursor()
    try:
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS {conf.database} "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        # 项目专用账号；若密码策略或权限不允许，回退为使用已配置账号
        if conf.user != admin_user:
            try:
                cur.execute(f"CREATE USER IF NOT EXISTS '{conf.user}'@'%' IDENTIFIED BY '{conf.password}'")
                cur.execute(f"GRANT ALL PRIVILEGES ON {conf.database}.* TO '{conf.user}'@'%'")
                cur.execute("FLUSH PRIVILEGES")
                logger.info(f"已创建项目账号 {conf.user}")
            except Exception as exc:
                logger.warning(f"创建项目账号失败（可设置 MYSQL_USER=root 绕过）: {exc}")
        cur.execute(f"USE {conf.database}")
        for path in (DDL_PATH, SEED_PATH):
            for stmt in _split_statements(path.read_text(encoding="utf-8")):
                cur.execute(stmt)
            logger.info(f"已执行 {path.name}")
        conn.commit()
        print("MySQL 数据库初始化完成，各表数据量：")
        for table in TABLES:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"  {table:<24} {cur.fetchone()[0]:>4} 行")
        return True
    except Exception as exc:
        logger.error(f"MySQL 初始化失败: {exc}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


def init_sqlite(conf: Config) -> None:
    ensure_sqlite_schema(conf.sqlite_path, force=True)
    import sqlite3
    conn = sqlite3.connect(conf.sqlite_path)
    try:
        print(f"SQLite 降级库初始化完成: {conf.sqlite_path}")
        for table in TABLES:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table:<24} {count:>4} 行")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="初始化 SmartVoyage 数据库")
    parser.add_argument("--sqlite", action="store_true", help="强制初始化 SQLite 降级库")
    parser.add_argument("--mysql-only", action="store_true", help="只初始化 MySQL，失败即报错")
    args = parser.parse_args()

    conf = Config()
    if args.sqlite:
        init_sqlite(conf)
        return
    if not init_mysql(conf):
        if args.mysql_only:
            raise SystemExit("MySQL 初始化失败")
        logger.warning("自动切换到 SQLite 降级库")
        init_sqlite(conf)


if __name__ == "__main__":
    main()
