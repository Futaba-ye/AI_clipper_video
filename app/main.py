"""
全自动切片机 (Auto Clipper) — FastAPI Web 服务

启动方式：
    python main.py                  # 默认 http://localhost:8000
    python main.py --port 8080      # 指定端口
    python main.py --no-browser     # 不自动打开浏览器

前端页面在启动后自动在浏览器中打开。
"""
from __future__ import annotations

import os
import sys
import argparse
import asyncio
import webbrowser
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from app.api.tasks import router as tasks_router
from app.api.config import router as config_router
from app.api.clips import router as clips_router
from app.utils.log_config import get_logger

logger = get_logger(__name__)

# 加载 .env
load_dotenv()

# 静态文件目录
STATIC_DIR = Path(__file__).resolve().parent / "static"


# ============================================================
# Lifespan — 启动 & 关闭
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时打印地址，结束时清理。"""
    logger.info("=" * 50)
    logger.info("🚀 全自动切片机 Web 服务已启动")
    logger.info("   默认地址: http://localhost:8000")
    logger.info("   API 文档: http://localhost:8000/docs")
    logger.info("=" * 50)
    yield
    logger.info("服务已关闭")


# ============================================================
# FastAPI 应用
# ============================================================

app = FastAPI(
    title="全自动切片机 (Auto Clipper)",
    description="自动从直播回放中识别精彩片段并裁剪",
    version="1.0.0",
    lifespan=lifespan,
)

# 注册 API 路由
app.include_router(tasks_router)
app.include_router(config_router)
app.include_router(clips_router)


# ============================================================
# 前端页面
# ============================================================

@app.get("/")
async def index():
    """主页 — 返回前端 SPA。"""
    return FileResponse(STATIC_DIR / "index.html")


# 静态文件挂载放在最后，避免覆盖 API 路由
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ============================================================
# 入口
# ============================================================

SERVER_PORT = 8000
AUTO_OPEN_BROWSER = True


def main():
    global SERVER_PORT, AUTO_OPEN_BROWSER

    parser = argparse.ArgumentParser(description="全自动切片机 (Auto Clipper) Web 服务")
    parser.add_argument("--port", type=int, default=8000, help="服务端口号（默认 8000）")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="绑定地址（默认 127.0.0.1）")
    args = parser.parse_args()

    SERVER_PORT = args.port
    AUTO_OPEN_BROWSER = not args.no_browser

    # 自动打开浏览器
    if AUTO_OPEN_BROWSER:
        def _open_browser():
            # 等待服务启动后打开
            url = f"http://localhost:{SERVER_PORT}"
            webbrowser.open(url)

        # 延迟 1.5 秒打开（等 uvicorn 启动完成）
        import threading
        threading.Timer(1.5, _open_browser).start()

    # 启动服务
    import uvicorn
    uvicorn.run(
        app,
        host=args.host,
        port=SERVER_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
