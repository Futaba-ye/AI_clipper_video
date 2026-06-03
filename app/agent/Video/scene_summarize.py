import base64
import json
from json import JSONDecodeError
import cv2
from app.utils.VTT_transform import transform_vtt_time


# 提取帧画面
def extract_frame(video_path: str, timestamp_sec):
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_MSEC, timestamp_sec * 1000)
    ret, frame = cap.read()
    if frame is None:
        return None
    _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    cap.release()
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()


# 总结画面场景
def summarize_scene(scene, video_path, client, model):
    mid = (scene['start_time'] + scene['end_time']) / 2
    base64_frame = extract_frame(video_path, mid)
    if base64_frame is None:
        return []
    SYSTEM_PROMPT = '''你是一个专业的直播画面内容分析系统。我会为你提供一张从直播回放视频中截取的画面，以及该画面对应的时间范围。     
                    【你的任务】
                    1. 仔细观察画面中的人物、动作、场景、界面元素（如游戏画面、弹幕、直播互动组件等）。
                    2. 结合直播内容的常见类型（游戏实况、杂谈聊天、才艺表演、户外直播等），判断当前画面正在发生什么。
                    3. 用一段高信息密度的文字总结画面内容。
                
                    【text 字段生成规则】
                    *   结构要求：采用"场景类型 + 核心内容"的二元结构。首先点明这是什么类型的直播画面（如"游戏对战"、"主播杂谈"、"游戏胜利结算"），随后描述画面中最关键的具体信息（ 
                    人物在做什么、画面中出现了什么值得关注的内容）。
                    *   人称与语态：强制使用第三人称客观叙述（如"主播正在…"、"画面中出现了…"），严禁使用第一人称。
                    *   降噪处理：忽略画面中的非信息性元素（UI 边框、常规弹幕滚动、纯装饰性特效）。只提取有实质内容的部分。
                    *   不确定时保持谨慎：如果画面模糊、过暗或无法确定内容，如实描述为"画面较暗，难以辨认具体内容"等。
                
                    【输出要求】
                    必须严格且仅输出一个合法的 JSON 对象，不要包含 Markdown 代码块标记。
                
                    【数据结构示例】
                    {
                      "start_time": "00:15:30.000",
                      "end_time": "00:17:45.000",
                      "text": "游戏胜利结算画面。玩家完成了本局比赛，结算界面显示击杀数为12、排名第1，主播正在复盘本局的关键操作并感谢观众礼物。"
                    }
                    '''

    start_str = transform_vtt_time(scene["start_time"])  # "00:15:30.000"
    end_str = transform_vtt_time(scene["end_time"])

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": base64_frame}},
                {"type": "text", "text": f"场景时间范围：{start_str} → {end_str}"}
            ]}
        ],
        stream=False
    )

    # 返回python对象
    try:
        return json.loads(response.choices[0].message.content)
    except JSONDecodeError:
        print(f"[ERROR] JSON 解析失败，原始返回: {response.choices[0].message.content}")
        return []
