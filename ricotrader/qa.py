"""Pre-upload check for Rica Shorts. Fails (exit 1 / raises) if the video could look glitched or wrong:
  - a scene uses a clip that isn't from the locked Rica look (only say-*/idle-* Grok clips are allowed)
  - Rica's look drifts in any frame (hair/face colours far from her locked look) -> different-looking woman
  - a hard pose jump at a cut (big frame-to-frame change in the webcam strip)
  - numbers disagree (big result number vs the trade's real P&L, ending number vs the day's last total)
Always writes a contact sheet next to the video (<video>.qa.png) to look at.

  python -m ricotrader.qa episode.json video.mp4
"""
import json
import os
import re
import subprocess
import sys

CAM = "crop=1080:480:0:0"


def _frames(mp4, vf, w, h, fps):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", mp4, "-vf", f"fps={fps},{vf},scale={w}:{h}", "-f", "rawvideo",
                                   "-pix_fmt", "rgb24", "-"])
    n = w * h * 3
    return [raw[i:i + n] for i in range(0, len(raw) - n + 1, n)]


def _num(text):
    m = re.match(r"^\s*([+-])\$([\d,]+)", text or "")
    return (1 if m.group(1) == "+" else -1) * int(m.group(2).replace(",", "")) if m else None


def _cut_times(ep, mp4):
    """Scene start times in the video (where a webcam cut is an edit, not a glitch)."""
    try:
        from ricotrader.render import build_audio_clips
        import tempfile
        _, timeline, _, _ = build_audio_clips(ep["scenes"], tempfile.mkdtemp())
        return [a - 0.35 for a, b in timeline]   # the picture switches 0.35 s before each clip's audio
    except Exception as e:
        print("cut times unavailable:", e)
        return []


def check(ep, mp4):
    errs, notes = [], []
    # 1) only locked-look clips
    for i, sc in enumerate(ep["scenes"]):
        c = os.path.basename(sc.get("clip", ""))
        if not re.match(r"^(say|idle)-[\w-]+\.mp4$", c):
            errs.append(f"scene {i}: clip {c or '(none)'} is not a locked-look Grok clip")
    if ep.get("reactions"):
        errs.append("reaction punch-ins are on (they tint/zoom her and looked fake)")
    # 2) numbers
    ev = ep.get("day_pnl", {}).get("events", [])
    last = ev[-1][2] if ev else None
    for i, sc in enumerate(ep["scenes"]):
        v = _num((sc.get("pop") or {}).get("text"))
        card = sc.get("pnl") or {}
        if v is not None and card.get("final") is not None and not card.get("path") and v != round(card["final"]):
            errs.append(f"scene {i}: big number {v} but the trade closed at {card['final']}")
    endv = _num((ep["scenes"][-1].get("pop") or {}).get("text"))
    if last is not None and endv is not None and endv != round(last):
        errs.append(f"ending number {endv} but the day's last total is {last}")
    for i, sc in enumerate(ep["scenes"]):
        card = sc.get("pnl") or {}
        if card.get("path") and last is not None and i == len(ep["scenes"]) - 1 and round(card["path"][-1]) != round(last):
            errs.append(f"ending day card ends at {card['path'][-1]} but the day total is {last}")
    # 2b) every cut must open on a different pose, never the shared base photo (Mochi, Nov 26: "same smile every cut")
    try:
        from ricotrader.render import resolve_starts, start_diff, START_MIN_DIFF
        resolve_starts(ep["scenes"])
        starts = []
        for i, sc in enumerate(ep["scenes"]):
            if not sc.get("clip"):
                continue
            dv, fr0 = start_diff(sc["clip"], float(sc.get("clip_from", 0)))
            if dv < START_MIN_DIFF:
                errs.append(f"scene {i} opens on the base photo (same default smile), diff {dv:.0f} < {START_MIN_DIFF}")
            for j, f in starts:
                if sum(abs(x - y) for x, y in zip(f, fr0)) / len(f) < 8:
                    errs.append(f"scenes {j} and {i} open on the same pose")
            starts.append((i, fr0))
        notes.append("cut starts: " + ", ".join(f"{i}@{sc.get('clip_from')}" for i, sc in enumerate(ep["scenes"]) if sc.get("clip")))
    except Exception as e:
        errs.append(f"could not check cut starts: {e}")
    # 3) look drift + pose jumps in the webcam strip
    fps, w, h = 10, 96, 43
    fr = _frames(mp4, CAM, w, h, fps)
    def stats(b):          # dark-hair share and mean colour in the face/hair box (centre third)
        px = [(b[k], b[k + 1], b[k + 2]) for y in range(4, 36) for x in range(30, 66) for k in [(y * w + x) * 3]]
        dark = sum(1 for r, g, bb in px if r + g + bb < 150) / len(px)
        mr = sum(p[0] for p in px) / len(px); mg = sum(p[1] for p in px) / len(px); mb = sum(p[2] for p in px) / len(px)
        return dark, mr, mg, mb
    st = [stats(b) for b in fr]
    med = sorted(s[0] for s in st)[len(st) // 2]
    drift = [i / fps for i, s in enumerate(st) if med > 0.05 and s[0] < med * 0.45]
    if len(drift) >= 3:
        errs.append(f"her look drifts (hair much lighter than usual) at {drift[0]:.1f}s ({len(drift)} frames)")
    jumps = []
    cut_t = _cut_times(ep, mp4)
    for i in range(1, len(fr)):
        if any(abs(i / fps - c) < 0.25 for c in cut_t):
            continue
        d = sum(abs(a - b) for a, b in zip(fr[i], fr[i - 1])) / len(fr[i])
        if d > 28:
            jumps.append((round(i / fps, 1), round(d)))
    if jumps:
        errs.append(f"hard jump(s) in the webcam at {jumps[:5]}")
    notes.append(f"frames {len(fr)}, median dark-hair share {med:.2f}, biggest cam change "
                 f"{max((sum(abs(a - b) for a, b in zip(fr[i], fr[i - 1])) / len(fr[i]) for i in range(1, len(fr))), default=0):.0f}")
    # 4) contact sheet
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp4, "-vf", "fps=1,scale=216:-1,tile=10x5", "-frames:v", "1",
                    mp4 + ".qa.png"], check=False)
    return errs, notes


if __name__ == "__main__":
    ep = json.load(open(sys.argv[1]))
    errs, notes = check(ep, sys.argv[2])
    print("\n".join(notes))
    if errs:
        print("QA FAILED:\n- " + "\n- ".join(errs))
        sys.exit(1)
    print("QA passed")
