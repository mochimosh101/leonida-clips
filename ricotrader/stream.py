"""Stream layout: Rica's webcam on top (1/4 of the screen), her Desk Trader screen below (3/4).

Episode JSON is the same as render.py plus optional:
  "layout": "stream",
  "cam_video": "path/to/rica-cam.mp4",   # realistic talking-head clip (AI host); placeholder if missing
  "tiles": [{"label": "TODAY", "value": 43.37, "fmt": "money"}, ...],
  "log": [{"time": "07:11", "sym": "QQQ 669P", "pnl": 244}, ...]
"""
import math
import os
import subprocess

from PIL import Image, ImageDraw

from ricotrader import render as R
from ricotrader.render import (CYAN, FPS, GREEN, H, PINK, RED, W, WHITE, YELLOW, font, glow_rect, money, vgrad)

CAM_H = 480                     # 1080x480 = exactly 1/4 of 1080x1920
APP_BG = (11, 13, 22)
APP_PANEL = (20, 23, 36)
APP_LINE = (40, 44, 64)
MUTED = (140, 146, 170)


def cam_frames(path, n, work):
    """Decode the webcam clip to 1080x480 frames (scaled + center-cropped), looping if short."""
    if not path or not os.path.exists(path):
        return None
    raw = os.path.join(work, "cam.rgb")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", path, "-frames:v", str(n),
                    "-vf", f"fps={FPS},scale={W}:-2:force_original_aspect_ratio=increase,crop={W}:{CAM_H}",
                    "-f", "rawvideo", "-pix_fmt", "rgb24", raw], check=True)
    return raw


SKIN_F = (236, 186, 150)
SKIN_FD = (206, 150, 116)
HAIR_F = (40, 22, 36)
HOODIE = (112, 52, 176)
RICA_W, RICA_H, SS = 600, 480, 2
_rica_cache = {}
_room = []


def rica(mouth, mood, blink):
    """Cartoon Rica (head and shoulders), drawn at 2x and scaled down. Cached per pose."""
    key = (mouth, mood, blink)
    if key in _rica_cache:
        return _rica_cache[key]
    im = Image.new("RGBA", (RICA_W * SS, RICA_H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def E(x0, y0, x1, y1, **kw):
        d.ellipse([x0 * SS, y0 * SS, x1 * SS, y1 * SS], **kw)

    def Rr(x0, y0, x1, y1, r=0, **kw):
        d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], radius=r * SS, **kw)

    def P(pts, **kw):
        d.polygon([(x * SS, y * SS) for x, y in pts], **kw)

    def L(pts, w, **kw):
        d.line([(x * SS, y * SS) for x, y in pts], width=int(w * SS), joint="curve", **kw)

    def A(box, a0, a1, w, **kw):
        d.arc([v * SS for v in box], a0, a1, width=int(w * SS), **kw)

    # long hair behind
    E(150, 50, 450, 330, fill=HAIR_F)
    Rr(150, 180, 450, 470, r=60, fill=HAIR_F)
    # hoodie + strings
    Rr(80, 360, 520, 620, r=120, fill=HOODIE)
    P([(230, 360), (300, 430), (370, 360)], fill=(86, 36, 140))
    L([(272, 392), (266, 470)], 5, fill=WHITE)
    L([(328, 392), (334, 470)], 5, fill=WHITE)
    # neck + head
    Rr(262, 290, 338, 380, r=26, fill=SKIN_FD)
    E(205, 80, 395, 330, fill=SKIN_F)
    # hair over the shoulders, front
    P([(160, 220), (205, 200), (225, 470), (150, 470)], fill=HAIR_F)
    P([(440, 220), (395, 200), (375, 470), (450, 470)], fill=HAIR_F)
    # bangs, swept
    P([(200, 175), (215, 95), (300, 62), (395, 100), (402, 175), (360, 120), (300, 140), (250, 125)], fill=HAIR_F)
    L([(250, 90), (300, 72), (350, 84)], 6, fill=(255, 80, 180))  # pink streak
    L([(410, 190), (430, 300), (425, 400)], 6, fill=(255, 80, 180))
    # headset
    A((185, 30, 415, 260), 190, 350, 14, fill=(30, 30, 44))
    for x0 in (178, 386):
        E(x0, 175, x0 + 40, 250, fill=(30, 30, 44))
        E(x0 + 6, 182, x0 + 34, 243, outline=CYAN, width=4 * SS)
    L([(200, 245), (225, 300), (262, 312)], 6, fill=(30, 30, 44))
    E(256, 304, 274, 322, fill=(30, 30, 44))
    # eyebrows (mood)
    br = {"hype": (-10, -12), "pain": (-9, 5), "calm": (0, 0), "deep": (-3, 3), "wow": (-18, -20), "ugh": (-12, 8)}[mood]
    L([(242, 176 + br[1]), (282, 170 + br[0])], 6, fill=HAIR_F)
    L([(318, 170 + br[0]), (358, 176 + br[1])], 6, fill=HAIR_F)
    # eyes
    for cx in (262, 338):
        if mood == "wow" and not blink:           # squeezed happy eyes  ^ ^
            A((cx - 22, 192, cx + 22, 232), 200, 340, 7, fill=HAIR_F)
        elif blink:
            A((cx - 22, 190, cx + 22, 214), 10, 170, 5, fill=HAIR_F)
        else:
            E(cx - 22, 188, cx + 22, 222, fill=WHITE)
            E(cx - 12, 192, cx + 12, 218, fill=(90, 50, 30))
            E(cx - 6, 198, cx + 6, 212, fill=(20, 10, 10))
            E(cx + 2, 196, cx + 8, 202, fill=WHITE)
            A((cx - 24, 184, cx + 24, 222), 195, 345, 6, fill=HAIR_F)  # lashes
            L([(cx + 18, 190), (cx + 28, 182)], 4, fill=HAIR_F)
            if mood == "ugh":                      # heavy, half-closed lids
                Rr(cx - 26, 182, cx + 26, 204, r=8, fill=SKIN_F)
                L([(cx - 24, 204), (cx + 24, 204)], 5, fill=HAIR_F)
    # blush + nose
    E(228, 236, 262, 252, fill=(246, 150, 150))
    E(338, 236, 372, 252, fill=(246, 150, 150))
    L([(300, 220), (294, 250), (304, 253)], 4, fill=SKIN_FD)
    # mouth
    my, lip = 282, (210, 60, 100)
    if mouth <= 0:
        if mood == "wow":
            P([(266, my - 6), (334, my - 6), (322, my + 22), (300, my + 30), (278, my + 22)], fill=(110, 24, 50))
            Rr(272, my - 6, 328, my + 2, r=3, fill=WHITE)
        elif mood == "ugh":
            L([(276, my + 10), (300, my + 4), (324, my + 12)], 6, fill=lip)
        elif mood == "hype":
            A((270, my - 22, 330, my + 10), 20, 160, 6, fill=lip)
        elif mood == "pain":
            A((274, my - 2, 326, my + 22), 200, 340, 6, fill=lip)
        else:
            A((278, my - 10, 322, my + 6), 30, 150, 6, fill=lip)
    else:
        h = 6 + mouth * 6
        w = 22 + mouth * 1.5
        E(300 - w, my - h / 2, 300 + w, my + h / 2, fill=(110, 24, 50), outline=lip, width=4 * SS)
        Rr(300 - w + 7, my - h / 2 + 3, 300 + w - 7, my - h / 2 + 9, r=3, fill=WHITE)
    out = im.resize((RICA_W, RICA_H), Image.LANCZOS)
    _rica_cache[key] = out
    return out


def bedroom():
    if _room:
        return _room[0]
    img = vgrad(W, CAM_H, [(0, (40, 16, 62)), (0.75, (70, 26, 92)), (1, (36, 14, 50))]).convert("RGBA")
    d = ImageDraw.Draw(img)
    # window with night city
    d.rectangle([40, 70, 300, 330], fill=(12, 10, 40))
    import random
    rnd = random.Random(5)
    for _ in range(9):
        x, h = rnd.randint(40, 280), rnd.randint(60, 200)
        d.rectangle([x, 330 - h, x + rnd.randint(20, 45), 330], fill=(30, 18, 64))
    for _ in range(40):
        x, y = rnd.randint(48, 292), rnd.randint(200, 325)
        d.rectangle([x, y, x + 4, y + 6], fill=rnd.choice([(255, 200, 120), (120, 220, 255)]))
    d.ellipse([220, 90, 270, 140], fill=(250, 240, 210))
    d.rectangle([40, 70, 300, 330], outline=(90, 60, 120), width=10)
    d.line([170, 70, 170, 330], fill=(90, 60, 120), width=6)
    # bed with pillows (right)
    d.rounded_rectangle([760, 300, 1100, 520], radius=30, fill=(150, 70, 160))
    d.rounded_rectangle([790, 260, 920, 330], radius=30, fill=(230, 210, 240))
    d.rounded_rectangle([930, 270, 1060, 335], radius=30, fill=(255, 150, 200))
    # plant
    d.rectangle([330, 360, 380, 470], fill=(200, 110, 70))
    for k in range(7):
        ang = -1.3 + k * 0.45
        d.ellipse([355 + 70 * math.sin(ang) - 22, 320 - 50 * math.cos(ang) - 12,
                   355 + 70 * math.sin(ang) + 22, 320 - 50 * math.cos(ang) + 12], fill=(60, 170, 110))
    # LED strip + neon sign
    glow_rect(img, (0, 14, W, 22), PINK, r=4, width=6, blur=10)
    sign = Image.new("RGBA", (360, 120), (0, 0, 0, 0))
    ImageDraw.Draw(sign).text((180, 60), "stay green", font=font("serif", 56), fill=GREEN + (255,), anchor="mm")
    from PIL import ImageFilter
    img.alpha_composite(sign.filter(ImageFilter.GaussianBlur(8)), (720, 90))
    img.alpha_composite(sign.filter(ImageFilter.GaussianBlur(8)), (720, 90))
    ImageDraw.Draw(img).text((900, 150), "stay green", font=font("serif", 56), fill=(210, 255, 220), anchor="mm")
    # desk edge with a monitor glow
    d.rectangle([0, 455, W, CAM_H], fill=(24, 12, 34))
    _room.append(img)
    return img


def _blink(t):
    """Irregular blinking (2-5 s apart, sometimes a double blink), like a person, not a metronome."""
    n = int(t / 0.9)
    for k in (n, n - 1):
        h = (k * 2654435761) % 1000 / 1000
        if h < 0.28:
            start = k * 0.9 + h
            if start <= t < start + 0.11 or (h < 0.06 and start + 0.22 <= t < start + 0.32):
                return True
    return False


def cam_placeholder(t, lv, mood="calm", since=9.0):
    """Cartoon webcam: Rica in her bedroom, lip-synced, blinking, and reacting at the start of each line:
    a happy bounce for hype, a slump and head shake for pain, a slow lean in for deep."""
    img = bedroom().copy()
    mouth = 0 if lv < 0.12 else min(5, 1 + int(lv * 5))
    blink = _blink(t)
    bob = math.sin(t * 1.7) * 3 + lv * 7 + math.sin(t * 0.37) * 3
    sway = math.sin(t * 0.9) * 5 + math.sin(t * 2.3) * 2
    e = math.exp(-3.5 * max(0.0, since))
    if mood in ("hype", "wow"):
        bob -= (44 if mood == "wow" else 28) * e * abs(math.sin(since * 11))
    elif mood in ("pain", "ugh"):
        bob += 14 * (1 - e) * math.exp(-0.6 * max(0.0, since))
        sway += 16 * e * math.sin(since * 17)
    elif mood == "deep":
        bob += 8 * min(1.0, since / 1.5)
    img.alpha_composite(rica(mouth, mood, blink), (int(W / 2 - RICA_W / 2 + sway), int(14 + bob)))
    # cyan monitor light on the lower frame
    return img


def cam_overlay(img):
    d = ImageDraw.Draw(img)
    d.ellipse([28, 30, 50, 52], fill=RED)
    d.text((62, 41), "RICA", font=font("black", 34), fill=WHITE, anchor="lm", stroke_width=3, stroke_fill=(0, 0, 0))
    d.rounded_rectangle([W - 250, 22, W - 24, 62], radius=20, fill=(0, 0, 0))
    d.text((W - 137, 42), "MY REAL TRADES", font=font("bold", 24), fill=CYAN, anchor="mm")
    d.line([0, CAM_H - 2, W, CAM_H - 2], fill=PINK, width=4)


def app_chrome(ep):
    """Static Desk Trader window: top bar, tiles frame, log frame."""
    img = Image.new("RGBA", (W, H), APP_BG + (255,))
    d = ImageDraw.Draw(img)
    y = CAM_H
    d.rectangle([0, y, W, y + 78], fill=(16, 18, 30))
    d.text((34, y + 39), "◆ DESK TRADER", font=font("black", 38), fill=WHITE, anchor="lm")
    date_txt = ep.get("date_label", ep.get("date", ""))
    lx = W - 34 - d.textlength(date_txt, font=font("bold", 28)) - 130
    d.ellipse([lx, y + 30, lx + 18, y + 48], fill=GREEN)
    d.text((lx + 28, y + 39), "LIVE", font=font("bold", 28), fill=GREEN, anchor="lm")
    d.text((W - 34, y + 39), ep.get("date_label", ep.get("date", "")), font=font("bold", 28), fill=MUTED, anchor="rm")
    x = 34
    for i, tab in enumerate(["Dashboard", "Trades", "Review", "Playbooks"]):
        d.text((x, y + 108), tab, font=font("bold", 28), fill=WHITE if i == 0 else MUTED, anchor="lm")
        if i == 0:
            d.rectangle([x, y + 128, x + d.textlength(tab, font=font("bold", 28)), y + 132], fill=CYAN)
        x += d.textlength(tab, font=font("bold", 28)) + 48
    d.line([0, y + 140, W, y + 140], fill=APP_LINE, width=2)
    d.text((W // 2, 1898), "Not financial advice", font=font("medium", 20), fill=(52, 56, 72), anchor="mm")
    return img


def screen_chrome(ep, y_screen_end):
    """Background for the screen-recording layout: dark area under the desktop view + footer."""
    img = Image.new("RGBA", (W, H), APP_BG + (255,))
    d = ImageDraw.Draw(img)
    d.line([0, y_screen_end, W, y_screen_end], fill=APP_LINE, width=3)
    tag = ep["screen"].get("tag", "")
    if tag:
        d.text((W // 2, 1845), tag, font=font("bold", 28), fill=CYAN, anchor="mm")
    d.text((W // 2, 1898), "Not financial advice", font=font("medium", 20), fill=(52, 56, 72), anchor="mm")
    return img


REACT_LEN = 1.8


def reaction_at(sc, t, a, b, fills):
    """Streamer-style reaction for this scene: starts on the order fill if there is one, else at 'at'."""
    rv = sc.get("react")
    if not rv:
        return 0, None
    t0 = fills[0] + 0.15 if fills else a + rv.get("at", 0.0) * (b - a)
    q = (t - t0) / REACT_LEN
    if 0 <= q < 1:
        return q, {**rv, "_t": t0}
    return 0, None


def punch(cam, q, rv):
    """Camera punch-in with a shake, a coloured flash and a big reaction word, like a streamer's webcam."""
    z = 1 + 0.16 * R.ease(q / 0.1) * (1 - R.ease((q - 0.72) / 0.28))
    sh = 14 * math.exp(-5 * q) * math.sin(q * 70)
    cw, chh = W / z, CAM_H / z
    x0 = (W - cw) / 2 + sh
    y0 = (CAM_H - chh) / 2 - sh * 0.4
    cam = cam.crop((int(x0), int(y0), int(x0 + cw), int(y0 + chh))).resize((W, CAM_H), Image.BILINEAR)
    col = R.COLORS.get(rv.get("color", "green"), GREEN)
    d = ImageDraw.Draw(cam)
    fl = int(255 * max(0.0, 1 - q / 0.35))
    if fl > 0:
        over = Image.new("RGBA", (W, CAM_H), col + (int(fl * 0.28),))
        cam.alpha_composite(over)
    d.rectangle([0, 0, W - 1, CAM_H - 1], outline=col, width=10)
    if rv.get("text"):
        k = R.ease(q / 0.12)
        size = int(96 * (0.5 + 0.5 * k) + 18 * max(0.0, 1 - abs(q - 0.12) / 0.12))
        layer = Image.new("RGBA", (W, CAM_H), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((W // 2, CAM_H - 90), rv["text"], font=font("black", size), fill=col,
                                   anchor="mm", stroke_width=8, stroke_fill=(0, 0, 0))
        layer = layer.rotate(-4 if rv.get("color") != "red" else 4, center=(W // 2, CAM_H - 90))
        cam.alpha_composite(layer)
    return cam


def filled_toast(img, y, q):
    """'Order filled' banner that slides down over the screen, like a trading app notification."""
    d = ImageDraw.Draw(img)
    k = R.ease(q / 0.15) * (1 - R.ease((q - 0.8) / 0.2))
    yy = y - 90 * (1 - k)
    d.rounded_rectangle([W / 2 - 250, yy, W / 2 + 250, yy + 76], radius=38, fill=(18, 24, 34), outline=GREEN, width=4)
    d.ellipse([W / 2 - 228, yy + 16, W / 2 - 184, yy + 60], fill=GREEN)
    d.text((W / 2 - 206, yy + 38), "✓", font=font("black", 30), fill=(10, 14, 20), anchor="mm")
    d.text((W / 2 - 165, yy + 38), "ORDER FILLED", font=font("black", 40), fill=WHITE, anchor="lm")


def pop(img, v, p, y):
    """Big number caption (e.g. +$28) that punches in at the start of a scene."""
    if not v:
        return
    d = ImageDraw.Draw(img)
    k = R.ease(p / 0.12)
    col = R.COLORS.get(v.get("color", ""), WHITE)
    text = v["text"]
    if v.get("count"):                    # live P&L ticking up like the app's position card
        a, b = v["count"]
        val = a + (b - a) * R.ease((p - 0.05) / 0.45)
        text = ("+$" if val >= 0 else "-$") + f"{abs(val):.0f}"
    size = int(130 * (0.7 + 0.3 * k) + 14 * max(0.0, 1 - abs(p - 0.1) / 0.1))
    d.text((W // 2, y), text, font=font("black", size), fill=col, anchor="mm", stroke_width=6, stroke_fill=(0, 0, 0))
    if v.get("sub"):
        d.text((W // 2, y + 95), v["sub"], font=font("bold", 40), fill=(200, 205, 225), anchor="mm",
               stroke_width=3, stroke_fill=(0, 0, 0))


def tiles(img, ep, t):
    items = ep.get("tiles", [])
    if not items:
        return
    d = ImageDraw.Draw(img)
    y0, y1 = CAM_H + 160, CAM_H + 300
    n = len(items)
    gw = (W - 60 - 20 * (n - 1)) / n
    for i, it in enumerate(items):
        x0 = 30 + i * (gw + 20)
        d.rounded_rectangle([x0, y0, x0 + gw, y1], radius=18, fill=APP_PANEL)
        d.text((x0 + 22, y0 + 34), it["label"], font=font("bold", 26), fill=MUTED, anchor="lm")
        v = it["value"] * R.ease(t / 1.2)
        fmt = it.get("fmt", "{:,.0f}")
        txt = money(v) if fmt == "money" else fmt.format(v)
        col = R.COLORS.get(it.get("color", ""), GREEN if (fmt == "money" and it["value"] >= 0) else
                           RED if fmt == "money" else WHITE)
        d.text((x0 + 22, y0 + 95), txt, font=font("black", 50), fill=col, anchor="lm")


def trade_log(img, ep, t):
    rows = ep.get("log", [])
    if not rows:
        return
    d = ImageDraw.Draw(img)
    y0 = 1430
    d.text((34, y0), "RECENT TRADES", font=font("bold", 26), fill=MUTED, anchor="lm")
    shift = (t * 18) % (len(rows) * 52)
    sym_x = 34 + max(d.textlength(r["time"], font=font("medium", 28)) for r in rows) + 30
    for k in range(len(rows) * 2):
        r = rows[k % len(rows)]
        y = y0 + 40 + k * 52 - shift
        if y < y0 + 22 or y > 1660:
            continue
        d.text((34, y), r["time"], font=font("medium", 28), fill=MUTED, anchor="lm")
        d.text((sym_x, y), r["sym"], font=font("bold", 28), fill=WHITE, anchor="lm")
        d.text((W - 34, y), money(r["pnl"]), font=font("bold", 28), fill=GREEN if r["pnl"] >= 0 else RED, anchor="rm")
    d.rectangle([0, 1680, W, 1860], fill=APP_BG)


def cursor(img, t, target):
    """A mouse pointer drifting toward the panel the host is talking about."""
    x = target[0] + math.sin(t * 0.9) * 120
    y = target[1] + math.cos(t * 1.3) * 60
    d = ImageDraw.Draw(img)
    pts = [(x, y), (x, y + 44), (x + 12, y + 33), (x + 22, y + 54), (x + 30, y + 50), (x + 20, y + 30), (x + 36, y + 30)]
    d.polygon(pts, fill=WHITE, outline=(0, 0, 0))


def render_stream(ep, out_path, work=None):
    import tempfile
    work = work or tempfile.mkdtemp()
    R.PANEL[:] = [40, CAM_H + 320, W - 40, CAM_H + 770]
    R.CAPTION_Y[0] = 520 + 820
    R.QUOTE_Y[0] = 1050
    scenes = ep["scenes"]
    voice = ep.get("voice", "en-US-AvaMultilingualNeural")
    wav, timeline, words, total = R.build_audio(scenes, voice, work)
    n = int(total * FPS)
    loud = R.loudness_per_frame(wav, n)
    # order-filled alerts: snap each fill to the nearest pause between words, so the alert doesn't talk over her
    fill_times, fill_times_by_scene = [], {}
    for i, sc in enumerate(scenes):
        a_, b_ = timeline[i]
        for f in sc.get("screen", {}).get("fills", []):
            want = a_ + f.get("at", 0.25) * (b_ - a_)
            ws = [w for w in words if w["scene"] == i]
            gaps = [(w1["t"] + w1["d"], w2["t"]) for w1, w2 in zip(ws, ws[1:])] + [(ws[-1]["t"] + ws[-1]["d"], b_)] if ws else []
            best = min(gaps, key=lambda g: abs(g[0] - want) - 0.6 * (g[1] - g[0]), default=(want, want))
            ft = best[0] + 0.05
            f["at"] = max(0.0, min(1.0, (ft - a_) / max(0.1, b_ - a_)))
            fill_times.append(ft)
            fill_times_by_scene.setdefault(i, []).append(ft)
    if fill_times and ep.get("fill_sound", True):
        wav = R.mix_sfx(wav, R.fill_sound(work), fill_times, work)
    screen = None
    if ep.get("screen"):
        from ricotrader.desktop import ScreenCam
        big = ep["screen"].get("big", False)
        SCR_H = 1000 if big else 608     # big: the screen fills most of the Short; numbers become pop captions
        screen = ScreenCam(ep, W, SCR_H)
        R.PANEL[:] = [40, CAM_H + SCR_H + 40, W - 40, CAM_H + SCR_H + 490]
        R.CAPTION_Y[0] = CAM_H + SCR_H + 290 if big else CAM_H + SCR_H + 580
        chrome = screen_chrome(ep, CAM_H + SCR_H)
    else:
        chrome = app_chrome(ep)
    cam_raw = cam_frames(ep.get("cam_video"), n, work)
    camf = open(cam_raw, "rb") if cam_raw else None

    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
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
        img = chrome.copy()
        lv = loud[fi] if a <= t <= b else 0
        if camf:
            cam = Image.frombytes("RGB", (W, CAM_H), camf.read(W * CAM_H * 3)).convert("RGBA")
        else:
            since = t - a
            for f_ in sc.get("screen", {}).get("fills", []):   # react again the moment the order fills
                ft = a + f_.get("at", 0.25) * (b - a)
                if t >= ft:
                    since = t - ft
            rq, rv = reaction_at(sc, t, a, b, fill_times_by_scene.get(si, []))
            face = rv.get("face", mood) if rv else mood
            cam = cam_placeholder(t, lv, face, since if not rv else (t - rv["_t"]))
            if rv:
                cam = punch(cam, rq, rv)
        img.alpha_composite(cam, (0, 0))
        cam_overlay(img)
        if screen:
            img.alpha_composite(screen.frame(scenes, si, p, t, timeline), (0, CAM_H))
            for ft in fill_times:
                if ft <= t < ft + 1.8:
                    filled_toast(img, CAM_H + 26, (t - ft) / 1.8)
            ImageDraw.Draw(img).line([0, CAM_H, W, CAM_H], fill=PINK, width=4)
        else:
            tiles(img, ep, t)
            trade_log(img, ep, t)
        vis = sc.get("visual", {})
        typ = vis.get("type")
        if screen and ep["screen"].get("big") and typ != "quote":
            pop(img, sc.get("pop"), p, CAM_H + SCR_H + 100)
            R.captions(img, words, t)
        elif typ == "quote":
            R.draw_quote(img, vis, p, mood, words, t, si)
        else:
            {"stat": R.draw_stat, "trade": R.draw_trade, "compare": R.draw_compare, "line": R.draw_line,
             "lesson": R.draw_lesson, "outro": R.draw_outro}.get(typ, lambda *x: None)(img, vis, p, mood)
            if not screen:
                cursor(img, t, (760, R.PANEL[1] + 200))
            R.captions(img, words, t)
        ff.stdin.write(img.convert("RGB").tobytes())
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    return out_path
