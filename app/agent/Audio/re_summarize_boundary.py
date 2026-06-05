# 转换时间
import json
from json import JSONDecodeError

from app.utils.VTT_parser import make_chunk_vtt


def parse_time(ts: str) -> float:
    """把 "00:28:15.500" 转成 1695.5 秒"""
    h, m, s = ts.split(":")
    sec, ms = s.split(".")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000


# 处理原始字幕，返回边界json summary
def re_summarize_boundary(prev_summary, next_summary, prev_chunk, curr_chunk, client, model):
    SYSTEM_PROMPT = """你是一个专业的视频内容总结系统。你会收到一段短小的VTT字幕，这段字幕是从两个相邻时间块的边界区域提取出来的，
                       之前的独立总结在这个边界上发生了话题截断——同一个话题被拆到了两个块的总结里。
                       
                       ## 你的任务
                       仔细阅读这段字幕，它的前两段是两个相邻时间块的边界区域的总结，之后是被重新拼在了一起的被截断的话题的完整上下文。
                       请为这段内容生成新的总结条目，替代之前被拆散的旧条目。
                       
                       ## 要求
                       1. 把被截断的内容合并为一个或多个语义完整的条目
                       2. 准确提取每条总结的 start_time 和 end_time
                       3. text 字段遵循标准格式：主题概括 + 核心细节
                       4. 不要受旧总结的影响，完全基于这段字幕重新判断
                       
                       ## 输出
                       严格只输出一个合法的 JSON ：
                       {"start_time": "HH:MM:SS.mmm", "end_time": "HH:MM:SS.mmm", "text": "..."}
                    """

    # 时间范围
    boundary_start = prev_summary[-1]["start_time"]
    boundary_end = next_summary[0]["end_time"]
    parse_start = parse_time(boundary_start)
    parse_end = parse_time(boundary_end)

    boundary_subs = []
    for sub in prev_chunk:
        if sub["start_time"] >= parse_start:
            boundary_subs.append(sub)
    for sub in curr_chunk:
        if sub["end_time"] <= parse_end:
            boundary_subs.append(sub)

    user_content = f"""【旧总结（被截断的边界）】
      {json.dumps([prev_summary[-1], next_summary[0]], ensure_ascii=False, indent=2)}

      【边界区域的完整原始字幕】
      {make_chunk_vtt(boundary_subs)}"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        stream=False
    )

    try:
        return json.loads(response.choices[0].message.content)
    except JSONDecodeError:
        print(f"[ERROR] JSON 解析失败，原始返回: {response.choices[0].message.content}")
        return []
