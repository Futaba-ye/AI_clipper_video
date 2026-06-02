# 切分chunks, 每个chunk的时间范围为chunk_seconds
def split_chunks(subtitles, chunk_seconds=900):
    if not subtitles:
        return []

    chunks, chunk = [], []
    window_start_time, window_end_time = subtitles[0]['start_time'], 0

    for subtitle in subtitles:
        if window_end_time - window_start_time > chunk_seconds:
            chunks.append(chunk)
            chunk = []
            window_start_time = subtitle['start_time']

        window_end_time = subtitle['end_time']
        chunk.append(subtitle)

    if chunk:
        chunks.append(chunk)

    return chunks

