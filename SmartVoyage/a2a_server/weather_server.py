"""天气 A2A 代理服务器（端口 5005）：LangChain Agent + MCP 工具决策。

启动：python -m SmartVoyage.a2a_server.weather_server
"""
import os

from python_a2a import AgentCard, AgentSkill

from SmartVoyage.a2a_server.base_agent import (
    BaseQueryServer, NEED_INPUT_MARK, query_via_mcp, run_agent_server,
)
from SmartVoyage.a2a_server.offline import offline_weather
from SmartVoyage.config import Config

conf = Config()
MCP_URL = conf.mcp_urls["weather"]

SYSTEM_PROMPT = f"""你是一个天气查询助手，能够调用天气查询工具。
仔细分析用户问题，提取城市和日期信息，然后调用 query_weather 工具。
当前日期是 {{current_date}}。
规则：
1. 缺少城市或日期等关键信息且无法合理推断时，不要调用工具，只输出一行以 {NEED_INPUT_MARK} 开头的追问，例如「{NEED_INPUT_MARK} 请提供要查询的城市和日期？」。
2. 用户只说「天气」「今天天气」时，city 传「全国」以查询北京/上海/广州/深圳四大热门城市，日期用当前日期并向后延伸 2 天。
3. 成功拿到工具结果后，用简洁中文总结天气、温度、湿度、风力和出行建议，不要输出原始 JSON。
4. 结果中若包含数据，即使出现「请确认」等字样，也按正常结果总结，不要输出追问标记。"""

agent_card = AgentCard(
    name="WeatherQueryAssistant",
    description="基于 LangChain 提供天气查询服务的助手",
    url=os.getenv("WEATHER_A2A_PUBLIC_URL", "http://localhost:5005"),
    version="1.0.0",
    capabilities={"streaming": True, "memory": True},
    skills=[
        AgentSkill(
            name="query weather",
            description="查询天气数据，支持自然语言输入",
            examples=["北京 2025-07-30 天气", "上海未来3天天气如何", "明天天气怎么样"],
        )
    ],
)


async def query_weather(conversation: str) -> dict:
    """通过 LangChain Agent + MCP Tools 执行天气查询。"""
    return await query_via_mcp(conversation, MCP_URL, SYSTEM_PROMPT, offline_weather)


class WeatherQueryServer(BaseQueryServer):
    query_fn = staticmethod(query_weather)

    def __init__(self):
        super().__init__(agent_card=agent_card)


def main():
    run_agent_server(WeatherQueryServer(), 5005, "WEATHER_A2A_PORT")


if __name__ == "__main__":
    main()
