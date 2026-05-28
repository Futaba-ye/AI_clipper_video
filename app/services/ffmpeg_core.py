import ffmpeg


# 使用ffmpeg提取音频文件
def extract_audio(filename: str):
    return ffmpeg.input(filename, acodec='aac').audio()


# 使用ffmpeg提取视频文件
def extract_video(filename: str):
    return ffmpeg.input(filename, vcodec='libx264').video()


