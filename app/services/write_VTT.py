# 接收whisper生成的时间轴列表，生成VTT字幕
def write_vtt(subtitles, output_path):
    print("开始生成VTT字幕")

    # 将时间转化为VTT标准时间戳
    def helper(time):
        h = int(time // 3600)
        mins = int((time % 3600) // 60)
        s = int(time % 60)
        ms = int((time - h * 3600 - mins * 60 - s) * 1000)
        return f"{h:02d}:{mins:02d}:{s:02d}.{ms:03d}"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("WEBVTT\n\n")
        for subtitle in subtitles:
            start_str = helper(subtitle['start'])
            end_str = helper(subtitle['end'])
            text = subtitle['text']

            f.write(f"{start_str} --> {end_str}\n{text}\n\n")

    print(f"[导出] 字幕已保存至 {output_path}")

