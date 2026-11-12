"""天气数据采集：从和风天气 API 拉取 30 天预报并增量写入天气表。

用法：
    python -m SmartVoyage.utils.spider_weather --once            # 立即检查并更新一次
    python -m SmartVoyage.utils.spider_weather --once --force    # 强制刷新
    python -m SmartVoyage.utils.spider_weather --scheduler       # 每日 01:00 定时更新
"""
import argparse
import gzip
import json
import time
from datetime import datetime

import pytz
import requests
import schedule

from SmartVoyage.config import Config
from SmartVoyage.create_logger import logger
from SmartVoyage.db import get_connection

conf = Config()
TZ = pytz.timezone('Asia/Shanghai')

# 常用城市与和风天气 Location ID
CITY_CODES = {
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280101",
    "深圳": "101280601",
    "成都": "101270101",
    "杭州": "101210101",
    "南京": "101190101",
}

INSERT_SQL = """
INSERT INTO weather_data (
    city, fx_date, sunrise, sunset, moonrise, moonset, moon_phase, moon_phase_icon,
    temp_max, temp_min, icon_day, text_day, icon_night, text_night,
    wind360_day, wind_dir_day, wind_scale_day, wind_speed_day,
    wind360_night, wind_dir_night, wind_scale_night, wind_speed_night,
    precip, uv_index, humidity, pressure, vis, cloud, update_time
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    temp_max = VALUES(temp_max), temp_min = VALUES(temp_min), text_day = VALUES(text_day),
    text_night = VALUES(text_night), humidity = VALUES(humidity), precip = VALUES(precip),
    update_time = VALUES(update_time)
"""


def fetch_weather_data(city: str, location: str):
    """请求和风天气 30 天预报，自动处理 gzip 压缩响应。"""
    if not conf.weather_api_key or not conf.weather_base_url:
        logger.warning("未配置 HEFENG_WEATHER_API_KEY / HEFENG_API_HOST，跳过在线采集")
        return None
    headers = {"X-QW-Api-Key": conf.weather_api_key, "Accept-Encoding": "gzip"}
    url = f"{conf.weather_base_url}/v7/weather/30d?location={location}"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        if response.headers.get('Content-Encoding') == 'gzip':
            text = gzip.decompress(response.content).decode('utf-8')
        else:
            text = response.text
        return json.loads(text)
    except requests.RequestException as exc:
        logger.error(f"请求 {city} 天气数据失败: {exc}")
        return None
    except (json.JSONDecodeError, gzip.BadGzipFile, UnicodeDecodeError) as exc:
        logger.error(f"{city} 天气响应解析失败: {exc}")
        return None


def get_latest_update_time(cursor, city: str):
    """查询某城市最近一次数据更新时间。"""
    cursor.execute(
        "SELECT MAX(update_time) AS latest_time FROM weather_data WHERE city = %s", (city,)
    )
    row = cursor.fetchone()
    if not row:
        return None
    value = row["latest_time"] if isinstance(row, dict) else row[0]
    if isinstance(value, str):
        try:
            value = datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    return value


def should_update_data(latest_time, force_update: bool = False) -> bool:
    """无记录、超过 24 小时或强制刷新时需要更新。"""
    if force_update or not latest_time:
        return True
    latest = latest_time.replace(tzinfo=TZ) if latest_time.tzinfo is None else latest_time
    return (datetime.now(TZ) - latest).total_seconds() / 3600 >= 24


def store_weather_data(conn, cursor, city: str, data: dict) -> int:
    """把预报数据写入天气表（唯一键 city+fx_date 冲突则更新）。"""
    if not data or str(data.get("code")) != "200":
        logger.warning(f"{city} 数据无效，跳过存储")
        return 0
    raw_update = data.get("updateTime") or datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')
    update_time = raw_update.replace('T', ' ')[:19]
    count = 0
    for day in data.get("daily", []):
        values = (
            city, day.get("fxDate"),
            day.get("sunrise"), day.get("sunset"), day.get("moonrise"), day.get("moonset"),
            day.get("moonPhase"), day.get("moonPhaseIcon"),
            _int(day.get("tempMax")), _int(day.get("tempMin")),
            day.get("iconDay"), day.get("textDay"), day.get("iconNight"), day.get("textNight"),
            _int(day.get("wind360Day")), day.get("windDirDay"), day.get("windScaleDay"), _int(day.get("windSpeedDay")),
            _int(day.get("wind360Night")), day.get("windDirNight"), day.get("windScaleNight"), _int(day.get("windSpeedNight")),
            _float(day.get("precip")), _int(day.get("uvIndex")), _int(day.get("humidity")),
            _int(day.get("pressure")), _int(day.get("vis")), _int(day.get("cloud")),
            update_time,
        )
        try:
            cursor.execute(INSERT_SQL, values)
            count += 1
        except Exception as exc:
            logger.error(f"{city} {day.get('fxDate')} 写入失败: {exc}")
            conn.rollback()
    conn.commit()
    logger.info(f"{city} 写入/更新 {count} 天预报数据")
    return count


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def update_weather(force_update: bool = False) -> int:
    """检查并更新所有城市天气数据，返回写入天数。"""
    if not conf.weather_api_key:
        logger.warning("未配置和风天气 API Key，保留数据库内已有模拟数据")
        return 0
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    total = 0
    try:
        for city, location in CITY_CODES.items():
            latest = get_latest_update_time(cursor, city)
            if not should_update_data(latest, force_update):
                logger.info(f"{city} 数据已是最新（{latest}）")
                continue
            data = fetch_weather_data(city, location)
            total += store_weather_data(conn, cursor, city, data or {})
    finally:
        cursor.close()
        conn.close()
    return total


def setup_scheduler():
    """每天北京时间 01:00 执行一次增量更新。"""
    schedule.every().day.at("01:00").do(update_weather)
    logger.info("天气定时更新任务已注册：每天 01:00")
    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="SmartVoyage 天气数据采集")
    parser.add_argument("--once", action="store_true", help="立即执行一次更新后退出")
    parser.add_argument("--force", action="store_true", help="忽略 24 小时增量判断")
    parser.add_argument("--scheduler", action="store_true", help="启动定时调度")
    args = parser.parse_args()
    if args.scheduler:
        setup_scheduler()
    else:
        print(f"本次写入 {update_weather(force_update=args.force)} 天预报数据")


if __name__ == "__main__":
    main()
