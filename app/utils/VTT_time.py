# 将秒数转化为 VTT 标准时间戳 "HH:MM:SS.mmm"
def transform_vtt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - h * 3600 - mins * 60 - s) * 1000)
    return f"{h:02d}:{mins:02d}:{s:02d}.{ms:03d}"


# 将 VTT 时间戳 "HH:MM:SS.mmm" 解析为秒数
def parse_vtt_ts(ts: str) -> float:
    h, m, s = ts.split(":")
    sec, ms = s.split(".")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000
