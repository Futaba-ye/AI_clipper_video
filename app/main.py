from app.services import ffmpeg_core, whisper_core, ffmpeg_clipper
from app.agent.Audio import audio_agent
from app.agent.Video import scene_detect, video_agent
from app.utils import VTT_writer, VTT_parser
from app.agent import summary_result


# 处理视频并剪辑精彩片段
def ai_clipper_video(file_path, output_audio_path, output_video_path,
                     output_subtitles_path, output_audio_summary_path,
                     output_scenes_path, output_video_summary_path, output_result_vtt_path, output_dir,
                     audio_api_key, audio_base_url, audio_model,
                     video_api_key, video_base_url, video_model,
                     summary_api_key, summary_base_url, summary_model):

    # 抽取音频和视频
    ffmpeg_core.extract_audio(file_path, output_audio_path)
    ffmpeg_core.extract_video(file_path, output_video_path)

    # 处理音频
    # 获取音频文本
    audio_subtitles = whisper_core.transcribe_audio(output_audio_path)
    VTT_writer.write_vtt(subtitles=audio_subtitles, output_path=output_subtitles_path)
    # 获取音频总结
    audio_result = audio_agent.generate_audio_summary(audio_subtitles, audio_api_key, audio_base_url, audio_model)
    VTT_writer.write_formatted_vtt(audio_result, output_audio_summary_path)

    # 处理视频
    # 获取画面片段时间轴
    scenes = scene_detect.detect_scenes(output_video_path)
    VTT_writer.write_formatted_vtt(VTT_parser.scenes_to_vtt(scenes), output_scenes_path)
    # 获取画面总结
    video_result = video_agent.generate_scene_summaries(scenes, output_video_path, video_api_key, video_base_url, video_model)
    VTT_writer.write_formatted_vtt(video_result, output_video_summary_path)

    # 获取最后的分析总结
    result_summary = summary_result.detect_highlights(summary_api_key, summary_base_url, summary_model, audio_result, video_result)
    VTT_writer.write_clipper_vtt(result_summary, output_result_vtt_path)

    # 剪辑部分
    ffmpeg_clipper.clip_video(file_path, result_summary, output_dir)


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()

    # ============================================================
    # RESUME_MODE 选一：
    #   "full"   — 完整流程（FFmpeg → ASR → 音频总结 → 场景检测 → 画面总结 → 融合 → 剪辑）
    #   "video"  — 从画面总结恢复（跳过 ASR+音频总结，读取 audio_summary.vtt）
    #   "fusion" — 从双通道融合恢复（跳过全部上游，读取 audio_summary + video_summary 两个 VTT）
    # ============================================================
    RESUME_MODE = "full"

    # ========== 输入文件 ==========
    input_video = r"C:\Users\32600\Desktop\Video\【瓶子录播5.22_杂谈电台】周五ACG聊天室（PPT厨往里进）_P1_1.mp4"

    # ========== 输出目录 ==========
    output_dir = r"C:\Users\32600\Desktop\Video\Video_clipper"
    os.makedirs(output_dir, exist_ok=True)

    # ========== 输出路径 ==========
    output_audio_path         = os.path.join(output_dir, "extracted_audio.wav")
    output_video_path         = os.path.join(output_dir, "extracted_video.mp4")
    output_subtitles_path     = os.path.join(output_dir, "subtitles.vtt")
    output_audio_summary_path = os.path.join(output_dir, "audio_summary.vtt")
    output_scenes_path        = os.path.join(output_dir, "scenes.vtt")
    output_video_summary_path = os.path.join(output_dir, "video_summary.vtt")
    output_result_vtt_path    = os.path.join(output_dir, "result_summary.vtt")

    # ========== API 密钥 ==========
    audio_api_key   = os.getenv("Audio_API_KEY")
    audio_base_url  = os.getenv("Audio_BASE_URL")
    audio_model     = "deepseek-chat"

    video_api_key   = os.getenv("VISION_API_KEY")
    video_base_url  = os.getenv("VISION_BASE_URL")
    video_model     = "qwen-vl-plus"

    summary_api_key  = os.getenv("Audio_API_KEY")
    summary_base_url = os.getenv("Audio_BASE_URL")
    summary_model    = "deepseek-chat"

    # ================================================================
    if RESUME_MODE == "full":
        # ==================== 完整流程 ====================
        ai_clipper_video(
            file_path=input_video,
            output_audio_path=output_audio_path,
            output_video_path=output_video_path,
            output_subtitles_path=output_subtitles_path,
            output_audio_summary_path=output_audio_summary_path,
            output_scenes_path=output_scenes_path,
            output_video_summary_path=output_video_summary_path,
            output_result_vtt_path=output_result_vtt_path,
            output_dir=output_dir,
            audio_api_key=audio_api_key,
            audio_base_url=audio_base_url,
            audio_model=audio_model,
            video_api_key=video_api_key,
            video_base_url=video_base_url,
            video_model=video_model,
            summary_api_key=summary_api_key,
            summary_base_url=summary_base_url,
            summary_model=summary_model,
        )

    elif RESUME_MODE == "video":
        # ==================== 从画面总结恢复 ====================
        print("[RESUME:video] 从视频场景总结恢复……")
        from app.utils.VTT_parser import parse_vtt_to_subtitles

        audio_result = parse_vtt_to_subtitles(output_audio_summary_path)
        print(f"[RESUME:video] 已加载音频总结，共 {len(audio_result)} 条")

        scenes = scene_detect.detect_scenes(output_video_path)
        VTT_writer.write_formatted_vtt(VTT_parser.scenes_to_vtt(scenes), output_scenes_path)
        print(f"[RESUME:video] 已检测 {len(scenes)} 个场景")

        video_result = video_agent.generate_scene_summaries(
            scenes, output_video_path, video_api_key, video_base_url, video_model
        )
        VTT_writer.write_formatted_vtt(video_result, output_video_summary_path)

        result_summary = summary_result.detect_highlights(
            summary_api_key, summary_base_url, summary_model,
            audio_result, video_result
        )
        VTT_writer.write_clipper_vtt(result_summary, output_result_vtt_path)

        ffmpeg_clipper.clip_video(input_video, result_summary, output_dir)
        print("[RESUME:video] 完成！")

    elif RESUME_MODE == "fusion":
        # ==================== 从双通道融合恢复 ====================
        print("[RESUME:fusion] 从双通道融合恢复……")
        from app.utils.VTT_parser import parse_vtt_to_subtitles

        audio_result = parse_vtt_to_subtitles(output_audio_summary_path)
        print(f"[RESUME:fusion] 已加载音频总结，共 {len(audio_result)} 条")

        video_result = parse_vtt_to_subtitles(output_video_summary_path)
        print(f"[RESUME:fusion] 已加载画面总结，共 {len(video_result)} 条")

        result_summary = summary_result.detect_highlights(
            summary_api_key, summary_base_url, summary_model,
            audio_result, video_result
        )

        # 保存融合结果
        VTT_writer.write_clipper_vtt(result_summary, output_result_vtt_path)
        print(f"[RESUME:fusion] 融合结果已保存至 {output_result_vtt_path}")

        # 剪辑
        ffmpeg_clipper.clip_video(input_video, result_summary, output_dir)
        print("[RESUME:fusion] 完成！")


