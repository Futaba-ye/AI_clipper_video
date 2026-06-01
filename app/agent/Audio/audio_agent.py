import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI
import app.agent.Audio.chunk_summarize as chunk_summarize
import app.agent.Audio.re_summarize_boundary as re_summarize_boundary
import app.agent.Audio.summary_boundaries_review as summary_boundaries_review


# 输入whisper chunks，返回 JSON 字符串 summaries {start_time, end_time, context}
def get_audio_summary(chunks, api_key, base_url, model, max_workers=3):
    client = OpenAI(
        api_key=api_key,
        base_url=base_url)

    #  并发处理，获取chunk_summaries列表
    chunk_summaries = [None] * len(chunks)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(chunk_summarize.summarize_chunk, chunk, client, model): i
            for i, chunk in enumerate(chunks)
        }
        for future in as_completed(futures):
            i = futures[future]
            chunk_summaries[i] = future.result()

    # 边界检查




