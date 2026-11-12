"""测试：提示词模板、启发式路由、多意图子查询切分、记忆持久化与对话编排。"""
import asyncio
import os
import socket
import unittest

os.environ.setdefault("SV_OFFLINE", "1")

from SmartVoyage.chat_service import ChatService  # noqa: E402
from SmartVoyage.main_prompts import SmartVoyagePrompts  # noqa: E402
from SmartVoyage.memory import ConversationMemory  # noqa: E402


def port_ready(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


class TestPrompts(unittest.TestCase):
    def test_intent_prompt_renders(self):
        rendered = SmartVoyagePrompts.intent_prompt().invoke({
            "current_date": "2026-11-10", "conversation_history": "",
            "user_profile": "无已知的用户偏好", "task_context": "{}", "query": "北京天气",
        }).to_string()
        self.assertIn('"intents": ["weather"]', rendered)
        self.assertIn("北京天气", rendered)

    def test_all_prompts_have_expected_variables(self):
        expected = {
            "planning_prompt": {"intents", "user_queries", "current_date"},
            "react_summary_prompt": {"query", "observations", "user_profile"},
            "attraction_prompt": {"query"},
            "summarize_weather_prompt": {"query", "raw_response"},
            "summarize_ticket_prompt": {"query", "raw_response"},
        }
        for name, variables in expected.items():
            prompt = getattr(SmartVoyagePrompts, name)()
            self.assertTrue(variables.issubset(set(prompt.input_variables)), name)
            prompt.invoke({v: "示例" for v in prompt.input_variables})


class TestChatServiceLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = ChatService()

    def setUp(self):
        self.service.clear_memory()

    def tearDown(self):
        self.service.clear_memory()

    def test_should_skip_planning(self):
        self.assertTrue(self.service._should_skip_planning(["weather"]))
        self.assertTrue(self.service._should_skip_planning(["weather", "train"]))
        self.assertFalse(self.service._should_skip_planning(["weather", "order"]))

    def test_offline_subqueries_split(self):
        queries = self.service._offline_subqueries(
            ["flight", "weather"], "帮我查下北京 2025-08-11 天气，还有北京到成都 2026-05-01 的机票"
        )
        self.assertIn("2025-08-11", queries["weather"])
        self.assertIn("2026-05-01", queries["flight"])
        self.assertIn("机票", queries["flight"])

    def test_multi_intent_slot_isolation(self):
        queries = self.service._offline_subqueries(
            ["car_rental", "insurance"], "成都 2026-05-01 租车和综合型保险"
        )
        self.assertIn("租车", queries["car_rental"])
        self.assertNotIn("租车", queries["insurance"])

    def test_out_of_scope(self):
        intents, _, follow_up = self.service._offline_intent("今天股票涨了吗")
        self.assertEqual(intents, ["out_of_scope"])
        self.assertTrue(follow_up)

    def test_memory_state_and_profile(self):
        self.service.update_user_profile({"座位喜好": "二等座"})
        self.assertEqual(self.service.get_memory_state()["user_profile"]["座位喜好"], "二等座")

    def test_agent_cards_length(self):
        self.assertEqual(len(self.service.get_agent_cards()), 3)


class TestMemoryPersistence(unittest.TestCase):
    def test_short_term_limit_and_reload(self):
        from SmartVoyage.db import get_connection
        memory = ConversationMemory(short_term_limit=3)
        memory.set_db_connection(get_connection())
        memory.clear()
        for i in range(4):
            memory.add_message("user", f"第{i + 1}条")
        memory.update_profile({"seat_type": "二等座"})
        memory.extract_entities("train", "北京到上海 2026-05-01")
        self.assertEqual(len(memory.short_term_messages), 3)
        self.assertEqual(memory.short_term_messages[0]["content"], "第2条")

        restored = ConversationMemory()
        restored.set_db_connection(get_connection())
        restored.load_messages_from_db()
        restored.load_profile_from_db()
        restored.load_entities_from_db()
        self.assertEqual(len(restored.short_term_messages), 3)
        self.assertEqual(restored.user_profile.get("seat_type"), "二等座")
        self.assertEqual(len(restored.entity_history), 1)
        self.assertEqual(len(ConversationMemory.from_dict(restored.to_dict()).short_term_messages), 3)
        restored.clear()


@unittest.skipUnless(all(port_ready(p) for p in (5005, 5006, 5007, 8001, 8002, 8003)),
                     "需先启动 MCP 与 A2A 服务：python scripts/start_all.py --offline")
class TestChatServiceIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = ChatService()

    def setUp(self):
        self.service.clear_memory()

    def test_single_intent_weather(self):
        reply = asyncio.run(self.service.chat("北京 2025-07-30 的天气怎么样"))
        self.assertIn("北京", reply)
        self.assertIn("2025-07-30", reply)

    def test_followup_then_slot_completion(self):
        first = asyncio.run(self.service.chat("查一下火车票"))
        self.assertIn("请提供", first)
        second = asyncio.run(self.service.chat("北京到上海 2025-07-30"))
        self.assertIn("G264", second)

    def test_multi_intent_parallel(self):
        reply = asyncio.run(self.service.chat("帮我查下成都 2026-05-01 天气，还有北京到成都 2026-05-01 的机票"))
        self.assertIn("成都", reply)
        self.assertIn("3U8882", reply)

    def test_tour_group_rag(self):
        reply = asyncio.run(self.service.chat("想看雪山的地方"))
        self.assertIn("雪山", reply)


if __name__ == "__main__":
    unittest.main()
