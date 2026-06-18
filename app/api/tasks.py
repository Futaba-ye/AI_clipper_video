"""
任务管理 API

- POST   /api/tasks              创建任务（上传视频 + 启动流水线）
- GET    /api/tasks              获取历史任务列表
- GET    /api/tasks/{id}         获取任务详情
- GET    /api/tasks/{id}/stream  SSE 实时进度流
"""
from __future__ import annotations

import os
import json
import asyncio
import queue
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse
from sse_starlette import EventSourceResponse

from app.models import (
    TaskInfo, TaskStatus, ProgressEvent, ApiResponse,
    STEP_LABELS, STEP_ORDER,
)
from app.task_manager import (
    create_task, get_task, list_tasks,
    run_pipeline, start_pipeline_async,
    get_progress_queue, remove_progress_queue,
    load_config, save_config,
    update_task_status,
    DATA_DIR,
)
from app.utils.log_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", response_model=ApiResponse)
async def create_new_task(
    video: UploadFile = File(...),
    audio_api_key: str = Form(""),
    audio_base_url: str = Form("https://api.deepseek.com"),
    audio_model: str = Form("deepseek-chat"),
    video_api_key: str = Form(""),
    video_base_url: str = Form("https://dashscope.aliyuncs.com/compatible-mode/v1"),
    video_model: str = Form("qwen-vl-plus"),
    summary_api_key: str = Form(""),
    summary_base_url: str = Form("https://api.deepseek.com"),
    summary_model: str = Form("deepseek-chat"),
):
    """上传视频文件并创建切片任务。

    支持 MP4、MKV、AVI、MOV、FLV、WMV 等常见格式。
    上传后自动在后台启动流水线。
    """
    # 验证文件类型
    allowed_ext = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"}
    ext = os.path.splitext(video.filename or "unknown.mp4")[1].lower()
    if ext not in allowed_ext:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式 {ext}。支持的格式: {', '.join(allowed_ext)}"
        )

    # 如果 API key 为空，尝试从已保存配置加载
    saved_config = load_config()

    task_config = {
        "audio_api_key": audio_api_key or saved_config.get("audio_api_key", ""),
        "audio_base_url": audio_base_url or saved_config.get("audio_base_url", "https://api.deepseek.com"),
        "audio_model": audio_model or saved_config.get("audio_model", "deepseek-chat"),
        "video_api_key": video_api_key or saved_config.get("video_api_key", ""),
        "video_base_url": video_base_url or saved_config.get("video_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "video_model": video_model or saved_config.get("video_model", "qwen-vl-plus"),
        "summary_api_key": summary_api_key or saved_config.get("summary_api_key") or audio_api_key or saved_config.get("audio_api_key", ""),
        "summary_base_url": summary_base_url or saved_config.get("summary_base_url") or saved_config.get("audio_base_url", "https://api.deepseek.com"),
        "summary_model": summary_model or saved_config.get("summary_model") or saved_config.get("audio_model", "deepseek-chat"),
    }

    # 保存视频到任务目录
    task_id_prefix = __generate_task_id()
    task_dir = DATA_DIR / "tasks" / task_id_prefix
    task_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = __sanitize_filename(video.filename or "video.mp4")
    video_path = task_dir / safe_filename

    try:
        with open(video_path, "wb") as f:
            # 分块写入，避免大文件撑爆内存
            while chunk := await video.read(8 * 1024 * 1024):  # 8MB 块
                f.write(chunk)
    except Exception as e:
        shutil.rmtree(task_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"文件保存失败: {e}")

    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)

    # 创建数据库记录（使用与目录名一致的 task_id）
    output_dir = str(task_dir)
    task_info = create_task(safe_filename, str(video_path), task_config,
                            task_id=task_id_prefix)

    # 启动后台流水线
    start_pipeline_async(task_info.id, str(video_path), output_dir, task_config)

    logger.info(f"[API] 任务 {task_info.id} 已创建，视频 {file_size_mb:.1f}MB")

    return ApiResponse(
        success=True,
        message=f"任务已创建，视频大小 {file_size_mb:.1f}MB",
        data={"task_id": task_info.id},
    )


@router.get("", response_model=ApiResponse)
async def list_all_tasks(limit: int = 50):
    """获取最近的任务列表。"""
    tasks = list_tasks(limit=limit)
    return ApiResponse(
        success=True,
        data={"tasks": [t.model_dump() for t in tasks]},
    )


@router.get("/{task_id}", response_model=ApiResponse)
async def get_task_detail(task_id: str):
    """获取单个任务的详情（含切片列表）。"""
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse(success=True, data={"task": task.model_dump()})


@router.post("/{task_id}/retry", response_model=ApiResponse)
async def retry_task(task_id: str):
    """从失败步骤重试任务。

    自动找到第一个未完成的步骤，验证中间文件存在，
    然后从该步骤重新启动流水线。
    """
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status != TaskStatus.FAILED:
        raise HTTPException(status_code=400, detail="只能重试失败的任务")

    # 找到第一个非 completed 的步骤
    failed_step = None
    for step in STEP_ORDER:
        status = task.step_statuses.get(step, "pending")
        if status != "completed":
            failed_step = step
            break

    if failed_step is None:
        raise HTTPException(status_code=400, detail="所有步骤已完成，无需重试")

    # 验证已完成步骤的中间文件仍存在
    task_dir_path = DATA_DIR / "tasks" / task_id
    required_files = {
        "extract_audio":   task_dir_path / "extracted_audio.wav",
        "extract_video":   task_dir_path / "extracted_video.mp4",
        "asr":             task_dir_path / "subtitles.vtt",
        "audio_summary":   task_dir_path / "audio_summary.vtt",
        "scene_detect":    task_dir_path / "scenes.vtt",
        "video_summary":   task_dir_path / "video_summary.vtt",
        "fusion":          task_dir_path / "result_summary.vtt",
    }

    from_step_idx = STEP_ORDER.index(failed_step)
    for i in range(from_step_idx):
        step_key = STEP_ORDER[i]
        file_path = required_files.get(step_key)
        if file_path and not (file_path.exists() and file_path.stat().st_size > 0):
            raise HTTPException(
                status_code=409,
                detail=f"中间文件缺失: {file_path.name}，无法从 "
                       f"{STEP_LABELS.get(failed_step, failed_step)} 重试"
            )

    # 验证原始视频文件仍存在
    if not Path(task.video_path).exists():
        raise HTTPException(
            status_code=409,
            detail=f"原始视频文件不存在: {task.video_path}"
        )

    if not task_dir_path.exists():
        raise HTTPException(status_code=409, detail="任务目录不存在")

    # 加载配置
    config = load_config()

    # 重置失败步骤状态 + 清除错误
    update_task_status(task_id, status=TaskStatus.RUNNING,
                       error_message=None, progress=0)
    update_task_status(task_id, step_status=(failed_step, "pending"))

    # 从失败步骤重新启动
    output_dir_str = str(task_dir_path)
    start_pipeline_async(task_id, task.video_path, output_dir_str, config,
                         from_step=failed_step)

    logger.info(f"[API] 任务 {task_id} 从步骤 '{failed_step}' 重试")

    return ApiResponse(
        success=True,
        message=f"任务将从 {STEP_LABELS.get(failed_step, failed_step)} 重新开始",
        data={"task_id": task_id, "from_step": failed_step},
    )


@router.post("/{task_id}/mark-failed", response_model=ApiResponse)
async def mark_task_failed(task_id: str):
    """将卡住的 RUNNING/PENDING 任务标记为 FAILED，使其可重试。

    用于处理服务器重启后遗留的僵尸任务。
    """
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status not in (TaskStatus.RUNNING, TaskStatus.PENDING):
        raise HTTPException(status_code=400,
                            detail=f"只能标记运行中或等待中的任务，当前状态: {task.status.value}")

    update_task_status(task_id, status=TaskStatus.FAILED,
                       error_message="用户手动标记为失败（任务可能中断）")
    # 将当前 running 的步骤也标为 failed
    for step in STEP_ORDER:
        if task.step_statuses.get(step) == "running":
            update_task_status(task_id, step_status=(step, "failed"))
            break

    logger.info(f"[API] 任务 {task_id} 被手动标记为失败")

    return ApiResponse(
        success=True,
        message="任务已标记为失败，可在片段库中重试",
        data={"task_id": task_id},
    )


@router.get("/{task_id}/stream")
async def stream_progress(task_id: str, request: Request):
    """SSE 实时进度流。

    无论任务状态如何，先回放当前 step_statuses，
    确保重新连接时前端立即看到正确的进度状态。
    然后再监听新事件（RUNNING/PENDING）或立即结束（COMPLETED/FAILED）。
    """
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 先回放当前状态（所有状态都适用）
    replay_type = "complete" if task.status == TaskStatus.COMPLETED else \
                  "error" if task.status == TaskStatus.FAILED else "progress"
    replay_event = ProgressEvent(
        type=replay_type,
        message=f"任务状态: {task.status.value}",
        progress=task.progress,
        step_statuses=task.step_statuses,
        step=task.current_step,
    )

    # 已结束的任务：回放 + done，立即关闭
    if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
        async def replay_and_done():
            yield {"event": "progress", "data": replay_event.model_dump_json()}
            yield {"event": "done", "data": "{}"}
        return EventSourceResponse(replay_and_done())

    # 运行中 / 等待中的任务：先回放当前状态，再监听新事件
    q = get_progress_queue(task_id)

    async def stream():
        # ① 立即发送当前状态回放
        yield {"event": "progress", "data": replay_event.model_dump_json()}

        # ② 监听新事件
        while True:
            if await request.is_disconnected():
                break

            try:
                event: ProgressEvent = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: q.get(timeout=15.0)
                )
                if event.type == "done":
                    yield {"event": "done", "data": "{}"}
                    break
                yield {"event": "progress", "data": event.model_dump_json()}
            except queue.Empty:
                yield {"event": "ping", "data": "{}"}

    return EventSourceResponse(stream())


def __generate_task_id() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]


def __sanitize_filename(name: str) -> str:
    import re
    return re.sub(r'[<>:"/\\|?*]', '_', name)
