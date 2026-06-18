from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
import app.agent.Audio.chunk_summarize as chunk_summarize
import app.agent.Audio.re_summarize_boundary as re_summarize_boundary
import app.agent.Audio.summary_boundaries_review as summary_boundaries_review
from app.agent.Audio.chunks_split import split_chunks
from app.utils.log_config import get_logger

logger = get_logger(__name__)


# 输入whisper chunks，返回 JSON 字符串 summaries {start_time, end_time, context}
def generate_audio_summary(subtitles, api_key, base_url, model, chunk_seconds=900, max_workers=3):
    if not subtitles:
        return []

    chunks = split_chunks(subtitles, chunk_seconds)
    logger.info("已将vtt切分为chunks")

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
            try:
                chunk_summaries[i] = future.result()
            except Exception as e:
                logger.error(f"chunk {i} 总结失败: {e}")
                chunk_summaries[i] = []
    logger.info("已将chunks初步总结，正在进行边界检查")

    # ============================================================
    # 边界检查：先并行审查所有相邻对，再串行重写合并
    # ============================================================
    n = len(chunk_summaries)
    # 并行发出所有 review_boundary 请求
    review_results = [None] * (n - 1)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        review_futures = {}
        for i in range(1, n):
            review_futures[
                executor.submit(
                    summary_boundaries_review.review_boundary,
                    chunk_summaries[i - 1], chunk_summaries[i], client, model
                )
            ] = i - 1
        for future in as_completed(review_futures):
            idx = review_futures[future]
            try:
                review_results[idx] = future.result()
            except Exception as e:
                logger.error(f"review_boundary 对 {idx}--{idx + 1} 失败: {e}")
                review_results[idx] = {"same_topic": False, "reason": f"审查异常: {e}"}

    # 串行应用合并结果
    summaries_result = chunk_summaries[0].copy()
    for i in range(1, n):
        is_similar = review_results[i - 1]
        prev_summary = chunk_summaries[i - 1]
        curr_summary = chunk_summaries[i]

        # 讲的是同一内容
        if is_similar.get("same_topic", False):
            logger.info(f"{i - 1}--{i} True: {is_similar['reason']}")
            try:
                boundary_summary = re_summarize_boundary.re_summarize_boundary(
                    prev_summary, curr_summary,
                    chunks[i - 1], chunks[i], client, model
                )
                del summaries_result[-1]
                del curr_summary[0]
                summaries_result.append(boundary_summary)
                summaries_result.extend(curr_summary)
            except Exception as e:
                logger.error(f"re_summarize_boundary {i - 1}--{i} 失败: {e}，跳过合并")
                summaries_result.extend(curr_summary)
        else:
            summaries_result.extend(curr_summary)
            logger.info(f"{i - 1}--{i} False: {is_similar['reason']}")
    logger.info("边界检查完毕，已返回完整音频总结")

    return summaries_result



