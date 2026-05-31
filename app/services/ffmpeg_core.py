import ffmpeg


# 使用ffmpeg提取音频文件
def extract_audio(file_path: str, audio_path: str, format='wav', acodec='pcm_s16le',
                                          ac=1, ar=16000):
    return ffmpeg.input(file_path).output(audio_path, format=format, acodec=acodec,
                                          ac=ac, ar=ar).run()  # silero_vad需要单声道，采样频率16k的音频


# 使用ffmpeg提取视频文件
def extract_video(file_path: str):
    return ffmpeg.input(file_path, vcodec='libx264').video()


