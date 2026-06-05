from app.services import ffmpeg_core, whisper_core
from app.agent.Audio import audio_agent
from app.agent.Video import scene_detect, video_agent
from app.utils import VTT_writer, VTT_parser
from app.agent import summary_result


# 处理视频并剪辑精彩片段
def AI_clipper_Video(File_Path, Output_Audio_Path, Output_Video_Path, audio_api_key, audio_base_url, audio_model,
                     video_api_key, video_base_url, video_model, summary_api_key, summary_base_url, summary_model):
    File_Path = r"C:\Users\32600\Desktop\Video\【瓶子录播5.22_杂谈电台】周五ACG聊天室（PPT厨往里进）_P1_1.mp4"
    Output_Audio_Path = r"C:\Users\32600\Desktop\Test_AI_Clipper\【瓶子录播5.22_杂谈电台】周五ACG聊天室（PPT厨往里进）_P1_1.wav"
    Output_Video_Path = r"C:\Users\32600\Desktop\Test_AI_Clipper\【瓶子录播5.22_杂谈电台】周五ACG聊天室（PPT厨往里进）_P1_1.mp4"

    # 抽取音频和视频
    ffmpeg_core.extract_audio(File_Path, Output_Audio_Path)
    ffmpeg_core.extract_video(File_Path, Output_Video_Path)

    # 处理音频
    # 获取音频文本
    Audio_subtitles = whisper_core.get_text(Output_Audio_Path)
    VTT_writer.write_vtt(subtitles=Audio_subtitles, output_path=Output_subtitles_Path)
    # 获取音频总结
    audio_result = audio_agent.get_audio_summary(Audio_subtitles, audio_api_key, audio_base_url, audio_model)
    VTT_writer.output_vtt(audio_result, Output_Audio_Summary_Path)

    # 处理视频
    # 获取画面片段时间轴
    scenes = scene_detect.detect_scene(Output_Video_Path)
    VTT_writer.output_vtt(VTT_parser.scenes_to_vtt(scenes), Output_scenes_Path)
    # 获取画面总结
    video_result = video_agent.get_scene_summaries(scenes, Output_Video_Path, video_api_key, video_base_url, video_model)
    VTT_writer.output_vtt(video_result, Output_Video_Summary_Path)

    # 获取最后的分析总结
    result_summary = summary_result.audio_video_summary(summary_api_key, summary_base_url, summary_model, audio_result, video_result)

    # 剪辑部分




