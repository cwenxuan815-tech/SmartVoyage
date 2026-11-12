"""SmartVoyage 端到端联调：A2AClient → A2A Agent → MCP Server → 数据库。

用法（需先启动服务）：
    python scripts/smoke_test.py
    python scripts/smoke_test.py --case ticket
"""
import argparse
import asyncio
import socket
import time
import uuid

from python_a2a import A2AClient, Message, MessageRole, Task, TextContent

PORTS = {
    "ticket_mcp": 8001, "weather_mcp": 8002, "trip_mcp": 8003,
    "weather_a2a": 5005, "ticket_a2a": 5006, "trip_a2a": 5007,
}
ENDPOINTS = {
    "weather": "http://127.0.0.1:5005",
    "ticket": "http://127.0.0.1:5006",
    "trip": "http://127.0.0.1:5007",
}
CASES = [
    ("weather", "北京 2025-07-30 的天气怎么样", "completed"),
    ("weather", "北京和上海 2025-08-11 天气对比", "completed"),
    ("ticket", "查询北京到上海 2025-07-30 的二等座火车票", "completed"),
    ("ticket", "查一下火车票", "input-required"),
    ("ticket", "北京到成都 2026-05-01 的机票", "completed"),
    ("trip", "查询综合型旅行保险", "completed"),
    ("trip", "成都 2026-05-01 租车", "completed"),
    ("trip", "想看雪山的地方", "completed"),
]


def port_ready(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def wait_services(timeout: int = 60) -> bool:
    deadline = time.time() + timeout
    pending = set(PORTS)
    while time.time() < deadline:
        pending = {name for name in pending if not port_ready(PORTS[name])}
        if not pending:
            return True
        time.sleep(0.5)
    print(f"以下服务未就绪: {sorted(pending)}")
    return False


def send_task(endpoint: str, text: str):
    client = A2AClient(endpoint, timeout=120)
    message = Message(content=TextContent(text=text), role=MessageRole.USER)
    task = Task(id="task-" + str(uuid.uuid4()), message=message.to_dict())
    return asyncio.run(client.send_task_async(task))


def display(response) -> str:
    state = getattr(response.status, "state", None)
    state = getattr(state, "value", state)
    if response.artifacts:
        parts = response.artifacts[0].get("parts", [])
        text = parts[0].get("text", "") if parts else ""
    else:
        message = getattr(response.status, "message", None) or {}
        if hasattr(message, "get"):
            text = (message.get("content") or {}).get("text", "")
        else:
            text = str(message)
    return str(state), text


def main():
    parser = argparse.ArgumentParser(description="SmartVoyage 端到端联调")
    parser.add_argument("--case", choices=["all", "weather", "ticket", "trip"], default="all")
    args = parser.parse_args()

    if not wait_services():
        raise SystemExit("服务未全部就绪，请先运行 scripts/start_all.py")
    print("6 个服务端口全部就绪\n")

    passed = 0
    cases = [c for c in CASES if args.case in ("all", c[0])]
    for agent, query, expected in cases:
        try:
            state, text = display(send_task(ENDPOINTS[agent], query))
        except Exception as exc:
            print(f"[ERROR] {agent} | {query} -> {type(exc).__name__}: {exc}")
            continue
        ok = state == expected
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {agent} | {query}")
        print(f"       状态={state}（期望 {expected}） 回复={text[:180].replace(chr(10), ' | ')}")
    print(f"\n结果: {passed}/{len(cases)} 通过")


if __name__ == "__main__":
    main()
