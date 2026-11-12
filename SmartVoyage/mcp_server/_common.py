"""MCP 服务公共配置。"""
import os


def server_options(default_port: int, port_env: str) -> dict:
    """绑定地址与端口：支持 Docker 环境变量，本地开发默认回环地址。"""
    port = int(os.getenv(port_env, os.getenv("PORT", str(default_port))))
    return {"host": os.getenv("HOST", "127.0.0.1"), "port": port}
