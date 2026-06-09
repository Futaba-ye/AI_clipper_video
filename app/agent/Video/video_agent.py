from concurrent.futures import ThreadPoolExecutor, as_completed
from app.agent.Video import scene_summarize
from openai import OpenAI


# 输入视频路径，返回视频总结Json列表
def generate_scene_summaries(scenes, video_path, api_key, base_url, model, max_workers=3):
    client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )

    print("正在对视频进行识别")
    # 并发处理
    video_summaries = [None] * len(scenes)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(scene_summarize.summarize_scene, scene, video_path, client, model): i
            for i, scene in enumerate(scenes)
        }
        for future in as_completed(futures):
            i = futures[future]
            video_summaries[i] = future.result()
    print("已将scenes总结")

    return video_summaries

