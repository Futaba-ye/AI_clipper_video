"""
切片管理 API

- GET  /api/clips/{task_id}              获取任务的所有切片
- GET  /api/clips/{task_id}/{filename}   播放/下载切片视频
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.models import ApiResponse
from app.task_manager import get_task, get_clips, DATA_DIR
from app.utils.log_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/clips", tags=["clips"])


@router.get("/{task_id}", response_model=ApiResponse)
async def list_clips(task_id: str):
    """获取某个任务的所有切片列表。"""
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    clips = get_clips(task_id)
    return ApiResponse(
        success=True,
        data={"task_id": task_id, "clips": [c.model_dump() for c in clips]},
    )


@router.get("/{task_id}/{filename:path}")
async def serve_clip(task_id: str, filename: str):
    """提供切片视频文件或文本文件的访问。

    支持：
      - 视频文件 (.mp4) → 流式播放
      - 文本文件 (.txt)  → 内联显示
    """
    # 安全检查：防止路径穿越
    filename = os.path.basename(filename)
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)

    task_dir = DATA_DIR / "tasks" / task_id
    clips_dir = task_dir / "clips"

    if not clips_dir.exists():
        raise HTTPException(status_code=404, detail="该任务无切片目录")

    clip_path = clips_dir / safe_name
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {safe_name}")

    # 确定 MIME 类型
    ext = os.path.splitext(safe_name)[1].lower()
    media_type_map = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".txt": "text/plain; charset=utf-8",
    }
    media_type = media_type_map.get(ext, "application/octet-stream")

    # 视频文件：不设 filename，让浏览器根据 Content-Type 内联播放
    # 文本文件：设 filename 让浏览器直接显示
    if ext == ".txt":
        return FileResponse(
            path=str(clip_path),
            media_type=media_type,
            filename=safe_name,
        )
    else:
        return FileResponse(
            path=str(clip_path),
            media_type=media_type,
        )
