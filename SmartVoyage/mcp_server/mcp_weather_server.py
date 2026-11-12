"""天气 MCP 服务（端口 8002）：参数化查询 weather_data，支持数据库 / 和风 API 双数据源。

启动：python -m SmartVoyage.mcp_server.mcp_weather_server
访问：http://127.0.0.1:8002/mcp
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

import requests
from mcp.server.fastmcp import FastMCP

from SmartVoyage.config import Config
from SmartVoyage.create_logger import logger
from SmartVoyage.db import get_connection
from SmartVoyage.mcp_server._common import server_options
from SmartVoyage.utils.format import dumps

conf = Config()
HOT_CITIES = ("北京", "上海", "广州", "深圳")


def _normalize_dates(start_date: Optional[str], end_date: Optional[str]):
    """缺省日期兜底：默认查询今天起 3 天。"""
    today = datetime.now().date()
    start = _parse_date(start_date) or today
    end = _parse_date(end_date) or start + timedelta(days=2)
    if end < start:
        end = start
    return start.isoformat(), end.isoformat()


def _parse_date(value: Optional[str]):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(value)[:10], fmt).date()
        except ValueError:
            continue
    return None


class WeatherService:
    def __init__(self):
        self.conn = get_connection()

    def _execute_query(self, sql: str, params: list) -> str:
        try:
            self.conn.ping(reconnect=True)
            cursor = self.conn.cursor(dictionary=True)
            cursor.execute(sql, params)
            results = cursor.fetchall()
            cursor.close()
            for row in results:
                for key, value in row.items():
                    if isinstance(value, (date, datetime, timedelta, Decimal)):
                        from SmartVoyage.utils.format import default_encoder
                        row[key] = default_encoder(value)
            payload = (
                {"status": "success", "data": results}
                if results else
                {"status": "no_data", "message": "未找到天气数据，请确认城市和日期。"}
            )
            return dumps(payload)
        except Exception as exc:
            logger.error(f"天气查询错误: {exc}")
            return dumps({"status": "error", "message": str(exc)})

    def query_weather(self, city: str, start_date: str, end_date: str) -> str:
        """从数据库查询天气，全部条件以参数化 SQL 下推。"""
        start, end = _normalize_dates(start_date, end_date)
        columns = (
            "city, fx_date, temp_max, temp_min, text_day, text_night, "
            "humidity, wind_dir_day, wind_scale_day, precip, uv_index"
        )
        if not city or city.strip() in ("全国", "热门城市", "四大城市", "默认"):
            placeholders = ", ".join(["%s"] * len(HOT_CITIES))
            sql = (f"SELECT {columns} FROM weather_data "
                   f"WHERE city IN ({placeholders}) AND fx_date BETWEEN %s AND %s "
                   "ORDER BY fx_date, city")
            return self._execute_query(sql, [*HOT_CITIES, start, end])
        sql = (f"SELECT {columns} FROM weather_data "
               "WHERE city = %s AND fx_date BETWEEN %s AND %s ORDER BY fx_date")
        return self._execute_query(sql, [city.strip(), start, end])

    def fetch_weather_from_api(self, city: str, start_date: str, end_date: str) -> str:
        """从和风天气 API 获取实时预报（需配置 API Host 与 Key）。"""
        if not conf.weather_api_key or not conf.weather_base_url:
            return dumps({"status": "error", "message": "未配置和风天气 API，请改用 WEATHER_SOURCE=database"})
        start, end = _normalize_dates(start_date, end_date)
        headers = {"X-QW-Api-Key": conf.weather_api_key, "Accept-Encoding": "gzip"}
        try:
            geo = requests.get(
                f"{conf.weather_base_url}/geo/v2/city/lookup",
                params={"location": city}, headers=headers, timeout=10,
            )
            geo.raise_for_status()
            locations = geo.json().get("location") or []
            if not locations:
                return dumps({"status": "no_data", "message": f"未找到城市：{city}"})

            resp = requests.get(
                f"{conf.weather_base_url}/v7/weather/7d",
                params={"location": locations[0]["id"]}, headers=headers, timeout=10,
            )
            resp.raise_for_status()
            payload = resp.json()
            if str(payload.get("code")) != "200":
                return dumps({"status": "error", "message": f"天气 API 返回 {payload.get('code')}"})
            results = []
            for day in payload.get("daily", []):
                fx_date = str(day.get("fxDate", ""))[:10]
                if start <= fx_date <= end:
                    results.append({
                        "city": city, "fx_date": fx_date,
                        "temp_max": int(day.get("tempMax", 0)), "temp_min": int(day.get("tempMin", 0)),
                        "text_day": day.get("textDay", ""), "text_night": day.get("textNight", ""),
                        "humidity": int(day.get("humidity", 0)),
                        "wind_dir_day": day.get("windDirDay", ""),
                        "wind_scale_day": day.get("windScaleDay", ""),
                        "precip": float(day.get("precip", 0)),
                    })
            if results:
                return dumps({"status": "success", "data": results})
            return dumps({"status": "no_data", "message": f"未找到 {city} 在 {start}~{end} 的天气数据"})
        except Exception as exc:
            logger.error(f"和风天气 API 查询失败: {exc}")
            return dumps({"status": "error", "message": f"天气 API 查询失败: {exc}"})


def create_weather_mcp_server() -> FastMCP:
    """创建天气 MCP 服务器（返回实例，便于单元测试断言）。"""
    weather_mcp = FastMCP(
        name="WeatherTools",
        instructions="天气查询工具，支持数据库或和风天气 API 双数据源。",
        log_level="ERROR",
        **server_options(8002, "WEATHER_MCP_PORT"),
    )
    service = WeatherService()

    @weather_mcp.tool(
        name="query_weather",
        description="查询天气数据，参数：city(城市), start_date(开始日期YYYY-MM-DD), end_date(结束日期YYYY-MM-DD)。city 留空或填'全国'时返回北京/上海/广州/深圳四大热门城市",
    )
    def query_weather(city: str, start_date: str, end_date: str) -> str:
        logger.info(f"执行天气查询: {city}, {start_date} ~ {end_date}")
        if conf.weather_source == "api":
            return service.fetch_weather_from_api(city, start_date, end_date)
        return service.query_weather(city, start_date, end_date)

    return weather_mcp


def main():
    server = create_weather_mcp_server()
    logger.info(f"天气 MCP 服务启动: {server.name} @ {server_options(8002, 'WEATHER_MCP_PORT')}")
    print("服务器已启动，请访问 http://127.0.0.1:8002/mcp")
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
