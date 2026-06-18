"""
全自动切片机 — 数据模型

使用 Pydantic 定义 API 请求/响应模型。
"""
from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ============================================================
# 任务状态
# ============================================================

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStep(str, Enum):
    EXTRACT_AUDIO = "extract_audio"
    EXTRACT_VIDEO = "extract_video"
    ASR = "asr"
    AUDIO_SUMMARY = "audio_summary"
    SCENE_DETECT = "scene_detect"
    VIDEO_SUMMARY = "video_summary"
    FUSION = "fusion"
    CLIP = "clip"


STEP_LABELS: dict[str, str] = {
    "extract_audio": "提取音频",
    "extract_video": "提取视频",
    "asr": "语音识别 (ASR)",
    "audio_summary": "音频内容总结",
    "scene_detect": "场景检测",
    "video_summary": "画面内容总结",
    "fusion": "双通道融合",
    "clip": "裁剪视频片段",
}

STEP_ORDER: list[str] = [
    "extract_audio",
    "extract_video",
    "asr",
    "audio_summary",
    "scene_detect",
    "video_summary",
    "fusion",
    "clip",
]


# ============================================================
# API 请求模型
# ============================================================

class TaskConfig(BaseModel):
    """创建任务时的配置参数"""
    # 音频通道
    audio_api_key: str = ""
    audio_base_url: str = "https://api.deepseek.com"
    audio_model: str = "deepseek-chat"

    # 视频通道
    video_api_key: str = ""
    video_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    video_model: str = "qwen-vl-plus"

    # 融合通道（默认复用音频通道）
    summary_api_key: str = ""
    summary_base_url: str = "https://api.deepseek.com"
    summary_model: str = "deepseek-chat"

    # 输出目录（可选，默认自动生成）
    output_dir: str = ""


class ConfigSave(BaseModel):
    """保存用户配置"""
    audio_api_key: str = ""
    audio_base_url: str = "https://api.deepseek.com"
    audio_model: str = "deepseek-chat"
    video_api_key: str = ""
    video_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    video_model: str = "qwen-vl-plus"
    summary_api_key: str = ""
    summary_base_url: str = "https://api.deepseek.com"
    summary_model: str = "deepseek-chat"
    default_output_dir: str = ""


# ============================================================
# API 响应模型
# ============================================================

class ClipInfo(BaseModel):
    id: int
    task_id: str
    title: str
    summary: str
    start_time: str
    end_time: str
    video_filename: str


class TaskInfo(BaseModel):
    id: str
    video_filename: str
    video_path: str = ""
    status: TaskStatus
    progress: float = 0.0
    current_step: str = ""
    step_statuses: dict[str, str] = Field(default_factory=dict)
    created_at: str = ""
    finished_at: Optional[str] = None
    error_message: Optional[str] = None
    clip_count: int = 0
    clips: list[ClipInfo] = Field(default_factory=list)


class ProgressEvent(BaseModel):
    """SSE 进度事件"""
    type: str = "progress"  # "progress" | "step_start" | "step_done" | "error" | "complete" | "ping"
    step: str = ""
    step_label: str = ""
    status: str = ""  # "running" | "completed" | "failed"
    message: str = ""
    progress: float = 0.0
    step_statuses: dict[str, str] = Field(default_factory=dict)


class ApiResponse(BaseModel):
    success: bool
    message: str = ""
    data: Optional[dict | list] = None
