"""Render an animated Rico Neon trading Short (1080x1920) from an episode JSON.

Episode JSON:
{
  "date": "2026-11-20",
  "voice": "en-US-BrianMultilingualNeural",
  "scenes": [
    {"say": "words Rico speaks", "mood": "hype|pain|calm|deep",
     "visual": {"type": "stat|trade|compare|line|lesson|quote|outro", ...}}
  ]
}
Everything on screen is drawn here with code (flat cartoon), so no AI image model is involved.

Usage: python -m ricotrader.render episode.json out.mp4
"""
import asyncio
import json
import math
import os
import random
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
PINK = (255, 20, 180)
CYAN = (0, 229, 255)
YELLOW = (255, 214, 64)
GREEN = (40, 230, 120)
RED = (255, 64, 88)
WHITE = (255, 255, 255)
NIGHT_TOP = (14, 6, 36)
NIGHT_MID = (54, 14, 84)
SKIN = (222, 170, 126)
SKIN_D = (190, 136, 96)
HAIR = (22, 14, 26)
SHIRT = (0, 168, 160)
MOOD_COLOR = {"hype": GREEN, "pain": RED, "calm": CYAN, "deep": (170, 110, 255)}
COLORS = {"green": GREEN, "red": RED, "cyan": CYAN, "pink": PINK, "yellow": YELLOW, "white": WHITE}

FONT_DIRS = ["/usr/share/fonts", os.path.expanduser("~/.fonts"), "assets/fonts"]
_font_cache = {}


def _find_font(names):
    for d in FONT_DIRS:
        for root, _, files in os.walk(d):
            for n in names:
                if n in files:
                    return os.path.join(root, n)
    raise FileNotFoundError(f"none of {names} installed")


def font(kind, size):
    key = (kind, size)
    if key not in _font_cache:
        names = {
            "black": ["InterDisplay-Black.otf", "Inter-Black.otf", "Montserrat-Black.ttf", "DejaVuSans-Bold.ttf"],
            "bold": ["InterDisplay-ExtraBold.otf", "Inter-ExtraBold.otf", "Montserrat-ExtraBold.ttf", "DejaVuSans-Bold.ttf"],
            "medium": ["InterDisplay-Medium.otf", "Inter-Medium.otf", "Montserrat-Medium.ttf", "DejaVuSans.ttf"],
            "serif": ["LiberationSerif-BoldItalic.ttf", "DejaVuSerif-BoldItalic.ttf", "DejaVuSerif-Bold.ttf"],
        }[kind]
        _font_cache[key] = ImageFont.truetype(_find_font(names), size)
    return _font_cache[key]


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def mix(a, b, k):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


# ---------------------------------------------------------------- voice

async def _tts(text, voice, path):
    if os.environ.get("RICO_FAKE_TTS"):  # offline preview: buzzing tone + evenly timed words
        ws = text.split()
        dur = 0.32 * len(ws)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        f"aevalsrc=0.3*sin(2*PI*180*t)*abs(sin(2*PI*3*t)):s=24000:d={dur}", path], check=True)
        return [{"t": i * 0.32, "d": 0.3, "w": w} for i, w in enumerate(ws)]
    import edge_tts
    words = []
    com = edge_tts.Communicate(text, voice, rate="+6%", boundary="WordBoundary")
    with open(path, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({"t": chunk["offset"] / 1e7, "d": chunk["duration"] / 1e7, "w": chunk["text"]})
    return words


def probe_duration(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", path])
    return float(out.strip())


def build_audio(scenes, voice, work):
    """Speak every scene, join with short pauses. Returns (wav path, per-scene timing, word list)."""
    parts, timeline, words, t = [], [], [], 0.35
    gap = 0.35
    for i, sc in enumerate(scenes):
        mp3 = os.path.join(work, f"s{i}.mp3")
        ws = asyncio.run(_tts(sc["say"], voice, mp3))
        dur = probe_duration(mp3)
        timeline.append((t, t + dur))
        words += [{**w, "t": w["t"] + t, "scene": i} for w in ws]
        parts.append((mp3, t))
        t += dur + gap
    total = t + 0.6
    wav = os.path.join(work, "voice.wav")
    inputs, filt = [], []
    for k, (mp3, start) in enumerate(parts):
        inputs += ["-i", mp3]
        filt.append(f"[{k}:a]adelay={int(start * 1000)}|{int(start * 1000)},aresample=48000[a{k}]")
    filt.append("".join(f"[a{k}]" for k in range(len(parts))) + f"amix=inputs={len(parts)}:normalize=0,apad[out]")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filt),
                    "-map", "[out]", "-t", f"{total:.2f}", "-ac", "1", wav], check=True)
    return wav, timeline, words, total


def loudness_per_frame(wav, n_frames):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", wav, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"])
    import array
    a = array.array("h", raw)
    per = 16000 // FPS
    out = []
    for f in range(n_frames):
        seg = a[f * per:(f + 1) * per]
        out.append(math.sqrt(sum(x * x for x in seg) / len(seg)) / 32768 if seg else 0)
    peak = max(out) or 1
    return [min(1.0, v / (peak * 0.55)) for v in out]


# ---------------------------------------------------------------- Rico (flat cartoon, drawn at 2x then scaled)

RICO_W, RICO_H, S = 700, 640, 2
_rico_cache = {}


def rico(mouth, mood):
    """mouth: 0..5 openness level. Cached per (mouth, mood)."""
    key = (mouth, mood)
    if key in _rico_cache:
        return _rico_cache[key]
    im = Image.new("RGBA", (RICO_W * S, RICO_H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def E(x0, y0, x1, y1, **kw):
        d.ellipse([x0 * S, y0 * S, x1 * S, y1 * S], **kw)

    def R(x0, y0, x1, y1, r=0, **kw):
        d.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius=r * S, **kw)

    def P(pts, **kw):
        d.polygon([(x * S, y * S) for x, y in pts], **kw)

    def L(pts, w, **kw):
        d.line([(x * S, y * S) for x, y in pts], width=int(w * S), joint="curve", **kw)

    cx = 350
    # shirt / shoulders
    R(110, 470, 590, 700, r=110, fill=SHIRT)
    rnd = random.Random(7)
    for _ in range(26):  # hibiscus print
        x, y = rnd.randint(130, 570), rnd.randint(490, 640)
        if abs(x - cx) < 60 and y < 560:
            continue
        c = rnd.choice([PINK, YELLOW, (255, 255, 255)])
        for a in range(5):
            ang = a * 2 * math.pi / 5
            E(x + 9 * math.cos(ang) - 7, y + 9 * math.sin(ang) - 7, x + 9 * math.cos(ang) + 7, y + 9 * math.sin(ang) + 7, fill=c)
        E(x - 4, y - 4, x + 4, y + 4, fill=YELLOW if c != YELLOW else PINK)
    # neck + open collar
    R(300, 420, 400, 510, r=30, fill=SKIN_D)
    P([(cx - 70, 470), (cx, 560), (cx + 70, 470)], fill=SKIN)
    P([(cx - 70, 470), (cx - 20, 540), (cx - 100, 520)], fill=(0, 132, 126))
    P([(cx + 70, 470), (cx + 20, 540), (cx + 100, 520)], fill=(0, 132, 126))
    L([(cx - 55, 482), (cx - 20, 525), (cx, 535), (cx + 20, 525), (cx + 55, 482)], 6, fill=(255, 200, 60))  # gold chain
    # ears
    E(205, 270, 245, 350, fill=SKIN_D)
    E(455, 270, 495, 350, fill=SKIN_D)
    # head
    E(220, 140, 480, 460, fill=SKIN)
    E(255, 380, 445, 470, fill=SKIN)  # jaw
    # hair: pompadour
    E(208, 85, 492, 245, fill=HAIR)
    E(230, 60, 440, 170, fill=HAIR)
    E(380, 70, 470, 150, fill=HAIR)
    P([(214, 200), (240, 300), (250, 200)], fill=HAIR)  # sideburns
    P([(486, 200), (460, 300), (450, 200)], fill=HAIR)
    L([(270, 105), (330, 82), (400, 90)], 5, fill=(70, 50, 80))  # shine
    # eyebrows (mood)
    brow = {"hype": (-14, -14), "pain": (10, -10), "calm": (0, 0), "deep": (6, 2)}[mood]
    # brow[0]: inner end offset, brow[1]: outer end offset (negative = up)
    L([(262, 262 + brow[1]), (330, 255 + brow[0])], 13, fill=HAIR)
    L([(370, 255 + brow[0]), (438, 262 + brow[1])], 13, fill=HAIR)
    # sunglasses
    for x0 in (252, 362):
        R(x0, 272, x0 + 88, 334, r=24, fill=PINK)
        R(x0 + 7, 279, x0 + 81, 327, r=19, fill=(36, 10, 60))
        L([(x0 + 18, 318), (x0 + 50, 286)], 6, fill=CYAN)
    R(336, 290, 366, 300, r=4, fill=PINK)
    # nose
    L([(350, 330), (338, 372), (356, 376)], 6, fill=SKIN_D)
    # mouth
    my = 410
    if mouth <= 0:
        if mood == "hype":
            d.arc([305 * S, (my - 30) * S, 395 * S, (my + 18) * S], 20, 160, fill=(120, 40, 50), width=7 * S)
        elif mood == "pain":
            d.arc([310 * S, (my + 2) * S, 390 * S, (my + 40) * S], 200, 340, fill=(120, 40, 50), width=7 * S)
        else:
            L([(318, my), (382, my)], 7, fill=(120, 40, 50))
    else:
        h = 8 + mouth * 9
        wdt = 34 + mouth * 2
        E(cx - wdt, my - h / 2, cx + wdt, my + h / 2, fill=(90, 20, 40))
        R(cx - wdt + 8, my - h / 2 + 1, cx + wdt - 8, my - h / 2 + 9, r=3, fill=WHITE)
        if mouth >= 3:
            E(cx - 18, my + h / 2 - 14, cx + 18, my + h / 2 - 2, fill=(220, 90, 110))
    # goatee
    E(334, 448, 366, 470, fill=HAIR)
    out = im.resize((RICO_W, RICO_H), Image.LANCZOS)
    _rico_cache[key] = out
    return out


# ---------------------------------------------------------------- static layers

def vgrad(w, h, stops):
    col = Image.new("RGB", (1, h))
    px = col.load()
    for y in range(h):
        t = y / (h - 1)
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if p0 <= t <= p1:
                px[0, y] = mix(c0, c1, (t - p0) / (p1 - p0 or 1))
                break
    return col.resize((w, h))


_glow_cache = {}


def glow_rect(base, box, color, r=28, width=5, blur=16, fill=None):
    """Neon rounded box. The blurred layer is built once per (box, color) and pasted as a crop."""
    key = (box, color, r, width, blur, fill)
    if key not in _glow_cache:
        m = blur * 3
        w, h = box[2] - box[0] + 2 * m, box[3] - box[1] + 2 * m
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        inner = (m, m, w - m, h - m)
        ImageDraw.Draw(layer).rounded_rectangle(inner, radius=r, outline=color + (255,), width=width + 6)
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
        top = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        top.alpha_composite(layer)
        top.alpha_composite(layer)
        dd = ImageDraw.Draw(top)
        if fill:
            dd.rounded_rectangle(inner, radius=r, fill=fill + (255,))
        dd.rounded_rectangle(inner, radius=r, outline=color + (255,), width=width)
        _glow_cache[key] = (top, (box[0] - m, box[1] - m))
    top, pos = _glow_cache[key]
    base.alpha_composite(top, pos)


def make_background():
    bg = vgrad(W, H, [(0, NIGHT_TOP), (0.42, NIGHT_MID), (0.52, (110, 24, 110)), (0.53, (20, 8, 40)), (1, (8, 4, 20))]).convert("RGBA")
    d = ImageDraw.Draw(bg)
    # window skyline behind the wall screen
    rnd = random.Random(3)
    x = 0
    while x < W:
        bw, bh = rnd.randint(50, 120), rnd.randint(120, 380)
        d.rectangle([x, 960 - bh, x + bw, 960], fill=(30, 10, 54))
        for wy in range(960 - bh + 14, 950, 26):
            for wx in range(x + 10, x + bw - 10, 22):
                if rnd.random() < 0.35:
                    d.rectangle([wx, wy, wx + 8, wy + 12], fill=rnd.choice([(255, 120, 200), (90, 220, 255), (255, 210, 120)]))
        x += bw + rnd.randint(4, 20)
    # floor grid under the desk
    for i in range(14):
        y = 1010 + int((i / 13) ** 1.8 * 910)
        d.line([0, y, W, y], fill=(80, 20, 110), width=2)
    for i in range(-10, 21):
        d.line([W / 2 + i * 30, 1010, W / 2 + i * 220, H], fill=(80, 20, 110), width=2)
    return bg


def make_desk():
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rectangle([0, 905, W, 1000], fill=(34, 14, 58))
    d.rectangle([0, 897, W, 910], fill=PINK)
    # keyboard + mug
    d.rounded_rectangle([330, 918, 750, 962], radius=10, fill=(20, 8, 36))
    for k in range(12):
        d.rectangle([345 + k * 33, 928, 370 + k * 33, 950], fill=(60, 30, 90))
    d.rounded_rectangle([830, 850, 905, 935], radius=12, fill=WHITE)
    d.arc([890, 870, 935, 915], 270, 90, fill=WHITE, width=10)
    d.text((867, 892), "RICO", font=font("black", 18), fill=PINK, anchor="mm")
    return lay


# ---------------------------------------------------------------- per-frame pieces

def wall_screen(img, t, mood):
    """Decorative scrolling candles behind Rico (ambience, not data)."""
    box = (70, 250, 1010, 700)
    col = MOOD_COLOR[mood]
    glow_rect(img, box, col, r=26, width=4, blur=14, fill=(10, 6, 26))
    d = ImageDraw.Draw(img)
    rnd = random.Random(11)
    drift = {"hype": -1.1, "pain": 1.1, "calm": 0, "deep": 0}[mood]
    shift = (t * 40) % 34
    y = 480
    for k in range(32):
        o = y + rnd.uniform(-22, 22)
        y = o + drift * 7 + rnd.uniform(-14, 14)
        y = min(650, max(300, y))
        x = box[0] + 20 + k * 34 - shift
        if x < box[0] + 10 or x > box[2] - 30:
            continue
        up = y < o
        c = mix((10, 6, 26), GREEN if up else RED, 0.45)
        d.line([x + 9, min(o, y) - 16, x + 9, max(o, y) + 16], fill=c, width=3)
        d.rectangle([x, min(o, y), x + 18, max(o, y) + 2], fill=c)


def header(img):
    d = ImageDraw.Draw(img)
    d.text((W // 2, 105), "RICO NEON", font=font("black", 74), fill=WHITE, anchor="mm",
           stroke_width=4, stroke_fill=PINK)
    d.rounded_rectangle([300, 155, 780, 205], radius=25, fill=(0, 0, 0))
    d.text((W // 2, 181), "MY REAL TRADES · NOT ADVICE", font=font("bold", 30), fill=CYAN, anchor="mm")


def captions(img, words, t):
    """Show the current 3-word chunk, active word in yellow."""
    if not words:
        return
    idx = max([i for i, w in enumerate(words) if w["t"] <= t + 0.05] or [-1])
    if idx < 0 or t > words[idx]["t"] + words[idx]["d"] + 0.9:
        return
    start = idx - (idx % 3)
    # keep chunks inside one scene
    while start < idx and words[start]["scene"] != words[idx]["scene"]:
        start += 1
    chunk = [w for w in words[start:start + 3] if w["scene"] == words[idx]["scene"]]
    f = font("black", 88)
    d = ImageDraw.Draw(img)
    texts = [w["w"].upper() for w in chunk]
    widths = [d.textlength(s, font=f) for s in texts]
    space = 26
    total = sum(widths) + space * (len(texts) - 1)
    scale_cap = 1.0 if total < W - 80 else (W - 80) / total
    if scale_cap < 1:
        f = font("black", int(88 * scale_cap))
        widths = [d.textlength(s, font=f) for s in texts]
        total = sum(widths) + space * (len(texts) - 1)
    x = (W - total) / 2
    for w, s, wd in zip(chunk, texts, widths):
        active = w is words[idx]
        pop = 1.0
        d.text((x, 1060), s, font=f, fill=YELLOW if active else WHITE, anchor="lm",
               stroke_width=9, stroke_fill=(0, 0, 0))
        x += wd + space


def panel_box(img, color):
    box = (60, 1130, 1020, 1580)
    glow_rect(img, box, color, r=34, width=5, blur=18, fill=(12, 6, 28))
    return box


def money(v, cents=True):
    s = f"${abs(v):,.2f}" if cents else f"${abs(v):,.0f}"
    return ("-" if v < 0 else "+") + s


def draw_stat(img, v, p, mood):
    box = panel_box(img, MOOD_COLOR[mood])
    d = ImageDraw.Draw(img)
    items = v["items"]
    n = len(items)
    rowh = (box[3] - box[1] - 60) / n
    for i, it in enumerate(items):
        t0 = i / n * 0.8
        k = ease((p - t0) / 0.25)
        if k <= 0:
            continue
        y = box[1] + 30 + rowh * (i + 0.5)
        col = COLORS.get(it.get("color", "white"), WHITE)
        val = it["value"] * k
        fmt = it.get("fmt", "{:,.0f}")
        txt = money(val, it.get("cents", True)) if fmt == "money" else fmt.format(val)
        size = int(min(150, rowh * 0.62))
        d.text((box[0] + 50, y), it["label"], font=font("bold", 44), fill=(200, 190, 230), anchor="lm")
        d.text((box[2] - 50, y), txt, font=font("black", size), fill=col, anchor="rm",
               stroke_width=3, stroke_fill=(0, 0, 0))


def draw_trade(img, v, p, mood):
    win = v["pnl"] >= 0
    col = GREEN if win else RED
    box = panel_box(img, col)
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    d.text((x0 + 45, y0 + 55), v["date"], font=font("bold", 40), fill=(200, 190, 230), anchor="lm")
    d.text((x1 - 45, y0 + 55), v["symbol"] + " " + v["what"], font=font("black", 50), fill=WHITE, anchor="rm")
    # entry / exit rows
    rows = [(v.get("in_label", "IN"), v["entry"]), (v.get("out_label", "OUT"), v["exit"])]
    for i, (lab, price) in enumerate(rows):
        k = ease((p - 0.08 - i * 0.22) / 0.15)
        if k <= 0:
            continue
        yy = y0 + 150 + i * 95
        d.rounded_rectangle([x0 + 40, yy - 38, x0 + 230, yy + 38], radius=18, fill=(40, 20, 70))
        d.text((x0 + 135, yy), lab, font=font("black", 40), fill=CYAN, anchor="mm")
        d.text((x0 + 260, yy), f"${price:.2f}", font=font("black", 70), fill=WHITE, anchor="lm")
    # P&L counter
    kp = ease((p - 0.5) / 0.3)
    if kp > 0:
        val = v["pnl"] * kp
        d.text((W // 2, y1 - 125), money(val, cents=False), font=font("black", 140), fill=col, anchor="mm",
               stroke_width=4, stroke_fill=(0, 0, 0))
        if "pct" in v and kp >= 1:
            d.text((W // 2, y1 - 38), f"{v['pct']:+.0f}% on this trade", font=font("bold", 38), fill=col, anchor="mm")


def draw_compare(img, v, p, mood):
    box = panel_box(img, MOOD_COLOR[mood])
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    d.text((W // 2, y0 + 55), v["title"], font=font("bold", 40), fill=(200, 190, 230), anchor="mm")
    mx = max(abs(r["value"]) for r in v["rows"])
    for i, r in enumerate(v["rows"]):
        k = ease((p - i * 0.3) / 0.3)
        if k <= 0:
            continue
        yy = y0 + 150 + i * 130
        col = COLORS[r["color"]]
        d.text((x0 + 45, yy), r["label"], font=font("black", 40), fill=WHITE, anchor="lm")
        bx0, bx1 = x0 + 300, x1 - 250
        bw = (bx1 - bx0) * abs(r["value"]) / mx * k
        d.rounded_rectangle([bx0, yy - 34, bx0 + max(bw, 20), yy + 34], radius=16, fill=col)
        d.text((bx0 + bw + 18, yy), money(r["value"] * k), font=font("black", 50), fill=col, anchor="lm")
    if v.get("note") and p > 0.7:
        d.text((W // 2, y1 - 50), v["note"], font=font("bold", 42), fill=YELLOW, anchor="mm")


def draw_line(img, v, p, mood):
    box = panel_box(img, MOOD_COLOR[mood])
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    d.text((W // 2, y0 + 50), v["title"], font=font("bold", 40), fill=(200, 190, 230), anchor="mm")
    pts = v["points"]
    lo, hi = min(pts + [0]), max(pts + [0])
    pad = (hi - lo) * 0.1 or 1
    lo, hi = lo - pad, hi + pad
    gx0, gx1, gy0, gy1 = x0 + 50, x1 - 50, y0 + 100, y1 - 90

    def Y(val):
        return gy1 - (val - lo) / (hi - lo) * (gy1 - gy0)
    d.line([gx0, Y(0), gx1, Y(0)], fill=(90, 80, 120), width=2)
    n = max(2, int(len(pts) * ease(p / 0.8)))
    xy = [(gx0 + i * (gx1 - gx0) / (len(pts) - 1), Y(pts[i])) for i in range(n)]
    for a, b in zip(xy, xy[1:]):
        d.line([a, b], fill=GREEN if b[1] <= Y(0) else RED, width=8)
    last = pts[n - 1]
    d.ellipse([xy[-1][0] - 12, xy[-1][1] - 12, xy[-1][0] + 12, xy[-1][1] + 12], fill=WHITE)
    d.text((W // 2, y1 - 45), money(last), font=font("black", 60), fill=GREEN if last >= 0 else RED, anchor="mm")


def wrap(d, text, f, maxw):
    lines, cur = [], ""
    for w in text.split():
        trial = (cur + " " + w).strip()
        if d.textlength(trial, font=f) <= maxw:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


def draw_lesson(img, v, p, mood):
    box = panel_box(img, YELLOW)
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    d.rounded_rectangle([W // 2 - 150, y0 - 32, W // 2 + 150, y0 + 32], radius=30, fill=YELLOW)
    d.text((W // 2, y0), v.get("tag", "LESSON"), font=font("black", 42), fill=(20, 8, 30), anchor="mm")
    lines = v["lines"]
    f = font("black", 60)
    blocks = [wrap(d, ln, f, x1 - x0 - 100) for ln in lines]
    if sum(len(b) for b in blocks) > 4:
        f = font("black", 52)
        blocks = [wrap(d, ln, f, x1 - x0 - 100) for ln in lines]
    n_rows = sum(len(b) for b in blocks)
    gap = 34
    yy = (y0 + y1) / 2 - (n_rows * 70 + gap * (len(blocks) - 1)) / 2 + 25
    for i, sub in enumerate(blocks):
        k = ease((p - i * 0.22) / 0.18)
        for s_ in sub:
            if k > 0:
                d.text((W // 2, yy), s_, font=f, fill=YELLOW if i == len(blocks) - 1 else WHITE, anchor="mt")
            yy += 70
        yy += gap


def draw_quote(img, v, p, mood, words, t, scene_idx):
    shade = Image.new("RGBA", (W, H), (6, 2, 18, int(150 * ease(p / 0.1))))
    img.alpha_composite(shade)
    d = ImageDraw.Draw(img)
    f = font("serif", 76)
    lines = wrap(d, "“" + v["text"] + "”", f, W - 160)
    spoken = [w for w in words if w["scene"] == scene_idx and w["t"] <= t]
    n_words_total = len(v["text"].split())
    n_show = len(spoken) if spoken else 0
    if p > 0.95:
        n_show = n_words_total
    shown = 0
    ytop = 1180 - len(lines) * 45
    for i, ln in enumerate(lines):
        out = []
        for w in ln.split():
            if shown < n_show + 1:
                out.append(w)
            shown += 1
        if out:
            txt = " ".join(out)
            key = ("q", txt)
            if key not in _glow_cache:
                layer = Image.new("RGBA", (W, 160), (0, 0, 0, 0))
                ImageDraw.Draw(layer).text((W // 2, 80), txt, font=f, fill=(190, 120, 255, 255), anchor="mm")
                layer = layer.filter(ImageFilter.GaussianBlur(10))
                ImageDraw.Draw(layer).text((W // 2, 80), txt, font=f, fill=WHITE, anchor="mm")
                _glow_cache[key] = layer
            img.alpha_composite(_glow_cache[key], (0, int(ytop + i * 92 - 80)))
    if p > 0.85 and v.get("by"):
        d.text((W // 2, ytop + len(lines) * 92 + 30), "— " + v["by"], font=font("bold", 40), fill=(200, 180, 240), anchor="mm")


def draw_outro(img, v, p, mood):
    box = panel_box(img, PINK)
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    k = ease(p / 0.3)
    d.text((W // 2, y0 + 110), v.get("big", "FOLLOW"), font=font("black", int(130 * (0.6 + 0.4 * k))), fill=PINK,
           anchor="mm", stroke_width=4, stroke_fill=WHITE)
    d.text((W // 2, y0 + 230), v.get("small", "one real trade lesson every day"), font=font("bold", 46), fill=WHITE, anchor="mm")
    d.text((W // 2, y1 - 80), "Real results. Education only.", font=font("medium", 36), fill=(200, 190, 230), anchor="mm")
    d.text((W // 2, y1 - 38), "Not financial advice. Trading can lose money.", font=font("medium", 36), fill=(200, 190, 230), anchor="mm")


# ---------------------------------------------------------------- main render

def render(ep, out_path, work=None):
    work = work or tempfile.mkdtemp()
    scenes = ep["scenes"]
    voice = ep.get("voice", "en-US-BrianMultilingualNeural")
    wav, timeline, words, total = build_audio(scenes, voice, work)
    n = int(total * FPS)
    loud = loudness_per_frame(wav, n)
    bg = make_background()
    desk = make_desk()
    head = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    header(head)

    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out_path],
        stdin=subprocess.PIPE)
    for fi in range(n):
        t = fi / FPS
        si = 0
        for i, (a, b) in enumerate(timeline):
            if t >= a - 0.35:
                si = i
        a, b = timeline[si]
        p = max(0.0, min(1.0, (t - a) / max(0.1, b - a)))
        sc = scenes[si]
        mood = sc.get("mood", "calm")
        img = bg.copy()
        wall_screen(img, t, mood)
        speaking = a <= t <= b
        lv = loud[fi] if speaking else 0
        mouth = 0 if lv < 0.12 else min(5, 1 + int(lv * 5))
        bob = math.sin(t * 2.2) * 6 + (lv * 8 if speaking else 0)
        sway = math.sin(t * 1.3) * 5
        r = rico(mouth, mood)
        img.alpha_composite(r, (int(W / 2 - RICO_W / 2 + sway), int(330 + bob)))
        img.alpha_composite(desk, (0, 840), (0, 840, W, 1000))
        img.alpha_composite(head, (0, 40), (0, 40, W, 220))
        vis = sc.get("visual", {})
        typ = vis.get("type")
        if typ == "quote":
            draw_quote(img, vis, p, mood, words, t, si)
        else:
            {"stat": draw_stat, "trade": draw_trade, "compare": draw_compare, "line": draw_line,
             "lesson": draw_lesson, "outro": draw_outro}.get(typ, lambda *x: None)(img, vis, p, mood)
            captions(img, words, t)
        ff.stdin.write(img.convert("RGB").tobytes())
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    return out_path


if __name__ == "__main__":
    ep = json.load(open(sys.argv[1]))
    render(ep, sys.argv[2])
    print("wrote", sys.argv[2])
