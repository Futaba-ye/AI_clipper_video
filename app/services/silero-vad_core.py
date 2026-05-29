import soundfile
import torch
from silero_vad import load_silero_vad, read_audio, get_speech_timestamps


# 音频提纯，去除噪音与空白音
def fresh_audio(audio_filename: str):
    model = load_silero_vad()
    # soundfile 解码器进行解码
    data, _ = soundfile.read(audio_filename)
    # 确保单声道
    if data.ndim() > 1:
        data = data[:, 0]
    wav = torch.from_numpy(data).float()
    # 获取时间戳
    speech_timestamps = get_speech_timestamps(
        wav,
        model,
        min_silence_duration_ms=700,
        speech_pad_ms=100,
        return_seconds=True,  # Return speech timestamps in seconds (default is samples)
    )

    return wav, speech_timestamps
