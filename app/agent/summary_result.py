import json
from json import JSONDecodeError
from openai import OpenAI
from app.utils.llm_json import parse_llm_json
from app.utils.llm_retry import retry_on_failure
from app.utils.log_config import get_logger

logger = get_logger(__name__)


@retry_on_failure(max_retries=3)
def _call_llm(client, model, messages):
    return client.chat.completions.create(model=model, messages=messages, timeout=120)


# 输入音频和视频的总结，输出有意义的内容片段 (至少传入一段)
def detect_highlights(api_key, base_url, model, audio_summaries=None, video_summaries=None):
    client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )

    SYSTEM_PROMPT = '''你是一个专业的直播回放精彩片段识别系统。你的任务是综合分析"音频总结"和"视频画面总结"两个通道的数据，
    从中识别出值得剪辑成独立视频的精彩片段，输出可直接用于视频剪辑的时间段列表。

    ## 你的任务
    1. 仔细阅读音频总结和视频总结，理解直播全程发生了什么。
    2. 交叉比对两个通道的信息，找出值得剪辑的精彩片段。
    3. **重点关注连续性**：如果时间上相邻或连续的多个总结段落实际上在讨论同一话题、同一事件，应当将它们合并为一个连贯的剪辑片段，而不是拆成多个零散的片段。
    4. 如果没有值得剪辑的内容，返回空列表。

    ## 精彩片段判定思路
    你需要根据以下维度的信号，综合判断一个片段是否值得剪辑：

    ### 音频维度（来自 ASR 字幕总结）
    - **情绪波动**：主播或参与者的强烈情绪表达，如大笑、惊呼、激动、沮丧等
    - **冲突与反转**：争论、对立、预期与结果的戏剧性反差
    - **精彩内容**：主播描述或进行中的关键事件、有实质内容的话题、意外结果
    - **节奏变化**：气氛的突然转变，如从平静到激烈、从严肃到搞笑
    - **记忆点**：可能被观众记住和传播的经典台词、口误、有趣互动

    ### 视频维度（来自画面场景分析）
    - **画面高潮**：关键事件发生的视觉时刻，如精彩操作、重要对决、标志性结算节点等
    - **画面突变**：突如其来的视觉变化、意外场面、有趣的表情或反应
    - **互动氛围**：观众热烈反应的视觉迹象，如弹幕刷屏、礼物特效等
    - **视觉张力**：画面本身的冲击力、紧张感或美感

    ### 综合判定规则
    - **双通道印证加分**：音频和视频在同一时间段都显示精彩信号 → 可信度更高
    - **单一通道也可**：仅音频或视频一方有精彩信号也可入选，但判断应更审慎
    - **连续性合并（重要）**：如果多个时间连续的总结段落围绕同一话题展开，应合并为一个完整的剪辑片段，使最终输出的片段具有完整的故事线
    - **合并判断依据**：以内容相关性为准——时间相近且主题一致即应合并，不要让同一话题被切分成多个碎片
    - **宁缺毋滥**：无实质亮点的常规内容不应入选

    ## 缓冲时间处理
    你输出的 start_time 和 end_time 需要包含适当的缓冲时间：
    - 在核心内容前预留 3-8 秒的上下文引入，让观众了解背景
    - 在精彩内容结束后预留 2-5 秒的收尾，避免戛然而止
    - 确保缓冲后整体片段连贯可懂，不要从一个突兀的位置开始

    ## 输出要求
    必须严格且仅输出一个合法的 JSON 数组，不要包含 Markdown 代码块标记，不要包含任何其他文字。

    ## 输出数据结构
    [
      {
        "start_time": "00:15:30.000",
        "end_time": "00:17:45.000",
        "title": "作为这个视频片段的标题", 
        "summary": "用一段话概述这个片段发生了什么、为什么精彩、包含哪些关键看点。"
      }
    ]
    '''

    if not audio_summaries and not video_summaries:
        logger.warning("detect_highlights 未收到任何输入，返回空列表")
        return []

    if audio_summaries and video_summaries:
        USER_PROMPT = f'''音频总结：
                          {json.dumps(audio_summaries, ensure_ascii=False, indent=2)}
                          视频总结：
                          {json.dumps(video_summaries, ensure_ascii=False, indent=2)}'''

    elif audio_summaries:
        USER_PROMPT = f'''音频总结：{json.dumps(audio_summaries, ensure_ascii=False, indent=2)}'''
    elif video_summaries:
        USER_PROMPT = f'''视频总结：{json.dumps(video_summaries, ensure_ascii=False, indent=2)}'''

    # 调用模型
    response = _call_llm(
        client, model,
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT}
        ]
    )

    try:
        return parse_llm_json(response.choices[0].message.content)
    except JSONDecodeError:
        logger.error(f"JSON 解析失败，原始返回: {response.choices[0].message.content}")
        return []




