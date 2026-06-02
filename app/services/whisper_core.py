from faster_whisper import WhisperModel
import app.services.silero_vad_core as silero_vad_core
from opencc import OpenCC

# 全局变量
whisper_model = None
whisper_config = None


# 懒加载 whisper模型
def get_whisper_model(model_size, device, compute_type):
    global whisper_model, whisper_config
    if whisper_config != (model_size, device, compute_type):
        whisper_model = WhisperModel(model_size_or_path=model_size, device=device, compute_type=compute_type)
        whisper_config = (model_size, device, compute_type)
    return whisper_model


# 获取音频对应的文本
def get_text(audio_filename: str, model_size: str = "large-v3", device: str = "cuda", compute_type="int8", beam_size=5,
             language="zh"):
    # 创建时间轴列表 subtitles
    subtitles = []
    # 创建opencc
    cc = OpenCC('t2s')

    model = get_whisper_model(model_size, device, compute_type)

    # 提纯音频，并获取有声时间轴列表 subtitles
    wav, sr, timestamps = silero_vad_core.fresh_audio(audio_filename)

    cnt, DB, length = 0, 10, len(timestamps)  # 记录已导出文本数量
    print("[ASR] 开始获取音频文本")
    for ts in timestamps:
        # 记录完成进度
        cnt += 1
        if round(cnt / length, 2) * 100 > DB:
            print(f"[ASR] 即将完成 {DB}%")
            DB += 10

        # 采样点
        start = int(ts['start'] * sr)
        end = int(ts['end'] * sr)
        clip = wav[start:end].numpy()
        # 通过whisper模型获取时间戳及其信息
        segments, info = model.transcribe(clip, beam_size=beam_size, condition_on_previous_text=False,
                                                  language=language)  # 取消窗口之间的上下文关系
        for seg in segments:
            # 将繁体字转化为简体字
            seg.text = cc.convert(seg.text)
            subtitles.append({'start_time': round(ts['start'] + seg.start, 3), 'end_time': round(ts['start'] + seg.end, 3), 'text': seg.text})

    return subtitles
