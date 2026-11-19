"""Make a censored copy of a clip: find exposed body parts with NudeNet and blur them."""
import subprocess

import cv2
import numpy as np

EXPOSED = {
    "FEMALE_BREAST_EXPOSED", "FEMALE_GENITALIA_EXPOSED", "MALE_GENITALIA_EXPOSED",
    "BUTTOCKS_EXPOSED", "ANUS_EXPOSED",
}
DETECT_EVERY = 3   # run the detector on every 3rd frame
HOLD = 8           # keep a box blurred this many frames after it was last seen
PAD = 0.35         # grow each box by 35% so edges are covered
MIN_SCORE = 0.25

_detector = None


def _detect(frame):
    global _detector
    if _detector is None:
        from nudenet import NudeDetector
        _detector = NudeDetector()
    out = []
    for d in _detector.detect(frame):
        if d["class"] in EXPOSED and d["score"] >= MIN_SCORE:
            out.append(d["box"])  # [x, y, w, h]
    return out


def _blur(frame, box):
    h, w = frame.shape[:2]
    x, y, bw, bh = box
    x0 = max(0, int(x - bw * PAD)); y0 = max(0, int(y - bh * PAD))
    x1 = min(w, int(x + bw * (1 + PAD))); y1 = min(h, int(y + bh * (1 + PAD)))
    if x1 <= x0 or y1 <= y0:
        return
    roi = frame[y0:y1, x0:x1]
    # pixelate then blur: reads clearly as "censored"
    small = cv2.resize(roi, (max(1, (x1 - x0) // 16), max(1, (y1 - y0) // 16)), interpolation=cv2.INTER_LINEAR)
    frame[y0:y1, x0:x1] = cv2.GaussianBlur(cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST), (0, 0), 6)


def censor(src: str, out: str) -> int:
    """Write a censored copy of src to out. Returns how many frames had something blurred."""
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", f"{fps}", "-i", "-",
         "-i", src, "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest", out],
        stdin=subprocess.PIPE,
    )
    active: list[tuple[list, int]] = []  # (box, frames left)
    hits, i = 0, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % DETECT_EVERY == 0:
            active = [(b, n) for b, n in active if n > 0] + [(b, HOLD) for b in _detect(frame)]
        if active:
            hits += 1
            for b, _ in active:
                _blur(frame, b)
            active = [(b, n - 1) for b, n in active]
        enc.stdin.write(np.ascontiguousarray(frame).tobytes())
        i += 1
    cap.release()
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("ffmpeg failed while writing censored clip")
    return hits
