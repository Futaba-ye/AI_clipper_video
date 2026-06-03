import cv2


# 检测场景切换点（返回时间戳列表）
def detect_scene(video_path: str, threshold: float = 30.0, min_scene_seconds: float = 2.0, frame_skip=10):
    cap = cv2.VideoCapture(video_path)  # 实例化一个视频捕获对象
    fps = cap.get(cv2.CAP_PROP_FPS)
    scenes = []
    prev_hist = None
    frame_idx = 0
    scene_start = 0.0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_skip != 0:  # 每 10 帧检测一次
            frame_idx += 1
            continue

        # 用 HSV 直方图做帧间差异
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
        hist = cv2.normalize(hist, hist).flatten()

        if prev_hist is not None:
            diff = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CHISQR)
            if diff > threshold:
                timestamp = frame_idx / fps
                if timestamp - scene_start >= min_scene_seconds:
                    scenes.append({"start_time": scene_start, "end_time": timestamp})
                scene_start = timestamp  # 短于阈值也重置起点，但不上一条记录

        prev_hist = hist
        frame_idx += 1

    scenes.append({"start_time": scene_start, "end_time": frame_idx / fps})
    cap.release()

    return scenes

