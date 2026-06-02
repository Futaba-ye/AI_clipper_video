import json
from json import JSONDecodeError
from app.utils.VTT_transform import make_chunk_vtt


# 将一个vvt字幕chunk总结为summary
def summarize_chunk(chunk, client, model):
    SYSTEM_PROMPT = '''你是一个专业的视频内容分析与总结系统。我会为你提供一段带有时间轴的VTT格式字幕文本。

                    【你的任务】
                    1. 仔细阅读并理解提供的VTT字幕内容。
                    2. 根据上下文和讨论话题的自然转换，将字幕划分为若干个连续的时间段。
                    3. 准确提取每个话题块的起始时间（start_time）和结束时间（end_time）。
                    4. 为每个时间段提炼出高信息熵的内容总结（text）。
                    5. 注意：你收到的VTT字幕可能从视频中间开始或在中间截断，这是正常的。仅基于你看到的这段字幕进行分析即可。
    
                    【 text 字段生成规则】
                    为了确保结构化输出的严谨性与泛化能力，`text` 字段的生成必须严格遵循以下约束：
                    *   结构要求：采用“主题概括 + 核心细节”的二元结构。首先用一句话高度概括该时间段的核心议题或动作（这段内容在干什么），随后提炼该话题下最具信息价值的关键细节（有什么重要的实质性内容）。
                    *   信息提取：允许对内容、数据或技术细节进行适度抽象，核心目标是准确传达该时间段的实质性信息。
                    *   人称与语态：强制使用第三人称客观叙述（如“主讲人演示了”、“视频探讨了”），严禁使用第一人称或代入式语态。
                    *   降噪处理：自动过滤字幕中的所有无信息熵词汇（语气词、停顿、重复性口语、非结构化闲聊）。
    
                    【输出要求】
                    必须严格且仅输出一个合法的 JSON 数组结构。
    
                    【数据结构示例】
                    [
                      {
                        "start_time": "00:03:15.500",
                        "end_time": "00:10:42.000",
                        "text": "讲解机器学习的核心分类。视频介绍了监督学习、无监督学习和强化学习三种基础类型，并重点通过预测房价的模型演示了监督学习的工作原理及其对数据标注的依赖。"
                      },
                      {
                        "start_time": "00:10:42.000",
                        "end_time": "00:15:20.000",
                        "text": "分析项目重构的具体流程。主讲人梳理了旧版代码中存在的耦合问题，并展示了如何通过引入依赖注入模式来解耦核心业务逻辑，同时列举了重构过程中需注意的测试覆盖率要求。"
                      }
                    ]'''
    # 把 chunk 格式化成vtt标准文本
    vtt_text = make_chunk_vtt(chunk)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": vtt_text},
        ],
        stream=False,  # stream=False 非流式（一次性返回）
    )

    raw = response.choices[0].message.content

    # 从返回的字符串解析出Json
    try:
        return json.loads(raw)
    except JSONDecodeError:
        print(f"[ERROR] JSON 解析失败，原始返回: {raw}")
        return []
