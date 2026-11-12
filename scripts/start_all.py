"""一键启动 SmartVoyage 全部服务（按依赖顺序：数据层 → MCP → A2A → API）。

用法：
    python scripts/start_all.py                 # 启动 6 个服务（在线 LLM 模式）
    python scripts/start_all.py --offline      # 规则式离线模式，不调用外部 LLM
    python scripts/start_all.py --with-api     # 额外启动 Web API (8080)
    python scripts/start_all.py --group mcp    # 只启动 MCP 层
"""
import argparse
import atexit
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

SERVICES = [
    ("ticket_mcp", "SmartVoyage.mcp_server.mcp_ticket_server", 8001, "TICKET_MCP_PORT", "mcp"),
    ("weather_mcp", "SmartVoyage.mcp_server.mcp_weather_server", 8002, "WEATHER_MCP_PORT", "mcp"),
    ("trip_mcp", "SmartVoyage.mcp_server.mcp_trip_server", 8003, "TRIP_MCP_PORT", "mcp"),
    ("weather_a2a", "SmartVoyage.a2a_server.weather_server", 5005, "WEATHER_A2A_PORT", "a2a"),
    ("ticket_a2a", "SmartVoyage.a2a_server.ticket_server", 5006, "TICKET_A2A_PORT", "a2a"),
    ("trip_a2a", "SmartVoyage.a2a_server.trip_server", 5007, "TRIP_A2A_PORT", "a2a"),
    ("api_server", "SmartVoyage.api_server", 8080, "API_PORT", "api"),
]

_PROCESSES = []


def port_ready(port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def service_port(default_port: int, port_env: str) -> int:
    """允许用环境变量覆盖端口（如 API_PORT=8090 避开已被占用的 8080）。"""
    try:
        return int(os.getenv(port_env, str(default_port)))
    except ValueError:
        return default_port


def wait_ready(name: str, port: int, timeout: int = 40) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_ready(port):
            print(f"  [OK] {name} 已就绪 @ {port}")
            return True
        time.sleep(0.4)
    print(f"  [FAIL] {name} 启动超时，请查看 logs/{name}.log")
    return False


def start(name: str, module: str, port: int, port_env: str, offline: bool):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["HOST"] = "127.0.0.1"
    env[port_env] = str(port)
    env["PORT"] = str(port)
    if offline:
        env["SV_OFFLINE"] = "1"
    log_file = open(LOG_DIR / f"{name}.log", "a", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", module],
        cwd=str(ROOT), env=env, stdout=log_file, stderr=subprocess.STDOUT,
    )
    _PROCESSES.append((name, proc, log_file))
    print(f"  [..] {name} 启动中 (pid={proc.pid}, port={port})")


def shutdown():
    for name, proc, log_file in reversed(_PROCESSES):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        log_file.close()
    print("所有服务已停止")


def main():
    parser = argparse.ArgumentParser(description="一键启动 SmartVoyage 服务")
    parser.add_argument("--offline", action="store_true", help="规则式离线模式（不调用 LLM API）")
    parser.add_argument("--with-api", action="store_true", help="同时启动 Web API 服务")
    parser.add_argument("--group", choices=["all", "mcp", "a2a", "api"], default="all")
    args = parser.parse_args()
    atexit.register(shutdown)

    selected = [s for s in SERVICES if (
        args.group == "all" or s[4] == args.group or
        (s[4] == "api" and args.with_api)
    ) and not (s[4] == "api" and args.group == "all" and not args.with_api)]

    print(f"SmartVoyage 服务启动（模式: {'离线' if args.offline else '在线'}，共 {len(selected)} 个）")
    for name, module, port, port_env, _ in selected:
        port = service_port(port, port_env)
        if port_ready(port):
            print(f"  [SKIP] {name} 端口 {port} 已被占用（假定服务已在运行）")
            continue
        start(name, module, port, port_env, args.offline)
        if not wait_ready(name, port):
            proc = dict((n, p) for n, p, _ in _PROCESSES).get(name)
            if proc and proc.poll() is not None:
                print(f"  进程退出码: {proc.returncode}")
    print("\n服务已就绪。按 Ctrl+C 停止全部服务。")
    try:
        while True:
            time.sleep(1)
            for name, proc, _ in _PROCESSES:
                if proc.poll() is not None:
                    print(f"[WARN] {name} 意外退出，退出码 {proc.returncode}，详见 logs/{name}.log")
    except KeyboardInterrupt:
        print("\n正在停止服务...")


if __name__ == "__main__":
    main()
