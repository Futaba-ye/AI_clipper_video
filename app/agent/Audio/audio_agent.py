from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
import app.agent.Audio.chunk_summarize as chunk_summarize
import app.agent.Audio.re_summarize_boundary as re_summarize_boundary
import app.agent.Audio.summary_boundaries_review as summary_boundaries_review
from app.agent.Audio.chunks_split import split_chunks


# 输入whisper chunks，返回 JSON 字符串 summaries {start_time, end_time, context}
def get_audio_summary(subtitles, api_key, base_url, model, chunk_seconds=900, max_workers=3):
    if not subtitles:
        return []

    chunks = split_chunks(subtitles, chunk_seconds)
    print("已将vtt切分为chunks")

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
    print("已将chunks初步总结，正在进行边界检查")

    # 边界检查
    Summaries_result = chunk_summaries[0].copy()
    for i in range(1, len(chunk_summaries)):
        prev_summary = chunk_summaries[i - 1]
        curr_summary = chunk_summaries[i]
        is_similar = summary_boundaries_review.review_boundaries(prev_summary, curr_summary, client, model)

        # 讲的是同一内容
        if is_similar["same_topic"]:
            print(f"{i - 1}--{i} True: {is_similar["reason"]}")
            boundary_summary = re_summarize_boundary.re_summarize_boundary(prev_summary, curr_summary,
                                                                           chunks[i - 1], chunks[i], client, model)
            del Summaries_result[-1]
            del curr_summary[0]
            Summaries_result.append(boundary_summary)
            Summaries_result.extend(curr_summary)
        else:
            Summaries_result.extend(curr_summary)
            print(f"{i - 1}--{i} False: {is_similar["reason"]}")
    print("边界检查完毕，已返回完整音频总结")

    return Summaries_result



