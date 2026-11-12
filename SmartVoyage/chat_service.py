"""核心对话服务：Planning + ReAct 架构的多智能体编排器。

流程：记忆 → 意图识别 → 启发式路由（跳过无谓规划）→ 并行执行 / ReAct 循环 → 结果汇总 → 记忆持久化。
"""
import asyncio
import json
import re
import uuid
from datetime import datetime

import pytz
import requests
from langchain_openai import ChatOpenAI
from python_a2a import A2AClient, AgentNetwork, Message, MessageRole, Task, TextContent

from SmartVoyage.config import Config
from SmartVoyage.create_logger import logger
from SmartVoyage.db import get_connection
from SmartVoyage.main_prompts import SmartVoyagePrompts
from SmartVoyage.memory import ConversationMemory

conf = Config()

INDEPENDENT_INTENTS = {
    "weather", "flight", "train", "concert", "attraction",
    "car_rental", "tour_group", "insurance", "trip_order",
}
INTENT_KEYWORDS = [
    ("car_rental", r"租车|包车|用车"),
    ("tour_group", r"旅游团|跟团|团游|雪山|亲子|海边|草原|古镇|度假"),
    ("insurance", r"保险|保障"),
    ("concert", r"演唱会|演出|音乐会|门票"),
    ("train", r"火车|高铁|动车|车票|车次"),
    ("flight", r"机票|航班|飞机|飞往"),
    ("attraction", r"景点|好玩|游玩|必去|打卡"),
    ("weather", r"天气|气温|下雨|降雨|温度|适合出行"),
]
OFFLINE_ATTRACTIONS = {
    "北京": ["故宫博物院", "天坛公园", "颐和园"],
    "上海": ["外滩", "豫园", "上海博物馆"],
    "成都": ["大熊猫繁育研究基地", "宽窄巷子", "都江堰"],
    "杭州": ["西湖", "灵隐寺", "西溪湿地"],
}
CITY_RE = re.compile("|".join(["北京", "上海", "广州", "深圳", "成都", "杭州", "南京", "西安", "三亚"]))
DATE_RE = re.compile(r"20\d{2}[-/年.]\d{1,2}[-/月.]\d{1,2}|明天|后天|今天")
SLOT_RE = re.compile(
    r"二等座|一等座|商务座|硬座|经济舱|商务舱|头等舱|看台票|内场票|VIP|"
    r"经济型|SUV|MPV|综合型|意外型|医疗型|境外型|"
    r"北京|上海|广州|深圳|成都|杭州|南京|西安|三亚|20\d{2}[-/年.]\d{1,2}[-/月.]\d{1,2}"
)


def _as_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(str(v) for v in value.values() if v)
    return str(value or "")


def _parse_json(text: str) -> dict:
    """宽容地解析 LLM 返回的 JSON（兼容 Markdown 代码块与前后缀文字）。"""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip(), flags=re.I).strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                pass
    logger.warning(f"LLM 输出无法解析为 JSON: {cleaned[:160]}")
    return {}


def _status_text(task) -> str:
    message = getattr(task.status, "message", None)
    if isinstance(message, dict):
        content = message.get("content") or {}
        return content.get("text", "") if isinstance(content, dict) else str(content)
    if message is not None:
        content = getattr(message, "content", None)
        return getattr(content, "text", str(content or ""))
    return ""


def _state_value(task) -> str:
    state = getattr(task.status, "state", "")
    return str(getattr(state, "value", state))


class ChatService:
    """对话编排中枢：注册 A2A 子代理、管理记忆、路由并执行任务。"""

    def __init__(self):
        self.agent_urls = dict(conf.agent_urls)
        self.agent_network = AgentNetwork(name="旅行助手网络")
        for name, url in self.agent_urls.items():
            self.agent_network.add(name, A2AClient(url, timeout=120))

        self.llm = None
        if conf.api_key and not conf.offline:
            self.llm = ChatOpenAI(
                model=conf.model_name, api_key=conf.api_key,
                base_url=conf.base_url, temperature=conf.temperature,
            )

        self.memory = ConversationMemory(short_term_limit=10)
        self.messages = []
        self.conversation_history = ""
        self._awaiting_followup = False
        self._pending_history = False
        self.last_agents = []
        self._init_db_and_load_memory()

    # ---------------- 初始化与记忆 ----------------
    def _init_db_and_load_memory(self):
        try:
            conn = get_connection()
            self.memory.set_db_connection(conn)
            self.memory.load_profile_from_db()
            self.memory.load_entities_from_db()
            self.memory.load_messages_from_db()
            for msg in self.memory.short_term_messages:
                self.messages.append({"role": msg["role"], "content": msg["content"]})
        except Exception as exc:
            logger.warning(f"数据库连接初始化失败，记忆降级为纯内存: {exc}")

    def get_memory_state(self) -> dict:
        return {
            "short_term_messages": self.memory.short_term_messages,
            "user_profile": self.memory.user_profile,
            "current_task": self.memory.current_task,
            "entity_history": self.memory.entity_history[-5:],
            "messages_count": len(self.messages),
        }

    def update_user_profile(self, profile: dict) -> None:
        self.memory.update_profile(profile)

    def clear_memory(self) -> None:
        self.memory.clear()
        self.messages = []

    def get_agent_cards(self) -> list:
        """能力发现：优先从各 A2A 服务拉取 AgentCard，离线时回退本地静态卡片。"""
        cards = []
        for name, url in self.agent_urls.items():
            try:
                response = requests.get(
                    f"{url}/agent.json", headers={"Accept": "application/json"}, timeout=1.5
                )
                if response.ok and "json" in response.headers.get("Content-Type", "").lower():
                    card = response.json()
                    cards.append({
                        "name": card.get("name", name),
                        "url": card.get("url", url),
                        "version": card.get("version", "1.0.0"),
                        "description": card.get("description", ""),
                        "skills": card.get("skills", []),
                    })
                    continue
            except requests.RequestException:
                pass
            cards.append({
                "name": name, "url": url, "version": "1.0.0",
                "description": f"{name}（A2A 子代理，服务未连接时展示本地卡片）",
                "skills": [],
            })
        return cards

    # ---------------- 意图识别 ----------------
    def _enrich_query(self, user_input: str) -> str:
        """多轮对话：仅在子代理明确追问、用户本轮补充信息时，才用历史补全槽位。"""
        if not getattr(self, "_pending_history", False):
            return user_input
        if CITY_RE.search(user_input) and DATE_RE.search(user_input):
            return user_input
        for msg in reversed(self.memory.short_term_messages[:-1]):
            if msg["role"] != "user":
                continue
            history = msg["content"]
            if CITY_RE.search(history) or DATE_RE.search(history):
                return f"历史上下文：{history}\n本轮问题：{user_input}"
            break
        return user_input

    def _offline_subqueries(self, intents: list, user_input: str) -> dict:
        """离线多意图：按连接词切出各意图对应的子查询，避免城市/日期串味。"""
        if len(intents) <= 1:
            return {intents[0]: user_input}
        parts = [p.strip() for p in re.split(r"和|还有|，|,|以及|另外|；|;", user_input) if p.strip()]
        patterns = dict(INTENT_KEYWORDS)
        result = {}
        for intent in intents:
            matched = [p for p in parts if re.search(patterns.get(intent, r"(?!x)x"), p)]
            chosen = matched[0] if matched else user_input
            if not DATE_RE.search(chosen):
                date_match = DATE_RE.search(user_input)
                if date_match:
                    chosen += " " + date_match.group()
            if not CITY_RE.search(chosen):
                cities = CITY_RE.findall(user_input)
                if cities:
                    chosen = cities[0] + " " + chosen
            result[intent] = chosen
        return result

    def _offline_intent(self, user_input: str):
        """离线规则式意图识别（不调用 LLM，仍支持多意图与追问链路）。"""
        intents = [name for name, pattern in INTENT_KEYWORDS if re.search(pattern, user_input)]
        enriched = user_input
        previous = self.memory.current_task.get("type")
        if not intents and previous in dict(INTENT_KEYWORDS):
            if getattr(self, "_pending_history", False):
                # 子代理上一轮在追问：继承意图并带上历史上下文
                intents = [previous]
                enriched = self._enrich_query(user_input)
            elif SLOT_RE.search(user_input):
                # 上一轮查询成功，本轮只补充槽位（如"二等座"）：沿用上一轮查询条件
                intents = [previous]
                last_query = self.memory.current_task.get("query", "")[:200]
                # 本轮补充放最前面，使新槽位覆盖历史槽位（如二等座 → 商务座）
                enriched = f"{user_input} {last_query}" if last_query else user_input
        if not intents:
            if re.search(r"订|预订|预定|买", user_input):
                intents = ["order"]
            else:
                return ["out_of_scope"], {}, "我是 SmartVoyage 旅行助手，可以帮您查天气、票务、租车、保险、旅游团和景点，换个旅行相关的问题试试吧。"
        return intents, self._offline_subqueries(intents, enriched), ""

    def intent_agent(self, user_input: str):
        """识别意图，注入短期对话、用户偏好、当前日期与任务上下文。"""
        current_date = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')
        if self.llm is None:
            return self._offline_intent(user_input)
        chain = SmartVoyagePrompts.intent_prompt() | self.llm
        response = chain.invoke({
            "conversation_history": self.memory.get_short_term_text(),
            "query": user_input,
            "current_date": current_date,
            "user_profile": self.memory.get_profile_text(),
            "task_context": json.dumps(self.memory.current_task, ensure_ascii=False),
        }).content.strip()
        parsed = _parse_json(response)
        if not parsed:
            return ["out_of_scope"], {}, "抱歉，我没能理解您的需求，可以再说得具体一些吗？"
        return (
            parsed.get("intents", []),
            parsed.get("user_queries", {}),
            parsed.get("follow_up_message", ""),
        )

    # ---------------- 规划与 ReAct ----------------
    def _should_skip_planning(self, intents: list) -> bool:
        if len(intents) <= 1:
            return True
        return all(intent in INDEPENDENT_INTENTS for intent in intents)

    def planning_agent(self, intents: list, user_queries: dict) -> dict:
        if self.llm is None:
            steps = [
                {"intent": intent, "query": _as_text(user_queries.get(intent, "")),
                 "depends_on": [intents[index - 1]] if index else []}
                for index, intent in enumerate(intents)
            ]
            return {"need_plan": len(steps) > 1, "reason": "离线规则规划：按意图顺序串行执行", "steps": steps}
        chain = SmartVoyagePrompts.planning_prompt() | self.llm
        response = chain.invoke({
            "current_date": datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d'),
            "user_profile": self.memory.get_profile_text(),
            "conversation_history": self.memory.get_short_term_text(),
            "intents": json.dumps(intents, ensure_ascii=False),
            "user_queries": json.dumps(user_queries, ensure_ascii=False, default=str),
        }).content.strip()
        return _parse_json(response) or {"need_plan": False, "reason": "规划解析失败，直接执行", "steps": []}

    async def react_loop(self, steps: list, user_queries: dict) -> str:
        """ReAct 循环：Thought（排序）→ Action（调用子代理）→ Observation（记录结果）→ 汇总。"""
        observations, results = [], []
        for index, step in enumerate(steps or [], start=1):
            intent = step.get("intent") if isinstance(step, dict) else str(step)
            query = (step.get("query") if isinstance(step, dict) else "") or _as_text(user_queries.get(intent, ""))
            depends = step.get("depends_on", []) if isinstance(step, dict) else []
            thought = f"步骤{index}：执行意图 {intent}" + (f"（依赖 {depends} 的结果）" if depends else "")
            logger.info(f"[Thought] {thought}")
            result = await self._call_agent_intent(intent, query)
            observations.append(f"{thought}\n[Observation] {result}")
            results.append(result)
        if self.llm and len(results) > 1:
            chain = SmartVoyagePrompts.react_summary_prompt() | self.llm
            return chain.invoke({
                "query": "；".join(_as_text(v) for v in user_queries.values()),
                "user_profile": self.memory.get_profile_text(),
                "observations": "\n\n".join(observations),
            }).content.strip()
        return "\n\n".join(results)

    # ---------------- 子代理统一调用 ----------------
    async def _call_agent_intent(self, intent: str, query_value, use_history: bool = False) -> str:
        query_str = _as_text(query_value)
        agent_name = conf.intent.get(intent)

        if intent == "attraction":
            if self.llm is None:
                city = CITY_RE.search(query_str)
                spots = OFFLINE_ATTRACTIONS.get(city.group() if city else "", ["本地博物馆", "城市公园", "老街"])
                return "景点推荐（离线）：\n" + "\n".join(f"- {name}：建议游玩 2~3 小时" for name in spots)
            chain = SmartVoyagePrompts.attraction_prompt() | self.llm
            return chain.invoke({"query": query_str}).content.strip()

        if not agent_name:
            return "暂不支持此意图。"

        if intent in ("flight", "train", "concert", "car_rental", "tour_group", "insurance"):
            self.memory.extract_entities(intent, query_str)
            self.memory.update_task_context({"type": intent, "query": query_str})

        agent = self.agent_network.get_agent(agent_name)
        # 只有上一轮子代理明确要求补充信息时，才把历史对话带给子代理，
        # 否则独立的新提问不应被历史城市/日期污染。
        if use_history:
            prior = self.memory.short_term_messages[:-1][-4:]
            history = "\n".join(
                f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}" for msg in prior
            )
            chat_history = (history + "\n" if history else "") + f"User: {query_str}"
        else:
            chat_history = f"User: {query_str}"
        message = Message(content=TextContent(text=chat_history), role=MessageRole.USER)
        task = Task(id="task-" + str(uuid.uuid4()), message=message.to_dict())
        raw_response = await asyncio.to_thread(asyncio.run, agent.send_task_async(task))

        state = _state_value(raw_response)
        if state == "completed" and raw_response.artifacts:
            parts = raw_response.artifacts[0].get("parts", [])
            agent_result = parts[0].get("text", "") if parts else ""
        elif state == "input-required":
            # 子代理要求补充信息：原样透传追问，并标记下一轮需要带上历史上下文
            self._awaiting_followup = True
            return _status_text(raw_response) or "请补充更多信息后重试。"
        else:
            agent_result = _status_text(raw_response) or "查询失败，请稍后重试。"

        if self.llm is None:
            return agent_result
        prompt = (SmartVoyagePrompts.summarize_weather_prompt()
                  if agent_name == "WeatherQueryAssistant"
                  else SmartVoyagePrompts.summarize_ticket_prompt())
        chain = prompt | self.llm
        return chain.invoke({"query": query_str, "raw_response": agent_result}).content.strip()

    # ---------------- 主入口 ----------------
    async def chat(self, user_input: str) -> str:
        awaiting = self._awaiting_followup
        self._awaiting_followup = False
        self._pending_history = awaiting
        self.memory.add_message("user", user_input)
        self.messages.append({"role": "user", "content": user_input})
        try:
            intents, user_queries, follow_up_message = self.intent_agent(user_input)
            logger.info(f"意图识别: {intents}")
            self.last_agents = [
                conf.intent.get(intent) or ("AttractionAssistant" if intent == "attraction" else "")
                for intent in intents if intent != "out_of_scope"
            ]
            self.last_agents = [name for name in self.last_agents if name]

            if "out_of_scope" in intents:
                response = follow_up_message or "暂不支持该问题，请咨询旅行相关内容。"
            elif follow_up_message:
                response = follow_up_message
            else:
                if self._should_skip_planning(intents):
                    plan = {"need_plan": False, "reason": "任务简单，可直接执行", "steps": []}
                else:
                    plan = self.planning_agent(intents, user_queries)

                if plan.get("need_plan"):
                    response = await self.react_loop(plan.get("steps", []), user_queries)
                else:
                    # 独立多意图并行执行（asyncio.gather）
                    tasks = [
                        self._call_agent_intent(intent, user_queries.get(intent, user_input), awaiting)
                        for intent in intents
                    ]
                    response = "\n\n".join(await asyncio.gather(*tasks)) if tasks else "未识别到可执行任务。"

            self.memory.add_message("assistant", response)
            self.messages.append({"role": "assistant", "content": response})
            self.conversation_history = self.memory.get_short_term_text()
            return response
        except Exception as exc:
            logger.error(f"对话处理失败: {exc}")
            message = f"处理失败：{exc}。请重试或检查各 A2A / MCP 服务是否已启动。"
            self.memory.add_message("assistant", message)
            return message
