"""行程管家 A2A 代理服务器（端口 5007）：租车、旅游团、保险查询与预订。

启动：python -m SmartVoyage.a2a_server.trip_server
"""
import os

from python_a2a import AgentCard, AgentSkill

from SmartVoyage.a2a_server.base_agent import (
    BaseQueryServer, NEED_INPUT_MARK, query_via_mcp, run_agent_server,
)
from SmartVoyage.a2a_server.offline import offline_trip
from SmartVoyage.config import Config

conf = Config()
MCP_URL = conf.mcp_urls["trip"]

SYSTEM_PROMPT = f"""你是一个行程管家助手，能调用工具完成租车查询/预定、旅游团查询/报名、保险查询/购买。
当前日期是 {{current_date}}。
仔细分析用户问题，提取工具所需参数后调用对应工具。
注意：
- query_tour_group 使用语义搜索，query_text 传用户的自然语言描述（如「想看雪山的地方」）；
- query_car_rental 需要取车城市、还车城市、日期；
- query_insurance 可不传 insurance_type，返回全部保险产品。
规则：
1. 缺少必填参数且无法推断时，不要编造参数、不要调用工具，只输出一行以 {NEED_INPUT_MARK} 开头的追问。
2. 查询成功后用中文总结名称、价格、余量/亮点，不要输出原始 JSON。
3. 结果数据中出现「请确认」等字样时仍属正常结果，禁止输出追问标记。"""

agent_card = AgentCard(
    name="TripAssistant",
    description="基于 LangChain 提供行程管家服务的统一助手，支持租车、旅游团、保险的查询与预订",
    url=os.getenv("TRIP_A2A_PUBLIC_URL", "http://localhost:5007"),
    version="1.0.0",
    capabilities={"streaming": True, "memory": True},
    skills=[
        AgentSkill(name="query car rental", description="查询租车信息", examples=["租车 成都 2026-05-01"]),
        AgentSkill(name="query tour group", description="通过语义搜索查询旅游团信息", examples=["想看雪山的地方"]),
        AgentSkill(name="query insurance", description="查询旅行保险产品", examples=["旅行保险"]),
        AgentSkill(name="order car rental", description="预订租车服务", examples=["预订租车 2026-05-01 SUV 1辆"]),
        AgentSkill(name="order tour group", description="报名旅游团", examples=["报名丽江三日游 2人"]),
        AgentSkill(name="order insurance", description="购买旅行保险", examples=["购买综合型保险"]),
    ],
)


async def query_trip(conversation: str) -> dict:
    """通过 LangChain Agent + MCP Tools 执行行程查询或预订。"""
    return await query_via_mcp(conversation, MCP_URL, SYSTEM_PROMPT, offline_trip)


class TripQueryServer(BaseQueryServer):
    query_fn = staticmethod(query_trip)

    def __init__(self):
        super().__init__(agent_card=agent_card)


def main():
    run_agent_server(TripQueryServer(), 5007, "TRIP_A2A_PORT")


if __name__ == "__main__":
    main()
