"""SmartVoyage Web API（FastAPI）：REST + SSE 流式对话 + 静态前端。

启动：python -m SmartVoyage.api_server   或   python scripts/start_all.py --with-api
"""
import asyncio
import json
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from SmartVoyage.chat_service import ChatService
from SmartVoyage.create_logger import logger

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

app = FastAPI(title="SmartVoyage API", description="基于 A2A + MCP 的旅行智能助手", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

chat_service = ChatService()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class ProfileRequest(BaseModel):
    profile: dict


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def sse_generator(message: str):
    """把完整回复切成小块推送，前端逐字显示。"""
    yield _sse({"type": "start"})
    try:
        reply = await chat_service.chat(message)
        for index in range(0, len(reply), 20):
            yield _sse({"type": "delta", "content": reply[index:index + 20]})
            await asyncio.sleep(0.015)
        yield _sse({"type": "done", "content": reply, "agents": chat_service.last_agents})
    except Exception as exc:
        logger.error(f"SSE 对话失败: {exc}")
        yield _sse({"type": "error", "content": f"处理失败：{exc}"})


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "SmartVoyage API"}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    response = await chat_service.chat(request.message)
    return {"status": "success", "message": response, "agents": chat_service.last_agents}


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    return StreamingResponse(
        sse_generator(request.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/memory")
async def get_memory():
    return {"status": "success", "data": chat_service.get_memory_state()}


@app.post("/api/memory/profile")
async def update_profile(request: ProfileRequest):
    chat_service.update_user_profile(request.profile)
    return {"status": "success", "message": "用户偏好已更新", "data": chat_service.get_memory_state()["user_profile"]}


@app.post("/api/memory/clear")
async def clear_memory():
    chat_service.clear_memory()
    return {"status": "success", "message": "记忆已清空"}


@app.get("/api/agents")
async def get_agents():
    return {"status": "success", "data": chat_service.get_agent_cards()}


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", os.getenv("PORT", "8080")))
    logger.info(f"SmartVoyage API 启动于 http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
