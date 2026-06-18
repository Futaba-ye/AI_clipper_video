import re
import os
from app.utils.VTT_time import transform_vtt_time
from app.utils.log_config import get_logger

logger = get_logger(__name__)


# 替换 Windows 文件名中的非法字符为合法替代
def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name)


# 安全打开文件：自动创建目录 + 清洗文件名，检查重名文件，返回安全文件名
def safe_open(file_path: str):
    dir_path = os.path.dirname(file_path)
    safe_name = sanitize_filename(os.path.basename(file_path))

    base, ext = os.path.splitext(safe_name)
    counter = 1
    while os.path.exists(os.path.join(dir_path, safe_name)):
        safe_name = f"{base}_{counter}{ext}"
        counter += 1

    safe_path = os.path.join(dir_path, safe_name)
    if safe_path != file_path:
        logger.warning(f"文件名包含非法字符，已替换为: {safe_path}")
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    return safe_path


# 接收 whisper 生成的时间轴(seconds)列表，生成 VTT 字幕文件
def write_vtt(subtitles, output_path):
    logger.info("开始生成VTT字幕")

    safe_path = safe_open(output_path)

    with open(safe_path, 'w', encoding='utf-8') as f:
        f.write("WEBVTT\n\n")
        for subtitle in subtitles:
            start_str = transform_vtt_time(subtitle['start_time'])
            end_str = transform_vtt_time(subtitle['end_time'])
            text = subtitle['text']

            f.write(f"{start_str} --> {end_str}\n{text}\n\n")

    logger.info(f"字幕已保存至 {safe_path}")


# 接收 [{start_time, end_time, text}, ...]（已格式化的时间戳）生成 VTT 字幕文件
def write_formatted_vtt(subtitles, output_path):
    logger.info("开始生成VTT字幕")

    safe_path = safe_open(output_path)

    skipped = 0
    with open(safe_path, 'w', encoding='utf-8') as f:
        f.write("WEBVTT\n\n")
        for subtitle in subtitles:
            if not isinstance(subtitle, dict):
                skipped += 1
                continue
            start_str = subtitle['start_time']
            end_str = subtitle['end_time']
            text = subtitle['text']

            f.write(f"{start_str} --> {end_str}\n{text}\n\n")

    if skipped:
        logger.warning(f"跳过了 {skipped} 个无效条目（非 dict），原因可能是上游 LLM 返回了空 JSON")
    logger.info(f"字幕已保存至 {safe_path}")


# 接收 [{start_time, end_time, title, summary}, ...]（已格式化的时间戳）生成 VTT 字幕文件
def write_clipper_vtt(subtitles, output_path):
    logger.info("开始生成VTT字幕")

    safe_path = safe_open(output_path)

    with open(safe_path, 'w', encoding='utf-8') as f:
        f.write("WEBVTT\n\n")
        for subtitle in subtitles:
            start_str = subtitle['start_time']
            end_str = subtitle['end_time']
            title = subtitle['title']
            summary = subtitle['summary']

            f.write(f"{start_str} --> {end_str}\n{title}\n{summary}\n\n")

    logger.info(f"字幕已保存至 {safe_path}")