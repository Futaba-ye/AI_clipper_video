"""
全自动切片机 — 任务管理器

负责：
  - SQLite 数据库存储（任务 & 切片）
  - 后台线程执行流水线
  - 进度事件队列管理（供 SSE 消费）
"""
from __future__ import annotations

import os
import sys
import json
import time
import queue
import uuid
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from app.models import (
    TaskStatus, TaskInfo, ClipInfo, ProgressEvent,
    STEP_LABELS, STEP_ORDER,
)
from app.utils.log_config import get_logger

logger = get_logger(__name__)

# ============================================================
# 路径常量
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent  # auto_clipper_backend/
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "tasks.db"
CONFIG_PATH = DATA_DIR / "config.json"


# ============================================================
# 数据库初始化
# ============================================================

def _get_db() -> sqlite3.Connection:
    """获取数据库连接（自动创建目录和表）。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id              TEXT PRIMARY KEY,
            video_filename  TEXT NOT NULL,
            video_path      TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending',
            progress        REAL NOT NULL DEFAULT 0.0,
            current_step    TEXT DEFAULT '',
            step_statuses   TEXT DEFAULT '{}',
            created_at      TEXT NOT NULL,
            finished_at     TEXT,
            error_message   TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clips (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id         TEXT NOT NULL,
            title           TEXT NOT NULL,
            summary         TEXT DEFAULT '',
            start_time      TEXT NOT NULL,
            end_time        TEXT NOT NULL,
            video_filename  TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
    """)
    conn.commit()
    return conn


db = _get_db()


# ============================================================
# 进度事件队列
# ============================================================

# 每个运行中的任务一个队列，{task_id: queue.Queue}
_progress_queues: dict[str, queue.Queue] = {}
_queues_lock = threading.Lock()


def get_progress_queue(task_id: str) -> queue.Queue:
    """获取或创建任务的进度队列。"""
    with _queues_lock:
        if task_id not in _progress_queues:
            _progress_queues[task_id] = queue.Queue()
        return _progress_queues[task_id]


def remove_progress_queue(task_id: str):
    """任务结束后清理队列。"""
    with _queues_lock:
        _progress_queues.pop(task_id, None)


def _emit_progress(task_id: str, event: ProgressEvent):
    """推送进度事件到队列（线程安全）。"""
    try:
        q = get_progress_queue(task_id)
        q.put(event)
    except Exception:
        pass


# ============================================================
# 配置管理
# ============================================================

DEFAULT_CONFIG = {
    "audio_api_key": "",
    "audio_base_url": "https://api.deepseek.com",
    "audio_model": "deepseek-chat",
    "video_api_key": "",
    "video_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "video_model": "qwen-vl-plus",
    "summary_api_key": "",
    "summary_base_url": "https://api.deepseek.com",
    "summary_model": "deepseek-chat",
    "default_output_dir": "",
}


def load_config() -> dict:
    """加载用户配置（不存在则创建默认）。"""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # 合并默认值（兼容新增字段）
            cfg = {**DEFAULT_CONFIG, **saved}
            return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(config: dict) -> dict:
    """保存用户配置。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg = {**DEFAULT_CONFIG, **config}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg


# ============================================================
# 任务 CRUD
# ============================================================

def create_task(video_filename: str, video_path: str, config: dict,
                task_id: str = "") -> TaskInfo:
    """在数据库中创建新任务并返回 TaskInfo。

    Args:
        task_id: 可选，不传则自动生成。外部调用时应传入与目录名一致的 ID。
    """
    if not task_id:
        task_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    step_statuses = {s: "pending" for s in STEP_ORDER}

    db.execute(
        """INSERT INTO tasks (id, video_filename, video_path, status, progress,
           current_step, step_statuses, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (task_id, video_filename, video_path, TaskStatus.PENDING.value,
         0.0, "", json.dumps(step_statuses), now)
    )
    db.commit()

    return _row_to_task_info(dict(db.execute(
        "SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    ))


def get_task(task_id: str) -> Optional[TaskInfo]:
    """获取单个任务详情（含切片列表）。"""
    row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        return None
    return _row_to_task_info(dict(row))


def list_tasks(limit: int = 50) -> list[TaskInfo]:
    """获取最近的任务列表。"""
    rows = db.execute(
        "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_task_info(dict(r)) for r in rows]


def update_task_status(
    task_id: str,
    status: Optional[TaskStatus] = None,
    progress: Optional[float] = None,
    current_step: Optional[str] = None,
    step_status: Optional[tuple[str, str]] = None,
    error_message: Optional[str] = None,
):
    """更新任务字段。"""
    row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        return

    updates = []
    params = []

    if status is not None:
        updates.append("status=?")
        params.append(status.value)
    if progress is not None:
        updates.append("progress=?")
        params.append(progress)
    if current_step is not None:
        updates.append("current_step=?")
        params.append(current_step)
    if error_message is not None:
        updates.append("error_message=?")
        params.append(error_message)

    if step_status is not None:
        step_name, step_val = step_status
        current_statuses = json.loads(row["step_statuses"] or "{}")
        current_statuses[step_name] = step_val
        updates.append("step_statuses=?")
        params.append(json.dumps(current_statuses))

    if status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
        updates.append("finished_at=?")
        params.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    if updates:
        params.append(task_id)
        db.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id=?", params)
        db.commit()


def add_clips(task_id: str, clips_data: list[dict]):
    """批量添加切片记录。"""
    for c in clips_data:
        db.execute(
            """INSERT INTO clips (task_id, title, summary, start_time, end_time, video_filename)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task_id, c["title"], c.get("summary", ""),
             c["start_time"], c["end_time"], c.get("video_filename", ""))
        )
    db.commit()


def get_clips(task_id: str) -> list[ClipInfo]:
    """获取任务的所有切片。"""
    rows = db.execute(
        "SELECT * FROM clips WHERE task_id=? ORDER BY id", (task_id,)
    ).fetchall()
    return [ClipInfo(
        id=r["id"], task_id=r["task_id"], title=r["title"],
        summary=r["summary"], start_time=r["start_time"],
        end_time=r["end_time"], video_filename=r["video_filename"]
    ) for r in rows]


def _row_to_task_info(row: dict) -> TaskInfo:
    clips = get_clips(row["id"]) if row["status"] == TaskStatus.COMPLETED.value else []
    return TaskInfo(
        id=row["id"],
        video_filename=row["video_filename"],
        video_path=row.get("video_path", ""),
        status=TaskStatus(row["status"]),
        progress=row["progress"],
        current_step=row.get("current_step", ""),
        step_statuses=json.loads(row.get("step_statuses", "{}")),
        created_at=row["created_at"],
        finished_at=row.get("finished_at"),
        error_message=row.get("error_message"),
        clip_count=len(clips),
        clips=clips,
    )


# ============================================================
# 流水线执行器
# ============================================================

def run_pipeline(
    task_id: str,
    video_path: str,
    output_dir: str,
    config: dict,
    from_step: str = "",
):
    """在后台线程中执行全自动切片流水线。

    进度事件通过 _emit_progress 推送到队列，供 SSE 消费。

    Args:
        from_step: 可选，从指定步骤开始执行（断点续跑）。空字符串表示从头开始。
    """
    from app.services import ffmpeg_core, whisper_core, ffmpeg_clipper
    from app.agent.Audio import audio_agent
    from app.agent.Video import scene_detect, video_agent
    from app.utils import VTT_writer, VTT_parser
    from app.agent import summary_result

    def _emit(step: str, status: str, message: str = "", progress: float = 0.0):
        """快捷推送进度。"""
        label = STEP_LABELS.get(step, step)
        _emit_progress(task_id, ProgressEvent(
            type="step_done" if status == "completed" else
                 "step_start" if status == "running" else "error",
            step=step, step_label=label, status=status,
            message=message, progress=progress,
        ))
        # 同步更新数据库
        if status in ("running", "completed", "failed"):
            update_task_status(task_id, step_status=(step, status))

    def _exists(path):
        return path and os.path.exists(path) and os.path.getsize(path) > 0

    try:
        update_task_status(task_id, status=TaskStatus.RUNNING)
        total_steps = 8.0
        current_step_name = ""  # 供异常处理器标记失败步骤

        # 确定起始步骤序号
        from_idx = 0
        if from_step and from_step in STEP_ORDER:
            from_idx = STEP_ORDER.index(from_step)

        # 输出路径
        os.makedirs(output_dir, exist_ok=True)
        output_audio_path = os.path.join(output_dir, "extracted_audio.wav")
        output_video_path = os.path.join(output_dir, "extracted_video.mp4")
        output_subtitles_path = os.path.join(output_dir, "subtitles.vtt")
        output_audio_summary_path = os.path.join(output_dir, "audio_summary.vtt")
        output_scenes_path = os.path.join(output_dir, "scenes.vtt")
        output_video_summary_path = os.path.join(output_dir, "video_summary.vtt")
        output_result_vtt_path = os.path.join(output_dir, "result_summary.vtt")

        api_keys = {
            "audio_key": config.get("audio_api_key", ""),
            "audio_url": config.get("audio_base_url", "https://api.deepseek.com"),
            "audio_model": config.get("audio_model", "deepseek-chat"),
            "video_key": config.get("video_api_key", ""),
            "video_url": config.get("video_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            "video_model": config.get("video_model", "qwen-vl-plus"),
            "summary_key": config.get("summary_api_key") or config.get("audio_api_key", ""),
            "summary_url": config.get("summary_base_url") or config.get("audio_base_url", "https://api.deepseek.com"),
            "summary_model": config.get("summary_model") or config.get("audio_model", "deepseek-chat"),
        }

        # ============================================================
        # 断点恢复：从 VTT 文件重新加载已跳过步骤的内存数据
        # ============================================================
        audio_result = None
        video_result = None
        sc = None
        subs = None
        result_summary = None

        if from_idx > 0:
            # 重放已完成步骤的进度事件，让 SSE 客户端看到它们已完成
            for i in range(from_idx):
                step_key = STEP_ORDER[i]
                _emit(step_key, "completed", "", (i + 1) / total_steps * 100)
            update_task_status(task_id, progress=from_idx / total_steps * 100)

            # 按需从 VTT 文件加载内存数据
            if from_idx > 2:  # 从步骤 4 起需要 subs
                if _exists(output_subtitles_path):
                    subs = VTT_parser.parse_vtt_to_subtitles(output_subtitles_path)
                    logger.info(f"[Resume] 从 subtitles.vtt 加载 {len(subs)} 条字幕")

            if from_idx > 3:  # 从步骤 5 起需要 audio_result
                if _exists(output_audio_summary_path):
                    audio_result = VTT_parser.parse_vtt_to_raw_subtitles(output_audio_summary_path)
                    logger.info(f"[Resume] 从 audio_summary.vtt 加载 {len(audio_result)} 条")

            if from_idx > 4:  # 从步骤 6 起需要 scenes
                if _exists(output_scenes_path):
                    raw_scenes = VTT_parser.parse_vtt_to_subtitles(output_scenes_path)
                    sc = [{"start_time": s["start_time"], "end_time": s["end_time"]}
                          for s in raw_scenes]
                    logger.info(f"[Resume] 从 scenes.vtt 加载 {len(sc)} 个场景")

            if from_idx > 5:  # 从步骤 7 起需要 video_result
                if _exists(output_video_summary_path):
                    video_result = VTT_parser.parse_vtt_to_raw_subtitles(output_video_summary_path)
                    logger.info(f"[Resume] 从 video_summary.vtt 加载 {len(video_result)} 条")

            if from_idx > 6:  # 从步骤 8 起需要 result_summary
                if _exists(output_result_vtt_path):
                    result_summary = VTT_parser.parse_clipper_vtt(output_result_vtt_path)
                    logger.info(f"[Resume] 从 result_summary.vtt 加载 {len(result_summary)} 条")

        # ================================================================
        # Step 1: 提取音频 (0/8 → 1/8)
        # ================================================================
        current_step_name = "extract_audio"
        if from_idx <= 0:
            _emit("extract_audio", "running", "正在从视频中提取音频……", 0)
            ffmpeg_core.extract_audio(video_path, output_audio_path)
            _emit("extract_audio", "completed", "音频提取完成", 100 / total_steps)
            update_task_status(task_id, progress=1 / total_steps * 100)

        # ================================================================
        # Step 2: 提取视频 (1/8 → 2/8)
        # ================================================================
        current_step_name = "extract_video"
        if from_idx <= 1:
            _emit("extract_video", "running", "正在提取纯视频流……", 1 / total_steps * 100)
            ffmpeg_core.extract_video(video_path, output_video_path)
            _emit("extract_video", "completed", "视频提取完成", 2 / total_steps * 100)
            update_task_status(task_id, progress=2 / total_steps * 100)

        # ================================================================
        # Step 3: ASR (2/8 → 3/8)
        # ================================================================
        current_step_name = "asr"
        if from_idx <= 2:
            _emit("asr", "running", "正在进行语音识别（可能需要数分钟）……", 2 / total_steps * 100)
            subs = whisper_core.transcribe_audio(output_audio_path)
            VTT_writer.write_vtt(subtitles=subs, output_path=output_subtitles_path)
            _emit("asr", "completed", f"语音识别完成，共 {len(subs)} 条字幕", 3 / total_steps * 100)
            update_task_status(task_id, progress=3 / total_steps * 100)

        # ================================================================
        # Step 4: 音频总结 (3/8 → 4/8)
        # ================================================================
        current_step_name = "audio_summary"
        if from_idx <= 3:
            _emit("audio_summary", "running", "正在用 LLM 分析音频内容（可能需要数分钟）……", 3 / total_steps * 100)
            audio_result = audio_agent.generate_audio_summary(
                subs, api_keys["audio_key"], api_keys["audio_url"], api_keys["audio_model"]
            )
            VTT_writer.write_formatted_vtt(audio_result, output_audio_summary_path)
            _emit("audio_summary", "completed", f"音频总结完成，共 {len(audio_result)} 条", 4 / total_steps * 100)
            update_task_status(task_id, progress=4 / total_steps * 100)

        # ================================================================
        # Step 5: 场景检测 (4/8 → 5/8)
        # ================================================================
        current_step_name = "scene_detect"
        if from_idx <= 4:
            _emit("scene_detect", "running", "正在检测视频场景切换……", 4 / total_steps * 100)
            sc = scene_detect.detect_scenes(output_video_path)
            VTT_writer.write_formatted_vtt(
                VTT_parser.scenes_to_vtt(sc), output_scenes_path
            )
            _emit("scene_detect", "completed", f"场景检测完成，共 {len(sc)} 个场景", 5 / total_steps * 100)
            update_task_status(task_id, progress=5 / total_steps * 100)

        # ================================================================
        # Step 6: 画面总结 (5/8 → 6/8)
        # ================================================================
        current_step_name = "video_summary"
        if from_idx <= 5:
            _emit("video_summary", "running", "正在用 VLM 分析画面内容（可能需要数分钟）……", 5 / total_steps * 100)
            video_result = video_agent.generate_scene_summaries(
                sc, output_video_path, api_keys["video_key"],
                api_keys["video_url"], api_keys["video_model"]
            )
            VTT_writer.write_formatted_vtt(video_result, output_video_summary_path)
            _emit("video_summary", "completed", f"画面总结完成，共 {len(video_result)} 条", 6 / total_steps * 100)
            update_task_status(task_id, progress=6 / total_steps * 100)

        # ================================================================
        # Step 7: 融合 (6/8 → 7/8)
        # ================================================================
        current_step_name = "fusion"
        if from_idx <= 6:
            _emit("fusion", "running", "正在进行双通道融合分析……", 6 / total_steps * 100)
            result_summary = summary_result.detect_highlights(
                api_keys["summary_key"], api_keys["summary_url"], api_keys["summary_model"],
                audio_result, video_result
            )
            VTT_writer.write_clipper_vtt(result_summary, output_result_vtt_path)
            _emit("fusion", "completed", f"融合完成，检测到 {len(result_summary)} 个高光片段", 7 / total_steps * 100)
            update_task_status(task_id, progress=7 / total_steps * 100)

        # ================================================================
        # Step 8: 裁剪 (7/8 → 8/8)
        # ================================================================
        current_step_name = "clip"
        if from_idx <= 7:
            _emit("clip", "running", f"正在裁剪 {len(result_summary) if result_summary else 0} 个视频片段……", 7 / total_steps * 100)
            if result_summary:
                ffmpeg_clipper.clip_video(video_path, result_summary, output_dir)
                # 记录切片到数据库
                for s in result_summary:
                    safe_title = __sanitize_filename(s["title"])
                    s["video_filename"] = f"{safe_title}.mp4"
                add_clips(task_id, result_summary)
            _emit("clip", "completed", f"裁剪完成，共 {len(result_summary) if result_summary else 0} 个片段", 8 / total_steps * 100)
            update_task_status(task_id, progress=100)

        # 完成
        clip_count = len(result_summary) if result_summary else 0
        _emit_progress(task_id, ProgressEvent(
            type="complete",
            message=f"全部完成！共生成 {clip_count} 个精彩片段",
            progress=100,
        ))
        update_task_status(task_id, status=TaskStatus.COMPLETED, progress=100)

        logger.info(f"[Task {task_id}] 流水线完成，{clip_count} 个片段")

    except Exception as e:
        logger.error(f"[Task {task_id}] 流水线失败: {e}", exc_info=True)
        # 标记当前步骤为 failed（重试端点的定位依据）
        if current_step_name:
            update_task_status(task_id, step_status=(current_step_name, "failed"))
            _emit(current_step_name, "failed", f"步骤执行失败: {e}", 0)
        update_task_status(task_id, status=TaskStatus.FAILED, error_message=str(e))
        _emit_progress(task_id, ProgressEvent(
            type="error",
            message=f"执行失败: {e}",
            progress=0,
        ))
    finally:
        # 发送结束信号
        _emit_progress(task_id, ProgressEvent(type="done"))
        # 延迟清理队列（给 SSE 客户端时间断开）
        threading.Timer(30.0, remove_progress_queue, args=[task_id]).start()


def __sanitize_filename(name: str) -> str:
    """替换 Windows 文件名非法字符。"""
    import re
    return re.sub(r'[<>:"/\\|?*]', '_', name)


def start_pipeline_async(task_id: str, video_path: str, output_dir: str, config: dict,
                         from_step: str = ""):
    """在后台线程启动流水线。可指定 from_step 从中途步骤恢复。"""
    thread = threading.Thread(
        target=run_pipeline,
        args=(task_id, video_path, output_dir, config, from_step),
        daemon=True,
        name=f"pipeline-{task_id}",
    )
    thread.start()
    return thread
