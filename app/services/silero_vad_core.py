import soundfile
import torch
from silero_vad import load_silero_vad, get_speech_timestamps

vad_model = None


# 懒加载模型，（如果一个进程内多次调用该模型）
def load_vad_model():
    global vad_model
    if vad_model is None:
        vad_model = load_silero_vad()
    return vad_model


# 音频提纯，去除噪音与空白音(16k音频采样频率)
def extract_speech_segments(audio_filename: str):
    print("[VAD] 开始提取有声片段")

    model = load_vad_model()
    # soundfile 解码器进行解码
    data, sr = soundfile.read(audio_filename)
    # 确保单声道
    if data.ndim > 1:
        data = data[:, 0]
    wav = torch.from_numpy(data).float()
    # 获取时间戳
    speech_timestamps = get_speech_timestamps(
        wav,
        model,
        min_silence_duration_ms=700,
        speech_pad_ms=300,
        return_seconds=True,  # Return speech timestamps in seconds (default is samples)
    )

    print(f"[VAD] 完成，共检测到 {len(speech_timestamps)} 个语音片段")

    return wav, sr, speech_timestamps
