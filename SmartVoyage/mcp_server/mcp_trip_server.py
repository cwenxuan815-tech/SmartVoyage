"""行程管家 MCP 服务（端口 8003）：租车 / 旅游团 / 保险的查询与预订，共 6 个工具。

数据源：MySQL（租车、保险）+ RAG 语义检索（旅游团，Milvus 或本地降级）。
启动：python -m SmartVoyage.mcp_server.mcp_trip_server
访问：http://127.0.0.1:8003/mcp
"""
from datetime import date as date_type, datetime, timedelta
from decimal import Decimal
from typing import Optional

from mcp.server.fastmcp import FastMCP

from SmartVoyage.create_logger import logger
from SmartVoyage.db import get_connection
from SmartVoyage.mcp_server._common import server_options
from SmartVoyage.utils.format import dumps
from SmartVoyage.vector_store import search_tour_groups


class TripService:
    def __init__(self):
        self.conn = get_connection()

    def _execute_query(self, sql: str, params: Optional[list] = None) -> str:
        try:
            self.conn.ping(reconnect=True)
            cursor = self.conn.cursor(dictionary=True)
            cursor.execute(sql, params or [])
            results = cursor.fetchall()
            cursor.close()
            for row in results:
                for key, value in row.items():
                    if isinstance(value, (date_type, datetime, timedelta, Decimal)):
                        from SmartVoyage.utils.format import default_encoder
                        row[key] = default_encoder(value)
            return dumps(
                {"status": "success", "data": results}
                if results else
                {"status": "no_data", "message": "未找到行程数据，请确认查询条件。"}
            )
        except Exception as exc:
            logger.error(f"行程查询错误: {exc}")
            return dumps({"status": "error", "message": str(exc)})

    def query_car_rental(self, pickup_city: str, return_city: str, date: str,
                         car_type: Optional[str] = None) -> str:
        sql = ("SELECT id, company, pickup_city, return_city, pickup_date, car_type, "
               "car_model, price_per_day, total_available, transmission, seats, deposit "
               "FROM car_rentals WHERE pickup_city = %s AND return_city = %s AND pickup_date = %s")
        params = [pickup_city, return_city, date]
        if car_type:
            sql += " AND car_type = %s"
            params.append(car_type)
        sql += " ORDER BY price_per_day"
        return self._execute_query(sql, params)

    def query_tour_group(self, query_text: str, city: Optional[str] = None) -> str:
        """旅游团语义检索（RAG）。"""
        try:
            tours = search_tour_groups(query_text, city, limit=5)
            if tours:
                return dumps({"status": "success", "data": tours})
            return dumps({
                "status": "no_data",
                "message": f"未找到匹配的旅游团。{'请确认城市名称，' if city else ''}可尝试其他描述。",
            })
        except Exception as exc:
            logger.error(f"旅游团 RAG 查询错误: {exc}")
            return dumps({"status": "error", "message": f"旅游团查询出错：{exc}"})

    def query_insurance(self, insurance_type: Optional[str] = None) -> str:
        sql = ("SELECT id, insurance_type, name, company, coverage, price, "
               "duration_days, max_coverage, medical_coverage, baggage_coverage, flight_delay "
               "FROM insurances")
        params = []
        if insurance_type:
            sql += " WHERE insurance_type = %s"
            params.append(insurance_type)
        sql += " ORDER BY price"
        return self._execute_query(sql, params)

    @staticmethod
    def _check_number(number: int) -> int:
        if not isinstance(number, int) or number <= 0:
            raise ValueError("数量必须是大于 0 的整数")
        return number

    def order_car_rental(self, date: str, car_type: str, number: int) -> str:
        self._check_number(number)
        return f"恭喜，租车预订成功！日期：{date}，车型：{car_type}，数量：{number}辆。"

    def order_tour_group(self, date: str, tour_name: str, number: int) -> str:
        self._check_number(number)
        return f"恭喜，旅游团报名成功！团名：{tour_name}，日期：{date}，人数：{number}人。"

    def order_insurance(self, insurance_type: str, date: str, number: int) -> str:
        self._check_number(number)
        return f"恭喜，旅行保险购买成功！类型：{insurance_type}，日期：{date}，份数：{number}份。"


def create_trip_mcp_server() -> FastMCP:
    """创建行程 MCP 服务器（返回实例，便于单元测试断言）。"""
    trip_mcp = FastMCP(
        name="TripTools",
        instructions="行程管家工具：租车、旅游团语义检索、保险的查询与预订。",
        log_level="ERROR",
        **server_options(8003, "TRIP_MCP_PORT"),
    )
    service = TripService()

    @trip_mcp.tool(
        name="query_car_rental",
        description="查询租车信息，参数：pickup_city(取车城市), return_city(还车城市), date(YYYY-MM-DD), car_type(可选：经济型/SUV/豪华型/MPV)",
    )
    def query_car_rental(pickup_city: str, return_city: str, date: str,
                         car_type: Optional[str] = None) -> str:
        return service.query_car_rental(pickup_city, return_city, date, car_type)

    @trip_mcp.tool(
        name="query_tour_group",
        description="查询旅游团（语义搜索），参数：query_text(自然语言描述，如'想看雪山的地方')，city(城市过滤，可选)",
    )
    def query_tour_group(query_text: str, city: Optional[str] = None) -> str:
        return service.query_tour_group(query_text, city)

    @trip_mcp.tool(
        name="query_insurance",
        description="查询旅行保险产品，参数：insurance_type(可选：综合型/意外型/医疗型/境外型，不传返回全部)",
    )
    def query_insurance(insurance_type: Optional[str] = None) -> str:
        return service.query_insurance(insurance_type)

    @trip_mcp.tool(name="order_car_rental", description="根据日期、车型和数量预订租车服务")
    def order_car_rental(date: str, car_type: str, number: int) -> str:
        return service.order_car_rental(date, car_type, number)

    @trip_mcp.tool(name="order_tour_group", description="根据出发日期、旅游团名称和人数报名旅游团")
    def order_tour_group(date: str, tour_name: str, number: int) -> str:
        return service.order_tour_group(date, tour_name, number)

    @trip_mcp.tool(name="order_insurance", description="根据保险类型、生效日期和份数购买旅行保险")
    def order_insurance(insurance_type: str, date: str, number: int) -> str:
        return service.order_insurance(insurance_type, date, number)

    return trip_mcp


def main():
    server = create_trip_mcp_server()
    logger.info(f"行程 MCP 服务启动: {server.name} @ {server_options(8003, 'TRIP_MCP_PORT')}")
    print("服务器已启动，请访问 http://127.0.0.1:8003/mcp")
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
