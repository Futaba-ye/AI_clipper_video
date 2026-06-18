from app.utils.VTT_time import transform_vtt_time, parse_vtt_ts


# 将 [{start_time, end_time, text}, ...]（seconds 格式）转换成 VTT 字符串
def make_chunk_vtt(subtitles):
    lines = []
    for sub in subtitles:
        lines.append(
            f"{transform_vtt_time(sub['start_time'])} --> {transform_vtt_time(sub['end_time'])}"
        )
        lines.append(sub['text'])
        lines.append("")
    return "\n".join(lines)


# VTT 文件公共解析器：逐条目产出 (start_str, end_str, text)
def _parse_vtt_entries(vtt_path: str):
    """读取 .vtt 文件，逐个 yield (start_time_str, end_time_str, text)。"""
    with open(vtt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    # 跳过 WEBVTT 头部和空行
    while i < len(lines) and (lines[i].startswith('WEBVTT') or lines[i].strip() == ''):
        i += 1

    while i < len(lines):
        line = lines[i].strip()

        if '-->' in line:
            parts = line.split('-->')
            start_str = parts[0].strip()
            end_str = parts[1].strip()

            # 下一行是文本
            i += 1
            text = lines[i].strip() if i < len(lines) else ''

            yield start_str, end_str, text

        i += 1


# 把导出的 .vtt 文件还原成 [{start_time, end_time, text}, ...] 格式（seconds）
def parse_vtt_to_subtitles(vtt_path: str) -> list[dict]:
    subtitles = []
    for start_str, end_str, text in _parse_vtt_entries(vtt_path):
        subtitles.append({
            'start_time': parse_vtt_ts(start_str),
            'end_time': parse_vtt_ts(end_str),
            'text': text
        })
    return subtitles


# 把 VTT 文件解析为原始时间戳字符串格式（"HH:MM:SS.mmm"）
def parse_vtt_to_raw_subtitles(vtt_path: str) -> list[dict]:
    return [
        {'start_time': start_str, 'end_time': end_str, 'text': text}
        for start_str, end_str, text in _parse_vtt_entries(vtt_path)
    ]


# 将场景检测列表转换为 VTT 格式列表（带占位文本）
def scenes_to_vtt(scenes):
    result = []
    for i, scene in enumerate(scenes, 1):
        result.append({
            "start_time": transform_vtt_time(scene["start_time"]),
            "end_time": transform_vtt_time(scene["end_time"]),
            "text": f"场景 {i}"
        })
    return result


def parse_clipper_vtt(vtt_path: str) -> list[dict]:
    """逆解析 write_clipper_vtt 的输出，恢复为高光片段列表。

    write_clipper_vtt 每条目格式：
        时间戳行
        title（第一行文本）
        summary（第二行文本）
        空行

    返回: [{start_time, end_time, title, summary}, ...]
    """
    results = []
    with open(vtt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    # 跳过 WEBVTT 头部和空行
    while i < len(lines) and (lines[i].startswith('WEBVTT') or lines[i].strip() == ''):
        i += 1

    while i < len(lines):
        line = lines[i].strip()
        if '-->' in line:
            parts = line.split('-->')
            start_str = parts[0].strip()
            end_str = parts[1].strip()

            # 第一行文本 = title
            i += 1
            title = lines[i].strip() if i < len(lines) else ''

            # 第二行文本 = summary
            i += 1
            summary = lines[i].strip() if i < len(lines) else ''

            results.append({
                'start_time': start_str,
                'end_time': end_str,
                'title': title,
                'summary': summary,
            })
        i += 1

    return results
