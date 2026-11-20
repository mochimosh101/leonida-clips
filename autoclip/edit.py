"""Turn a 16:9 clip into a 1080x1920 Short: blurred fill, zoomed gameplay, captions, Rico voice + avatar."""
import json
import os
import subprocess

W, H = 1080, 1920
FG_H = 860          # zoomed gameplay band height
FG_Y = 400          # top of gameplay band


def probe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def has_audio(path: str) -> bool:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", path],
        capture_output=True, text=True,
    ).stdout
    return bool(out.strip())


def render(src: str, ass_path: str, hook_mp3: str, verdict_mp3: str, out: str,
           max_duration: float, avatar: str | None = None,
           mid_mp3: str | None = None, mid_at: float | None = None) -> str:
    dur = min(probe_duration(src), max_duration)
    hook_len = probe_duration(hook_mp3)
    verdict_len = probe_duration(verdict_mp3)
    verdict_at = max(hook_len + 0.5, dur - verdict_len - 0.3)

    inputs = ["-t", f"{dur:.2f}", "-i", src, "-i", hook_mp3, "-i", verdict_mp3]
    # Rico's mid-clip reaction (more original commentary per Short); dropped if it won't fit cleanly
    use_mid = False
    if mid_mp3 and mid_at is not None:
        mid_len = probe_duration(mid_mp3)
        mid_at = max(mid_at, hook_len + 0.8)
        use_mid = mid_at + mid_len + 0.5 <= verdict_at
    if use_mid:
        inputs += ["-i", mid_mp3]
    av_idx = 4 if use_mid else 3
    use_avatar = bool(avatar and os.path.exists(avatar))
    if use_avatar:
        inputs += ["-loop", "1", "-t", f"{dur:.2f}", "-i", avatar]

    ass = ass_path.replace("\\", "/").replace(":", "\\:")
    v = (
        f"[0:v]split[a][b];"
        f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=25:2,eq=brightness=-0.15[bg];"
        f"[b]scale=-2:{FG_H},crop={W}:{FG_H}[fg];"
        f"[bg][fg]overlay=0:{FG_Y}[base];"
    )
    if use_avatar:
        on = f"between(t,0,{hook_len + 0.4:.2f})+between(t,{verdict_at:.2f},{dur:.2f})"
        if use_mid:
            on += f"+between(t,{mid_at:.2f},{mid_at + mid_len + 0.3:.2f})"
        v += (f"[{av_idx}:v]scale=300:-1[av];"
              f"[base][av]overlay=40:{H}-300-260:enable='{on}'[base2];"
              f"[base2]ass='{ass}'[vout]")
    else:
        v += f"[base]ass='{ass}'[vout]"

    if use_mid:
        ms = int(mid_at * 1000)
        vo = (
            f"[1:a]adelay=200|200[h];"
            f"[3:a]adelay={ms}|{ms}[md];"
            f"[2:a]adelay={int(verdict_at * 1000)}|{int(verdict_at * 1000)}[vd];"
            f"[h][md][vd]amix=inputs=3:normalize=0,volume=1.6,asplit[vo1][vo2];"
        )
    else:
        vo = (
            f"[1:a]adelay=200|200[h];"
            f"[2:a]adelay={int(verdict_at * 1000)}|{int(verdict_at * 1000)}[vd];"
            f"[h][vd]amix=inputs=2:normalize=0,volume=1.6,asplit[vo1][vo2];"
        )
    if has_audio(src):
        a = vo + (
            "[0:a]aresample=48000[orig];"
            "[orig][vo1]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck];"
            "[duck][vo2]amix=inputs=2:normalize=0:duration=first[aout]"
        )
    else:
        a = vo + f"[vo1]apad=whole_dur={dur:.2f}[aout];[vo2]anullsink"

    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
         "-filter_complex", v + ";" + a,
         "-map", "[vout]", "-map", "[aout]", "-t", f"{dur:.2f}",
         "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out],
        check=True,
    )
    return out


def sample_frames(src: str, work: str, n: int = 4) -> list[str]:
    """Grab n evenly spaced JPEG frames (small) for the writer to look at."""
    dur = probe_duration(src)
    paths = []
    for i in range(n):
        t = dur * (i + 0.5) / n
        out = os.path.join(work, f"frame{i}.jpg")
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", src,
                            "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "5", out])
        if r.returncode == 0 and os.path.exists(out):
            paths.append(out)
    return paths


def quiet_spot(words, dur: float, lo: float = 0.35, hi: float = 0.7) -> float:
    """Start time for Rico's mid-clip line: the longest pause in the streamer's speech in the middle stretch."""
    best, best_gap = dur * 0.5, 0.0
    times = sorted((w.start, w.end) for w in words)
    for (s0, e0), (s1, _) in zip(times, times[1:]):
        if lo * dur <= e0 <= hi * dur and s1 - e0 > best_gap:
            best, best_gap = e0 + 0.15, s1 - e0
    return best
