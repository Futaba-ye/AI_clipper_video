"""
配置管理 API

- GET  /api/config       获取用户配置
- PUT  /api/config       保存用户配置
"""
from __future__ import annotations

from fastapi import APIRouter

from app.models import ConfigSave, ApiResponse
from app.task_manager import load_config, save_config
from app.utils.log_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=ApiResponse)
async def get_config():
    """获取当前用户配置（API Key 会部分脱敏）。"""
    cfg = load_config()
    # 脱敏处理
    safe = dict(cfg)
    for key in ["audio_api_key", "video_api_key", "summary_api_key"]:
        val = safe.get(key, "")
        if val and len(val) > 8:
            safe[key] = val[:4] + "****" + val[-4:]
        elif val:
            safe[key] = "****"
    return ApiResponse(success=True, data={"config": safe})


@router.put("", response_model=ApiResponse)
async def update_config(body: ConfigSave):
    """保存用户配置。"""
    cfg = save_config(body.model_dump())
    logger.info("[API] 用户配置已更新")
    return ApiResponse(success=True, message="配置已保存", data={"config": cfg})
