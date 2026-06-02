import re
import os


# 替换 Windows 文件名中的非法字符为合法替代
def sanitize_filename(name: str) -> str:
    # Windows 禁止: < > : " / \ | ? *
    return re.sub(r'[<>:"/\\|?*]', '_', name)


# 安全打开文件：自动创建目录 + 清洗文件名，检查重名文件，返回安全文件名
def safe_open(file_path: str):
    # 清洗文件名 + 确保目录存在
    dir_path = os.path.dirname(file_path)
    safe_name = sanitize_filename(os.path.basename(file_path))

    # 检查重名文件
    base, ext = os.path.splitext(safe_name)
    counter = 1
    while os.path.exists(os.path.join(dir_path, safe_name)):
        safe_name = f"{base}_{counter}{ext}"
        counter += 1

    safe_path = os.path.join(dir_path, safe_name)
    if safe_path != file_path:
        print(f"[WARN] 文件名包含非法字符，已替换为: {safe_path}")
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    return safe_path


# 接收whisper生成的时间轴(seconds)列表，生成VTT字幕文件
def write_vtt(subtitles, output_path):
    print("开始生成VTT字幕")

    # 将时间转化为VTT标准时间戳
    def helper(time):
        h = int(time // 3600)
        mins = int((time % 3600) // 60)
        s = int(time % 60)
        ms = int((time - h * 3600 - mins * 60 - s) * 1000)
        return f"{h:02d}:{mins:02d}:{s:02d}.{ms:03d}"

    safe_path = safe_open(output_path)

    with open(safe_path, 'w', encoding='utf-8') as f:
        f.write("WEBVTT\n\n")
        for subtitle in subtitles:
            start_str = helper(subtitle['start_time'])
            end_str = helper(subtitle['end_time'])
            text = subtitle['text']

            f.write(f"{start_str} --> {end_str}\n{text}\n\n")

    print(f"[导出] 字幕已保存至 {safe_path}")


# 接收 [{start_time, end_time, text}, ...]vtt 格式的Json列表，生成VTT字幕文件
def output_vtt(subtitles, output_path):
    print("开始生成VTT字幕")

    safe_path = safe_open(output_path)

    with open(safe_path, 'w', encoding='utf-8') as f:
        f.write("WEBVTT\n\n")
        for subtitle in subtitles:
            start_str = subtitle['start_time']
            end_str = subtitle['end_time']
            text = subtitle['text']

            f.write(f"{start_str} --> {end_str}\n{text}\n\n")

    print(f"[导出] 字幕已保存至 {safe_path}")


# 将 [{start_time, end_time, text}, ...](seconds) 格式 转换成字符串
def make_chunk_vtt(subtitles):
    def format_ts(seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds - h * 3600 - m * 60 - s) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

    lines = []
    for sub in subtitles:
        lines.append(f"{format_ts(sub['start_time'])} --> {format_ts(sub['end_time'])}")
        lines.append(sub['text'])
        lines.append("")
    return "\n".join(lines)


# 把导出的 .vtt 文件还原成 [{start_time, end_time, text}, ...] 格式
def parse_vtt_to_subtitles(vtt_path: str) -> list[dict]:
    def parse_ts(ts: str) -> float:
        """把 "00:03:15.500" 转成 195.5 秒"""
        h, m, s = ts.split(":")
        sec, ms = s.split(".")
        return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000

    with open(vtt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    subtitles = []
    i = 0

    # 跳过 WEBVTT 头部和空行
    while i < len(lines) and (lines[i].startswith('WEBVTT') or lines[i].strip() == ''):
        i += 1

    while i < len(lines):
        line = lines[i].strip()

        if '-->' in line:
            # 时间戳行："00:03:15.500 --> 00:03:20.000"
            parts = line.split('-->')
            start = parse_ts(parts[0].strip())
            end = parse_ts(parts[1].strip())

            # 下一行是文本
            i += 1
            text = lines[i].strip() if i < len(lines) else ''

            subtitles.append({'start_time': start, 'end_time': end, 'text': text})

        i += 1

    return subtitles
