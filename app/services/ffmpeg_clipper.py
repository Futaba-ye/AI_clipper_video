import os
import re
import ffmpeg
from app.utils.log_config import get_logger

logger = get_logger(__name__)


def _sanitize_filename(name: str) -> str:
    """替换 Windows 文件名中的非法字符"""
    return re.sub(r'[<>:"/\\|?*]', '_', name)


def clip_video(file_path, result_summary, output_dir):
    """裁剪精彩片段：每个片段以标题命名，摘要保存为同名 .txt。

    Args:
        file_path:       源视频路径
        result_summary:  detect_highlights 输出 [{start_time, end_time, title, summary}, ...]
        output_dir:      输出根目录（自动创建 clips/ 子目录）
    """
    if not result_summary:
        logger.info("[CLIP] 无精彩片段，跳过剪辑")
        return

    clips_dir = os.path.join(output_dir, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    for i, segment in enumerate(result_summary):
        start = segment['start_time']
        end = segment['end_time']
        title = segment['title']
        summary_text = segment.get('summary', '')

        safe_title = _sanitize_filename(title)
        clip_path = os.path.join(clips_dir, f"{safe_title}.mp4")

        # 裁剪视频片段
        ffmpeg.input(file_path, ss=start, to=end).output(
            clip_path, acodec='copy', vcodec='copy'
        ).run(overwrite_output=True)

        # 保存同名摘要文本
        txt_path = os.path.join(clips_dir, f"{safe_title}.txt")
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(f"标题：{title}\n\n内容概括：{summary_text}")

        logger.info(f"[CLIP] {i+1}/{len(result_summary)}: {title} → {safe_title}.mp4")
