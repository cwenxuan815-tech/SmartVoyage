"""SmartVoyage 命令行客户端。

启动：python -m SmartVoyage.main
调试命令：cards（代理卡片）/ memory（记忆状态）/ clear（清空记忆）/ quit（退出）
"""
import asyncio
import socket
import sys

from SmartVoyage.chat_service import ChatService
from SmartVoyage.config import Config
from SmartVoyage.create_logger import logger

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

conf = Config()
chat_service = ChatService()


def initialize_system():
    ports = [5005, 5006, 5007, 8001, 8002, 8003]
    missing = []
    for port in ports:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                pass
        except OSError:
            missing.append(port)
    if missing:
        print(f"[提示] 以下端口尚未就绪: {missing}")
        print("       请先运行: python scripts/start_all.py [--offline]")
    else:
        print("[提示] 3 个 A2A 代理与 3 个 MCP 服务均已就绪")


def display_agent_cards():
    print("\n=== 可用子代理 (AgentCard) ===")
    for card in chat_service.get_agent_cards():
        print(f"\nAgent: {card.get('name')}")
        print(f"  URL: {card.get('url')}")
        print(f"  描述: {card.get('description')}")
        skills = card.get("skills") or []
        if skills:
            for skill in skills[:8]:
                name = skill.get("name") if isinstance(skill, dict) else str(skill)
                print(f"  - {name}")
    print()


def display_memory():
    state = chat_service.get_memory_state()
    print("\n=== 记忆状态 ===")
    print(f"短期对话: {len(state['short_term_messages'])} 条")
    print(f"用户偏好: {state['user_profile'] or '无'}")
    print(f"任务上下文: {state['current_task'] or '无'}")
    print(f"实体历史: {len(state['entity_history'])} 条")
    for msg in state["short_term_messages"][-6:]:
        label = "User" if msg["role"] == "user" else "Assistant"
        print(f"  {label}: {msg['content'][:100]}")
    print()


def process_user_input(user_input: str):
    try:
        response = asyncio.run(chat_service.chat(user_input))
        print(f"\nSmartVoyage: {response}")
        if chat_service.last_agents:
            print(f"[路由至] {', '.join(chat_service.last_agents)}")
    except Exception as exc:
        logger.error(f"CLI 处理失败: {exc}")
        print(f"处理失败: {exc}")


def main():
    initialize_system()
    print("\n基于 A2A 的 SmartVoyage 旅行智能助手")
    print("输入问题后回车；'quit' 退出，'cards' 查看代理卡片，'memory' 查看记忆，'clear' 清空记忆")
    display_agent_cards()
    while True:
        try:
            user_input = input("\n请输入您的问题: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n感谢使用 SmartVoyage！再见！")
            break
        command = user_input.lower()
        if command in ("quit", "exit", "q"):
            print("感谢使用 SmartVoyage！再见！")
            break
        if command == "cards":
            display_agent_cards()
        elif command == "memory":
            display_memory()
        elif command == "clear":
            chat_service.clear_memory()
            print("记忆已清空。")
        elif user_input:
            process_user_input(user_input)


if __name__ == "__main__":
    main()
