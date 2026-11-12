"""A2A 子代理公共能力：LLM + MCP 工具执行、任务状态判定、服务启动。

追问判定优化（对应课件集成测试要求）：
不再仅凭「请提供 / 请确认」两个词判断 INPUT_REQUIRED，而是
1) Agent 输出显式 [NEED_INPUT] 标记时结构化判定；
2) 缺少标记时用「追问句式 + 无结果证据 + 短文本」三条件联合判定；
3) 结果文本中出现车次/航班/日期/票价等数据证据时一律视为 COMPLETED。
"""
import asyncio
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable, Optional

import pytz
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_openai import ChatOpenAI
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from python_a2a import A2AServer, TaskState, TaskStatus, run_server

from SmartVoyage.config import Config
from SmartVoyage.create_logger import logger

conf = Config()
NEED_INPUT_MARK = "[NEED_INPUT]"

FOLLOW_UP_RE = re.compile(
    r"(请(?:您)?(?:提供|补充|告诉|说明|确认一下|选择)|需要(?:您)?(?:提供|补充)|"
    r"还(?:缺|需要)[^，。]{0,10}(?:信息|日期|城市|出发地|目的地|车次)|"
    r"请问(?:您)?(?:想|要|需要|是)|无法(?:确定|识别)[^，。]{0,10}(?:日期|城市|车次))"
)
RESULT_EVIDENCE_RE = re.compile(
    r"(\bG\d{1,4}\b|\bD\d{1,4}\b|\b[A-Z]{2}\d{3,4}\b|[¥￥]|\d+(?:\.\d+)?\s*元|"
    r"\d{1,2}\s*℃|\d{4}-\d{2}-\d{2}|车次|航班号|票价|余票|气温|湿度|"
    r"以下(?:是|为)|查询(?:到|结果)|共(?:找到|有)|推荐)"
)


def current_date() -> str:
    return datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d')


def build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=conf.model_name,
        base_url=conf.base_url,
        api_key=conf.api_key or "offline",
        temperature=conf.temperature,
    )


def run_async(coro):
    """在同步 handle_task 中安全执行协程（兼容已有事件循环的服务器线程）。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def query_via_mcp(conversation: str, mcp_url: str, system_prompt: str,
                        offline_router: Optional[Callable] = None) -> dict:
    """连接 MCP Server → 加载工具 → LangChain Agent 决策 → 返回结构化结果。

    离线模式（SV_OFFLINE=1 或未配置 API Key）改用规则式路由，仍走真实 MCP 调用链。
    """
    try:
        async with streamablehttp_client(mcp_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await load_mcp_tools(session)

                if conf.offline or not conf.api_key:
                    if offline_router is None:
                        return {"status": "error", "message": "离线模式未配置规则路由"}
                    return await offline_router(session, conversation)

                prompt = ChatPromptTemplate.from_messages([
                    ("system", system_prompt),
                    ("human", "{input}"),
                    ("placeholder", "{agent_scratchpad}"),
                ])
                agent = create_tool_calling_agent(build_llm(), tools, prompt)
                executor = AgentExecutor(
                    agent=agent, tools=tools, verbose=False,
                    handle_parsing_errors=True, max_iterations=6,
                )
                response = await executor.ainvoke({
                    "input": conversation,
                    "current_date": current_date(),
                })
                text = str(response.get("output", "")).strip()
                need_input = text.startswith(NEED_INPUT_MARK)
                if need_input:
                    text = text[len(NEED_INPUT_MARK):].strip()
                return {"status": "success", "message": text, "need_input": need_input}
    except ExceptionGroup as group:
        first = group.exceptions[0] if group.exceptions else group
        logger.error(f"MCP 查询出错: {first}")
        return {"status": "error", "message": f"MCP 查询出错：{first}"}
    except BaseException as exc:
        logger.error(f"MCP 查询出错: {exc}")
        return {"status": "error", "message": f"MCP 查询出错：{exc}"}


def heuristic_need_input(text: str) -> bool:
    """兜底判定：追问句式 + 无数据证据 + 短文本，三者同时满足才算追问。"""
    if not text or len(text) > 180:
        return False
    if RESULT_EVIDENCE_RE.search(text):
        return False
    if not FOLLOW_UP_RE.search(text):
        return False
    return "?" in text or "？" in text or len(text) < 100


def classify_result(result: dict) -> tuple:
    """把 Agent 结果映射为 (状态类别, 展示文本)，供 handle_task 使用。

    类别: completed / input_required / failed
    """
    status = (result or {}).get("status")
    text = str((result or {}).get("message") or "")
    if status == "error":
        return "failed", text or "查询失败，请重试。"
    if status == "input_required":
        return "input_required", text
    need_input = (result or {}).get("need_input")
    if need_input is True:
        return "input_required", text
    if need_input is False:
        return "completed", text
    # 兼容旧版本/第三方 Agent 输出：仅靠文本时采用保守的联合判定
    return ("input_required", text) if heuristic_need_input(text) else ("completed", text)


class BaseQueryServer(A2AServer):
    """通用 A2A 任务处理器：解析消息 → 执行查询 → 按结构化结果设置状态。"""

    query_fn: Callable = None

    def handle_task(self, task):
        content = (task.message or {}).get("content", {})
        conversation = content.get("text", "") if isinstance(content, dict) else ""
        logger.info(f"[{self.agent_card.name}] 用户查询: {conversation}")
        try:
            outcome = self.query_fn(conversation)
            if asyncio.iscoroutine(outcome):
                outcome = run_async(outcome)
            kind, text = classify_result(outcome)

            if kind == "completed":
                task.artifacts = [{"parts": [{"type": "text", "text": text}]}]
                task.status = TaskStatus(state=TaskState.COMPLETED)
            elif kind == "input_required":
                task.status = TaskStatus(
                    state=TaskState.INPUT_REQUIRED,
                    message={"role": "agent", "content": {"text": text}},
                )
            else:
                task.status = TaskStatus(
                    state=TaskState.FAILED,
                    message={"role": "agent", "content": {"text": text}},
                )
            return task
        except Exception as exc:
            logger.error(f"[{self.agent_card.name}] 查询失败: {exc}")
            task.status = TaskStatus(
                state=TaskState.FAILED,
                message={"role": "agent", "content": {"text": f"查询失败: {exc} 请重试。"}},
            )
            return task


def run_agent_server(server: BaseQueryServer, default_port: int, port_env: str) -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv(port_env, os.getenv("PORT", str(default_port))))
    print(f"\n=== 服务器信息 ===")
    print(f"名称: {server.agent_card.name}")
    print(f"描述: {server.agent_card.description}")
    print("\n技能:")
    for skill in server.agent_card.skills:
        print(f"- {skill.name}: {skill.description}")
    logger.info(f"{server.agent_card.name} 启动于 {host}:{port}")
    run_server(server, host=host, port=port)
