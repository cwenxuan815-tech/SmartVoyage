"""票务 A2A 代理服务器（端口 5006）：火车票、机票、演唱会票查询与预定。

启动：python -m SmartVoyage.a2a_server.ticket_server
"""
import os

from python_a2a import AgentCard, AgentSkill

from SmartVoyage.a2a_server.base_agent import (
    BaseQueryServer, NEED_INPUT_MARK, query_via_mcp, run_agent_server,
)
from SmartVoyage.a2a_server.offline import offline_ticket
from SmartVoyage.config import Config

conf = Config()
MCP_URL = conf.mcp_urls["ticket"]

SYSTEM_PROMPT = f"""你是一个票务查询和预定助手，能调用工具完成火车票、机票、演唱会票的查询和预定。
当前日期是 {{current_date}}。
仔细分析用户问题，提取必要参数（出发城市、到达城市、日期、座位类型/舱位、艺人、场馆、数量等），再调用对应工具。
规则：
1. 缺少任一必填参数且无法从历史对话推断时，不要编造参数、不要调用工具，只输出一行以 {NEED_INPUT_MARK} 开头的追问，例如「{NEED_INPUT_MARK} 请提供出发城市、到达城市和出发日期？」。
2. 查询成功后，用中文列出车次/航班/艺人、时间、票价和余票，并给出简短建议；不要输出原始 JSON。
3. 结果数据中出现「请确认车次」「请核对信息」等字样时仍属正常结果，禁止输出追问标记。
4. 用户明确要预订且参数齐全时，调用对应的 order 工具。"""

agent_card = AgentCard(
    name="TicketAssistant",
    description="基于 LangChain 提供票务查询和预定服务的统一助手",
    url=os.getenv("TICKET_A2A_PUBLIC_URL", "http://localhost:5006"),
    version="1.0.0",
    capabilities={"streaming": True, "memory": True},
    skills=[
        AgentSkill(name="query train tickets", description="查询火车票信息", examples=["北京到上海的高铁 2025-07-30"]),
        AgentSkill(name="query flight tickets", description="查询航班机票信息", examples=["上海到北京的机票 10月28日"]),
        AgentSkill(name="query concert tickets", description="查询演唱会门票信息", examples=["刀郎北京演唱会门票"]),
        AgentSkill(name="order train tickets", description="预定火车票", examples=["帮我订一张G264二等座"]),
        AgentSkill(name="order flight tickets", description="预定机票", examples=["订一张经济舱机票"]),
        AgentSkill(name="order concert tickets", description="预定演唱会票", examples=["买两张刀郎演唱会VIP票"]),
    ],
)


async def query_tickets(conversation: str) -> dict:
    """通过 LangChain Agent + MCP Tools 执行票务查询或预定。"""
    return await query_via_mcp(conversation, MCP_URL, SYSTEM_PROMPT, offline_ticket)


class TicketQueryServer(BaseQueryServer):
    query_fn = staticmethod(query_tickets)

    def __init__(self):
        super().__init__(agent_card=agent_card)


def main():
    run_agent_server(TicketQueryServer(), 5006, "TICKET_A2A_PORT")


if __name__ == "__main__":
    main()
