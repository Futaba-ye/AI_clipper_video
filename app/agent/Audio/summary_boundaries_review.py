import json
from json import JSONDecodeError
from app.utils.llm_json import parse_llm_json


# 比较相邻两个summary的边界是否高度相似
def review_boundary(prev_summaries, curr_summaries, client, model):
    SYSTEM_PROMPT = """你是一个视频内容边界审查专家。你的任务是检查两个相邻视频片段的摘要，判断它们是否在话题边界上发生了截断。                                                        
              ## 背景
              这两段摘要是从同一段视频的两个相邻时间块各自独立总结出来的。第一个块结束时可能正好在一个话题中间，
              第二个块开始时可能延续了那个话题。由于两个块是独立总结的，同一个话题可能被拆成了两条不同的摘要。
            
              ## 你的任务
              对比【前块尾部】和【后块头部】的摘要，判断是否存在"同一话题被边界截断"的情况。
            
              ## 判断标准
              - **same_topic =
              true**：两边的摘要实质上在描述同一件事/同一话题/同一段对话，只是因为时间分块被拆开了。例如：前块在讲"演示登录功能"，后块接着"演示登录的异常处理"，它们属于同一个演示环节。
              - **same_topic = false**：两边的摘要描述的是不同的话题或不同的内容段落，自然切换。例如：前块在讲"安装Python"，后块在讲"写Hello World"，虽然都是技术内容但属于不同阶段。
            
              ## 输出要求
              严格只输出一个合法的 JSON 对象，不要包含任何其他文字：
            
              {"same_topic": true/false, "reason": "一句话说明判断依据（中文）"}
            
              如果 same_topic 为 true，reason 需要说明应该合并哪些条目、合并后的主题是什么。
              """

    # 获取 Json
    prev_tail = prev_summaries[-1:]  # 前块最后 1 条
    curr_head = curr_summaries[:1]  # 后块前 1 条
    user_content = f"""【前块尾部摘要】
                    {json.dumps(prev_tail, ensure_ascii=False, indent=2)}

                    【后块头部摘要】
                    {json.dumps(curr_head, ensure_ascii=False, indent=2)}"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        stream=False
    )

    try:
        return parse_llm_json(response.choices[0].message.content)
    except JSONDecodeError:
        print(f"[ERROR] JSON 解析失败，原始返回: {response.choices[0].message.content}")
        return []
