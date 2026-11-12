"""集成测试：三个 MCP 工具服务的参数化查询与工具注册（依赖数据库，含 SQLite 降级）。"""
import asyncio
import json
import unittest

from SmartVoyage.mcp_server.mcp_ticket_server import TicketService, create_ticket_mcp_server
from SmartVoyage.mcp_server.mcp_trip_server import TripService, create_trip_mcp_server
from SmartVoyage.mcp_server.mcp_weather_server import WeatherService, create_weather_mcp_server


def parse(result):
    return json.loads(result)


class TestWeatherMCPIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = WeatherService()

    def test_query_weather_single_day(self):
        parsed = parse(self.service.query_weather("北京", "2025-07-30", "2025-07-30"))
        self.assertEqual(parsed["status"], "success")
        self.assertEqual(parsed["data"][0]["city"], "北京")
        self.assertEqual(parsed["data"][0]["fx_date"], "2025-07-30")

    def test_query_weather_no_data(self):
        parsed = parse(self.service.query_weather("火星", "2025-07-30", "2025-07-30"))
        self.assertEqual(parsed["status"], "no_data")

    def test_query_weather_hot_cities(self):
        parsed = parse(self.service.query_weather("全国", "2025-08-11", "2025-08-11"))
        self.assertEqual(parsed["status"], "success")
        self.assertGreaterEqual(len(parsed["data"]), 4)

    def test_weather_mcp_server_config(self):
        self.assertEqual(create_weather_mcp_server().name, "WeatherTools")
        tools = asyncio.run(create_weather_mcp_server().list_tools())
        self.assertIn("query_weather", [tool.name for tool in tools])


class TestTicketMCPIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = TicketService()

    def test_query_train(self):
        parsed = parse(self.service.query_train("北京", "上海", "2025-07-30"))
        self.assertEqual(parsed["status"], "success")
        self.assertGreater(len(parsed["data"]), 0)

    def test_query_train_with_seat(self):
        parsed = parse(self.service.query_train("北京", "上海", "2025-07-30", "二等座"))
        self.assertEqual(parsed["status"], "success")
        for item in parsed["data"]:
            self.assertEqual(item["seat_type"], "二等座")

    def test_query_flight(self):
        parsed = parse(self.service.query_flight("北京", "成都", "2026-05-01"))
        self.assertEqual(parsed["status"], "success")

    def test_query_concert(self):
        parsed = parse(self.service.query_concert("北京", "刀郎", "2025-08-23"))
        self.assertEqual(parsed["status"], "success")
        self.assertEqual(parsed["data"][0]["artist"], "刀郎")

    def test_order_train(self):
        self.assertIn("预定成功", self.service.order_train("2026-05-01", "G88", "二等座", 2))
        with self.assertRaises(ValueError):
            self.service.order_train("2026-05-01", "G88", "二等座", 0)

    def test_ticket_mcp_server_config(self):
        tools = asyncio.run(create_ticket_mcp_server().list_tools())
        self.assertEqual(create_ticket_mcp_server().name, "TicketTools")
        self.assertEqual(len(tools), 6)


class TestTripMCPIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = TripService()

    def test_query_car_rental(self):
        parsed = parse(self.service.query_car_rental("北京", "上海", "2025-08-01"))
        self.assertEqual(parsed["status"], "success")

    def test_query_insurance_with_type(self):
        parsed = parse(self.service.query_insurance("综合型"))
        self.assertEqual(parsed["status"], "success")
        for item in parsed["data"]:
            self.assertEqual(item["insurance_type"], "综合型")

    def test_query_tour_group_rag(self):
        parsed = parse(self.service.query_tour_group("想看雪山的地方"))
        self.assertEqual(parsed["status"], "success")
        self.assertIn("雪山", parsed["data"][0]["tour_name"])

    def test_trip_mcp_server_config(self):
        tools = asyncio.run(create_trip_mcp_server().list_tools())
        self.assertEqual(create_trip_mcp_server().name, "TripTools")
        self.assertEqual(len(tools), 6)


if __name__ == "__main__":
    unittest.main()
