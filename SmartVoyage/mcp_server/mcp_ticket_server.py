"""票务 MCP 服务（端口 8001）：火车票/机票/演唱会票的查询与预定，共 6 个工具。

启动：python -m SmartVoyage.mcp_server.mcp_ticket_server
访问：http://127.0.0.1:8001/mcp
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from mcp.server.fastmcp import FastMCP

from SmartVoyage.create_logger import logger
from SmartVoyage.db import get_connection
from SmartVoyage.mcp_server._common import server_options
from SmartVoyage.utils.format import dumps


class TicketService:
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
                    if isinstance(value, (date, datetime, timedelta, Decimal)):
                        from SmartVoyage.utils.format import default_encoder
                        row[key] = default_encoder(value)
            return dumps(
                {"status": "success", "data": results}
                if results else
                {"status": "no_data", "message": "未找到票务数据，请确认查询条件。"}
            )
        except Exception as exc:
            logger.error(f"票务查询错误: {exc}")
            return dumps({"status": "error", "message": str(exc)})

    def query_train(self, departure_city: str, arrival_city: str, date: str,
                    seat_type: Optional[str] = None) -> str:
        sql = ("SELECT id, departure_city, arrival_city, departure_time, arrival_time, "
               "train_number, seat_type, price, remaining_seats FROM train_tickets "
               "WHERE departure_city = %s AND arrival_city = %s AND DATE(departure_time) = %s")
        params = [departure_city, arrival_city, date]
        if seat_type:
            sql += " AND seat_type = %s"
            params.append(seat_type)
        sql += " ORDER BY departure_time, price"
        return self._execute_query(sql, params)

    def query_flight(self, departure_city: str, arrival_city: str, date: str,
                     cabin_type: Optional[str] = None) -> str:
        sql = ("SELECT id, departure_city, arrival_city, departure_time, arrival_time, "
               "flight_number, cabin_type, price, remaining_seats FROM flight_tickets "
               "WHERE departure_city = %s AND arrival_city = %s AND DATE(departure_time) = %s")
        params = [departure_city, arrival_city, date]
        if cabin_type:
            sql += " AND cabin_type = %s"
            params.append(cabin_type)
        sql += " ORDER BY departure_time, price"
        return self._execute_query(sql, params)

    def query_concert(self, city: str, artist: str, date: str,
                      ticket_type: Optional[str] = None) -> str:
        sql = ("SELECT id, artist, city, venue, start_time, end_time, "
               "ticket_type, price, remaining_seats FROM concert_tickets "
               "WHERE city = %s AND artist = %s AND DATE(start_time) = %s")
        params = [city, artist, date]
        if ticket_type:
            sql += " AND ticket_type = %s"
            params.append(ticket_type)
        sql += " ORDER BY price"
        return self._execute_query(sql, params)

    @staticmethod
    def _check_number(number: int) -> int:
        if not isinstance(number, int) or number <= 0:
            raise ValueError("预定数量必须是大于 0 的整数")
        return number

    def order_train(self, departure_date: str, train_number: str, seat_type: str, number: int) -> str:
        self._check_number(number)
        return f"恭喜，火车票预定成功！日期：{departure_date}，车次：{train_number}，座位：{seat_type}，数量：{number}张。"

    def order_flight(self, departure_date: str, flight_number: str, cabin_type: str, number: int) -> str:
        self._check_number(number)
        return f"恭喜，机票预定成功！日期：{departure_date}，航班号：{flight_number}，舱位：{cabin_type}，数量：{number}张。"

    def order_concert(self, start_date: str, artist: str, venue: str,
                      ticket_type: str, number: int) -> str:
        self._check_number(number)
        return f"恭喜，演出票预定成功！日期：{start_date}，艺人：{artist}，场馆：{venue}，票类型：{ticket_type}，数量：{number}张。"


def create_ticket_mcp_server() -> FastMCP:
    """创建票务 MCP 服务器（返回实例，便于单元测试断言）。"""
    ticket_mcp = FastMCP(
        name="TicketTools",
        instructions="票务工具，支持火车票、机票、演唱会票的查询与预定。",
        log_level="ERROR",
        **server_options(8001, "TICKET_MCP_PORT"),
    )
    service = TicketService()

    @ticket_mcp.tool(
        name="query_train",
        description="查询火车票信息，参数：departure_city(出发城市), arrival_city(到达城市), date(日期YYYY-MM-DD), seat_type(座位类型，可选)",
    )
    def query_train(departure_city: str, arrival_city: str, date: str,
                    seat_type: Optional[str] = None) -> str:
        return service.query_train(departure_city, arrival_city, date, seat_type)

    @ticket_mcp.tool(
        name="query_flight",
        description="查询机票信息，参数：departure_city(出发城市), arrival_city(到达城市), date(日期YYYY-MM-DD), cabin_type(舱位类型，可选)",
    )
    def query_flight(departure_city: str, arrival_city: str, date: str,
                     cabin_type: Optional[str] = None) -> str:
        return service.query_flight(departure_city, arrival_city, date, cabin_type)

    @ticket_mcp.tool(
        name="query_concert",
        description="查询演唱会票信息，参数：city(城市), artist(艺人), date(日期YYYY-MM-DD), ticket_type(票类型，可选)",
    )
    def query_concert(city: str, artist: str, date: str,
                      ticket_type: Optional[str] = None) -> str:
        return service.query_concert(city, artist, date, ticket_type)

    @ticket_mcp.tool(name="order_train", description="根据日期、车次、座位类型、数量预定火车票")
    def order_train(departure_date: str, train_number: str, seat_type: str, number: int) -> str:
        return service.order_train(departure_date, train_number, seat_type, number)

    @ticket_mcp.tool(name="order_flight", description="根据日期、航班号、舱位类型、数量预定机票")
    def order_flight(departure_date: str, flight_number: str, cabin_type: str, number: int) -> str:
        return service.order_flight(departure_date, flight_number, cabin_type, number)

    @ticket_mcp.tool(name="order_concert", description="根据日期、艺人、场馆、票类型、数量预定演出票")
    def order_concert(start_date: str, artist: str, venue: str,
                      ticket_type: str, number: int) -> str:
        return service.order_concert(start_date, artist, venue, ticket_type, number)

    return ticket_mcp


def main():
    server = create_ticket_mcp_server()
    logger.info(f"票务 MCP 服务启动: {server.name} @ {server_options(8001, 'TICKET_MCP_PORT')}")
    print("服务器已启动，请访问 http://127.0.0.1:8001/mcp")
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
