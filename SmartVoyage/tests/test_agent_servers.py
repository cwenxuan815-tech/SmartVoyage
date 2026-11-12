"""测试：A2A 代理卡片、任务状态机（含追问误判优化）与在线集成链路。"""
import asyncio
import socket
import unittest
import uuid

from python_a2a import A2AClient, Message, MessageRole, Task, TextContent

from SmartVoyage.a2a_server.base_agent import classify_result, heuristic_need_input
from SmartVoyage.a2a_server.ticket_server import TicketQueryServer, agent_card as ticket_card
from SmartVoyage.a2a_server.trip_server import TripQueryServer, agent_card as trip_card
from SmartVoyage.a2a_server.weather_server import WeatherQueryServer, agent_card as weather_card


def port_ready(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def state_value(task) -> str:
    state = getattr(task.status, "state", "")
    return str(getattr(state, "value", state))


def make_task(text: str) -> Task:
    message = Message(content=TextContent(text=text), role=MessageRole.USER)
    return Task(id="task-" + str(uuid.uuid4()), message=message.to_dict())


class TestAgentCards(unittest.TestCase):
    def test_weather_card_basic(self):
        self.assertEqual(weather_card.name, "WeatherQueryAssistant")
        self.assertIn("天气查询", weather_card.description)
        self.assertEqual(weather_card.url, "http://localhost:5005")
        self.assertEqual(len(weather_card.skills), 1)

    def test_weather_skill_examples(self):
        skill = weather_card.skills[0]
        self.assertIn("weather", skill.name.lower())
        self.assertGreater(len(skill.examples), 0)

    def test_ticket_card_skills(self):
        self.assertEqual(ticket_card.name, "TicketAssistant")
        self.assertEqual(ticket_card.url, "http://localhost:5006")
        self.assertEqual(len(ticket_card.skills), 6)

    def test_ticket_query_and_order_skills(self):
        names = [s.name for s in ticket_card.skills]
        self.assertEqual(len([n for n in names if 'query' in n.lower()]), 3)
        self.assertEqual(len([n for n in names if 'order' in n.lower()]), 3)

    def test_trip_card_skills(self):
        self.assertEqual(trip_card.name, "TripAssistant")
        self.assertEqual(trip_card.url, "http://localhost:5007")
        self.assertEqual(len(trip_card.skills), 6)

    def test_trip_has_all_skills(self):
        names = [s.name.lower() for s in trip_card.skills]
        self.assertTrue(any('car' in n for n in names))
        self.assertTrue(any('tour' in n for n in names))
        self.assertTrue(any('insurance' in n for n in names))

    def test_server_instances(self):
        self.assertEqual(WeatherQueryServer().agent_card.name, "WeatherQueryAssistant")
        self.assertEqual(TicketQueryServer().agent_card.name, "TicketAssistant")
        self.assertEqual(TripQueryServer().agent_card.name, "TripAssistant")


class TestTaskStateMachine(unittest.TestCase):
    """课件验收点：不能仅靠「请提供/请确认」判断 INPUT_REQUIRED。"""

    def setUp(self):
        self.server = TicketQueryServer()

    def _handle(self, payload):
        self.server.query_fn = lambda conversation: payload
        return self.server.handle_task(make_task("查询火车票"))

    def test_structured_input_required(self):
        task = self._handle({"status": "input_required", "message": "请提供出发日期？"})
        self.assertEqual(state_value(task), "input-required")

    def test_structured_completed(self):
        task = self._handle({"status": "success", "message": "G264 二等座 409.88 元", "need_input": False})
        self.assertEqual(state_value(task), "completed")
        self.assertIn("G264", task.artifacts[0]["parts"][0]["text"])

    def test_structured_failed(self):
        task = self._handle({"status": "error", "message": "MCP 连接失败"})
        self.assertEqual(state_value(task), "failed")

    def test_explicit_need_input_mark(self):
        task = self._handle({"status": "success", "message": "请问您想查询哪天？", "need_input": True})
        self.assertEqual(state_value(task), "input-required")

    def test_legacy_pure_followup(self):
        task = self._handle({"status": "success", "message": "请提供出发城市和到达城市？"})
        self.assertEqual(state_value(task), "input-required")

    def test_no_false_positive_when_confirm_with_data(self):
        task = self._handle({"status": "success",
                             "message": "为您找到 G942 次列车，商务座 808.51 元，余票 19 张，请确认后预订。"})
        self.assertEqual(state_value(task), "completed")

    def test_no_false_positive_when_provide_with_data(self):
        task = self._handle({"status": "success",
                             "message": "查询结果：G101 2025-07-30 09:05 出发，662.00 元，请提供是否预订？"})
        self.assertEqual(state_value(task), "completed")

    def test_heuristic_requires_short_text(self):
        self.assertFalse(heuristic_need_input("请提供城市？" + "。" * 200))
        self.assertTrue(heuristic_need_input("请提供出发城市？"))

    def test_classify_result_matrix(self):
        cases = [
            ({"status": "input_required", "message": "请补充日期"}, "input_required"),
            ({"status": "success", "message": "今天天气晴", "need_input": False}, "completed"),
            ({"status": "error", "message": "超时"}, "failed"),
            ({}, "completed"),
        ]
        for payload, expected in cases:
            self.assertEqual(classify_result(payload)[0], expected)


@unittest.skipUnless(all(port_ready(p) for p in (5005, 5006, 5007, 8001, 8002, 8003)),
                     "需先启动 MCP 与 A2A 服务：python scripts/start_all.py --offline")
class TestTicketA2AIntegration(unittest.TestCase):
    """课件集成测试场景：票务 A2A 服务追问与正常查询的状态验证。"""

    def _send(self, text: str):
        client = A2AClient("http://127.0.0.1:5006", timeout=120)
        return asyncio.run(client.send_task_async(make_task(text)))

    def test_missing_slots_returns_input_required(self):
        task = self._send("查一下火车票")
        self.assertEqual(state_value(task), "input-required")

    def test_full_query_returns_completed(self):
        task = self._send("查询北京到上海 2025-07-30 的二等座火车票")
        self.assertEqual(state_value(task), "completed")
        self.assertTrue(task.artifacts)

    def test_trip_semantic_search(self):
        client = A2AClient("http://127.0.0.1:5007", timeout=120)
        task = asyncio.run(client.send_task_async(make_task("想看雪山的地方")))
        self.assertEqual(state_value(task), "completed")
        self.assertIn("雪山", task.artifacts[0]["parts"][0]["text"])


if __name__ == "__main__":
    unittest.main()
