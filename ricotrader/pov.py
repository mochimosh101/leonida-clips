"""POV skit layout: "you walk away from a winning trade".

Rica's webcam on top, a light trading chart below with a live P&L bubble, all driven by a REAL trade's
price history (option marks from Desk Trader). She cheers at the top, leaves her desk, the trade slides
back while she's gone, it sells, and she comes back: "Guys... what happened?"

  python -m ricotrader.pov ricotrader/pov/fri-594p-walkaway.json out.mp4
"""
import asyncio
import math
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

from ricotrader import render as R
from ricotrader.render import FPS, GREEN, H, RED, W, WHITE, font
from ricotrader.stream import RICA_H, RICA_W, bedroom, punch, rica, filled_toast

CAM_H = 640
CHART_TOP = CAM_H
BG = (255, 255, 255)
GRID = (238, 240, 244)
AXIS_TXT = (120, 126, 140)
UP, DOWN = (8, 153, 129), (242, 54, 69)          # candle colours
BLUE = (41, 98, 255)

# beats (seconds)
T_SIG0, T_FILL = 0.3, 3.4           # waiting on the book's signal, then the buy fills
T_RISE0, T_PEAK = 3.9, 8.8          # price runs from entry to the high
T_LEAVE0, T_LEAVE1 = 9.4, 10.8      # she stands up and walks out
T_FALL1 = 14.4                      # price slides back; the exit fills here
T_BACK0, T_BACK1 = 14.8, 16.1       # she walks back in
T_SEE = 16.3                        # "Guys... what happened?"
T_END = 21.0
GRADES = ["D", "C", "B", "A", "A+"]
GRADE_T = [0.5, 1.2, 1.9, 2.5, 3.0]  # when each grade lights up (vague "how close to a trade" meter)


def ease(x):
    return R.ease(x)


def lerp(a, b, k):
    return a + (b - a) * k


def mark_index(t, n, peak_i):
    """How far through the real price history we are at time t."""
    if t < T_RISE0:
        return 0
    if t < T_PEAK:
        return int(lerp(0, peak_i, (t - T_RISE0) / (T_PEAK - T_RISE0)))
    if t < T_LEAVE1:
        return peak_i + int((t - T_PEAK) / (T_FALL1 - T_PEAK) * (n - 1 - peak_i) * 0.25)
    if t < T_FALL1:
        k0 = (T_LEAVE1 - T_PEAK) / (T_FALL1 - T_PEAK) * 0.25
        k = k0 + (1 - k0) * (t - T_LEAVE1) / (T_FALL1 - T_LEAVE1)
        return peak_i + int(k * (n - 1 - peak_i))
    return n - 1


# ---------------------------------------------------------------- webcam

def cam_frame(t, lv, face, blink):
    """Rica at her desk, or walking out / back in. Returns a 1080x640 webcam image."""
    room = bedroom().copy()
    x = W / 2 - RICA_W / 2 + math.sin(t * 0.9) * 5
    y = 14 + math.sin(t * 1.7) * 3 + lv * 7
    if T_LEAVE0 <= t < T_BACK1:
        if t < T_LEAVE1:                                   # stand up, then walk off to the right
            k = (t - T_LEAVE0) / (T_LEAVE1 - T_LEAVE0)
            y -= 110 * ease(k / 0.35)
            x += 900 * ease((k - 0.3) / 0.7)
            y += abs(math.sin(t * 9)) * -14 * (k > 0.3)
        elif t < T_BACK0:
            x = 99999                                     # empty room
        else:                                             # walk back in and sit down
            k = (t - T_BACK0) / (T_BACK1 - T_BACK0)
            x += 900 * (1 - ease(k / 0.7))
            y -= 110 * (1 - ease((k - 0.6) / 0.4))
            y += abs(math.sin(t * 9)) * -14 * (k < 0.7)
    if x < W:
        room.alpha_composite(rica(0 if lv < 0.12 else min(5, 1 + int(lv * 5)), face, blink), (int(x), int(y)))
    cam = room.resize((int(W * CAM_H / 480), CAM_H), Image.LANCZOS)
    off = (cam.width - W) // 2
    return cam.crop((off, 0, off + W, CAM_H))


class ClipCam:
    """Realistic webcam from a generated video clip. ep["cam_clip"] = {"file": path, "map": [[t, src_t], ...]}:
    output time t plays source time src_t, linearly in between (equal src_t = freeze, slower = slow-mo)."""

    def __init__(self, cfg, work):
        self.map = cfg["map"]
        self.dir = os.path.join(work, "camframes")
        os.makedirs(self.dir, exist_ok=True)
        info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                               "stream=r_frame_rate,width,height", "-of", "csv=p=0", cfg["file"]],
                              capture_output=True, text=True, check=True).stdout.strip().split(",")
        w, h, rate = int(info[0]), int(info[1]), info[2]
        a, b = rate.split("/")
        self.fps = float(a) / float(b)
        cw = int(w * CAM_H / h) // 2 * 2
        crop = cfg.get("crop", 0)                     # optional extra zoom (0..0.3)
        sw, sh = int(cw * (1 + crop)) // 2 * 2, int(CAM_H * (1 + crop)) // 2 * 2
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", cfg["file"], "-vf",
                        f"scale={sw}:{sh}:flags=lanczos,crop={W}:{CAM_H}:(iw-{W})/2:(ih-{CAM_H})/2*{cfg.get('ybias', 1)},"
                        "unsharp=5:5:0.6", "-q:v", "2", os.path.join(self.dir, "%05d.jpg")], check=True)
        self.n = len(os.listdir(self.dir))

    def src_t(self, t):
        m = self.map
        if t <= m[0][0]:
            return m[0][1]
        for (t0, s0), (t1, s1) in zip(m, m[1:]):
            if t <= t1:
                return s0 + (s1 - s0) * (t - t0) / max(1e-6, t1 - t0)
        return m[-1][1]

    def frame(self, t):
        i = min(self.n, max(1, int(self.src_t(t) * self.fps) + 1))
        return Image.open(os.path.join(self.dir, f"{i:05d}.jpg")).convert("RGB")


# ---------------------------------------------------------------- chart

class Chart:
    def __init__(self, ep):
        self.ep = ep
        m = ep["marks"]
        self.c = [(m[i], max(m[i:i + 3]), min(m[i:i + 3]), m[min(i + 2, len(m) - 1)]) for i in range(0, len(m), 2)]
        self.lo = min(min(m), ep["entry"]) - 0.12
        self.hi = max(m) + 0.14
        self.x0, self.x1 = 30, W - 150
        self.y0, self.y1 = CHART_TOP + 330, H - 150

    def py(self, p):
        return self.y1 - (p - self.lo) / (self.hi - self.lo) * (self.y1 - self.y0)

    def draw(self, img, idx, t, live=True):
        d = ImageDraw.Draw(img)
        d.rectangle([0, CHART_TOP, W, H], fill=BG)
        # grid + axis labels
        step = 0.1
        p = math.ceil(self.lo / step) * step
        while p < self.hi:
            y = self.py(p)
            d.line([0, y, self.x1, y], fill=GRID, width=2)
            d.text((self.x1 + 18, y), f"{p:.2f}", font=font("medium", 26), fill=AXIS_TXT, anchor="lm")
            p += step
        d.line([self.x1, CHART_TOP + 300, self.x1, H], fill=(225, 228, 234), width=2)
        n_show = idx // 2 + 1
        cw = (self.x1 - self.x0 - 40) / len(self.c)
        entry, last = self.ep["entry"], self.ep["marks"][idx]
        # position shading (profit green / loss red) from entry to the live price
        xs = self.x0 + 2 * cw
        xe = max(xs + 20, self.x0 + n_show * cw + 10)
        ye, yl = self.py(entry), self.py(last)
        ya, yb = int(min(ye, yl)), int(max(ye, yl)) + 1
        shade = Image.new("RGBA", (int(xe - xs) + 1, yb - ya + 1),
                          (8, 153, 129, 46) if last >= entry else (242, 54, 69, 46))
        if live:
            img.alpha_composite(shade, (int(xs), ya))
        d = ImageDraw.Draw(img)
        for i in range(n_show):
            o, hi_, lo_, c = self.c[i]
            if i == n_show - 1:                               # the live candle wiggles a little
                c = self.ep["marks"][idx] + math.sin(t * 9) * 0.004
                hi_, lo_ = max(hi_, c, o), min(lo_, c, o)
            x = self.x0 + i * cw
            col = UP if c >= o else DOWN
            d.line([x + cw / 2, self.py(hi_), x + cw / 2, self.py(lo_)], fill=col, width=2)
            d.rectangle([x + 1, self.py(max(o, c)), x + cw - 1, self.py(min(o, c)) + 1], fill=col)
        # live price tag on the axis
        col = UP if last >= entry else DOWN
        if not live:
            col = (120, 126, 140)
        else:
            # entry line, LONG tag and the BUY fill marker
            for x in range(int(xs), self.x1, 18):
                d.line([x, ye, x + 9, ye], fill=(120, 126, 140), width=2)
            d.rounded_rectangle([xs - 40, ye + 16, xs + 52, ye + 52], radius=6, fill=UP)
            d.text((xs + 6, ye + 34), "LONG", font=font("black", 22), fill=WHITE, anchor="mm")
            k = ease((t - T_FILL) / 0.25)
            bx = self.x0 + cw / 2
            r = 16 + 10 * max(0, 1 - (t - T_FILL) / 0.4)
            d.polygon([(bx, ye - 14), (bx - r, ye - 14 - r * 1.4), (bx + r, ye - 14 - r * 1.4)], fill=UP)
            d.rounded_rectangle([bx - 22, ye - 96 - 20 * (1 - k), bx + 138, ye - 48 - 20 * (1 - k)], radius=8, fill=UP)
            d.text((bx + 58, ye - 72 - 20 * (1 - k)), f"BUY {entry:.2f}", font=font("black", 28), fill=WHITE, anchor="mm")
            if t >= T_FALL1:                              # the SELL marker where the exit filled
                sx = self.x0 + (len(self.c) - 0.5) * cw
                sy = self.py(self.ep["exit"])
                d.polygon([(sx, sy - 14), (sx - 16, sy - 36), (sx + 16, sy - 36)], fill=(230, 160, 20))
                d.rounded_rectangle([sx - 170, sy - 92, sx - 6, sy - 46], radius=8, fill=(230, 160, 20))
                d.text((sx - 88, sy - 69), f"SELL {self.ep['exit']:.2f}", font=font("black", 28), fill=WHITE, anchor="mm")
        d.rounded_rectangle([self.x1 + 4, yl - 20, W - 8, yl + 20], radius=5, fill=col)
        d.text(((self.x1 + W - 4) / 2, yl), f"{last:.2f}", font=font("black", 26), fill=WHITE, anchor="mm")
        return last

    def signal_card(self, img, t):
        """Vague 'waiting for the signal' meter: the book's grade climbs D -> A+, then it fires."""
        a = 1 - ease((t - T_FILL - 0.5) / 0.35)
        if a <= 0:
            return
        card = Image.new("RGBA", (800, 300), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        fired = t >= T_FILL - 0.15
        d.rounded_rectangle([0, 0, 799, 299], radius=26, fill=(255, 255, 255, 245),
                            outline=UP if fired else (205, 210, 220), width=4)
        d.text((40, 48), "TREND BOOK", font=font("black", 34), fill=(20, 22, 30), anchor="lm")
        dots = "." * (1 + int(t * 3) % 3)
        d.text((760, 48), "SIGNAL ✓" if fired else f"waiting for signal{dots}", font=font("bold", 30),
               fill=UP if fired else (120, 126, 140), anchor="rm")
        lit = sum(1 for g in GRADE_T if t >= g)
        for i, g in enumerate(GRADES):
            x = 40 + i * 146
            on = i < lit
            pulse = 1 + 0.12 * max(0, 1 - (t - GRADE_T[i]) / 0.25) if on else 1
            col = [(242, 54, 69), (240, 130, 40), (230, 190, 30), (120, 190, 60), UP][i] if on else (232, 235, 240)
            w2, h2 = 62 * pulse, 48 * pulse
            d.rounded_rectangle([x + 62 - w2, 150 - h2, x + 62 + w2, 150 + h2], radius=16, fill=col)
            d.text((x + 62, 150), g, font=font("black", 46), fill=WHITE if on else (170, 175, 186), anchor="mm")
        prog = min(1, max(0, (t - T_SIG0) / (GRADE_T[-1] + 0.2 - T_SIG0)))
        d.rounded_rectangle([40, 232, 760, 258], radius=13, fill=(236, 239, 244))
        d.rounded_rectangle([40, 232, 40 + max(26, 720 * ease(prog)), 258], radius=13, fill=UP if fired else BLUE)
        if a < 1:
            card.putalpha(card.getchannel("A").point(lambda v: int(v * a)))
        img.alpha_composite(card, (W // 2 - 400, int(CHART_TOP + 560 - 40 * (1 - a))))

    def bubble(self, img, pnl, closed):
        """The P&L pill that sits on the webcam edge, like a trading app's position tool."""
        d = ImageDraw.Draw(img)
        y = CAM_H
        txt = ("+" if pnl >= 0 else "-") + f"${abs(pnl):,.2f} USD"
        f = font("black", 40)
        tw = d.textlength(txt, font=f)
        lw = 120
        x0 = W / 2 - (lw + tw + 110) / 2
        d.rounded_rectangle([x0, y - 34, x0 + lw + tw + 110, y + 34], radius=10, fill=WHITE, outline=(210, 214, 222), width=2)
        d.rounded_rectangle([x0, y - 34, x0 + lw, y + 34], radius=10, fill=BLUE)
        d.rectangle([x0 + lw - 12, y - 34, x0 + lw, y + 34], fill=BLUE)
        d.text((x0 + lw / 2, y), str(self.ep.get("contracts", 1)), font=font("black", 38), fill=WHITE, anchor="mm")
        d.text((x0 + lw + 24, y), txt, font=f, fill=UP if pnl >= 0 else DOWN, anchor="lm")
        d.text((x0 + lw + tw + 70, y), "✓" if closed else "×", font=font("black", 34),
               fill=(120, 126, 140), anchor="mm")


# ---------------------------------------------------------------- audio

def build_audio(ep, work):
    lines = [(T_SIG0 + 0.2, "Come on... give me the signal."), (T_FILL + 1.5, "We're in!"),
             (T_PEAK - 0.1, "Let's go!"), (T_LEAVE0 + 0.2, "Okay. Snack break."), (T_SEE + 0.1, "Guys... what happened?")]
    lines = ep.get("lines") and [(float(a), s) for a, s in ep["lines"]] or lines
    parts, words = [], []
    for k, (t0, text) in enumerate(lines):
        mp3 = os.path.join(work, f"l{k}.mp3")
        ws = asyncio.run(R._tts(text, ep.get("voice", "en-US-AvaNeural"), mp3, "+0%", "+0Hz"))
        parts.append((mp3, t0))
        words += [{**w, "t": w["t"] + t0, "scene": k} for w in ws]
    # clock ticking while she's away (suspense), and the order-filled alert at the exit
    tick = os.path.join(work, "tick.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    "aevalsrc=0.25*sin(2*PI*2400*t)*exp(-90*t):s=48000:d=0.12", tick], check=True)
    sfx = R.fill_sound(work)
    inputs, filt, k = [], [], 0
    for mp3, t0 in parts:
        inputs += ["-i", mp3]
        filt.append(f"[{k}:a]aresample=48000,adelay={int(t0 * 1000)}|{int(t0 * 1000)}[a{k}]")
        k += 1
    blip = os.path.join(work, "blip.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    "aevalsrc=0.22*sin(2*PI*(700+300*t*8)*t)*exp(-25*t):s=48000:d=0.18", blip], check=True)
    for i, g in enumerate(GRADE_T):                      # a rising blip each time the grade climbs
        inputs += ["-i", blip]
        filt.append(f"[{k}:a]adelay={int(g * 1000)}|{int(g * 1000)},asetrate=48000*{1 + 0.12 * i:.2f},"
                    f"aresample=48000,volume=0.8[a{k}]")
        k += 1
    tt = T_LEAVE1 + 0.3
    while tt < T_FALL1 - 0.2:
        inputs += ["-i", tick]
        filt.append(f"[{k}:a]adelay={int(tt * 1000)}|{int(tt * 1000)},volume=0.7[a{k}]")
        k += 1
        tt += 0.5
    for tf in (T_FILL, T_FALL1):                         # order-filled alert at the buy and at the exit
        inputs += ["-i", sfx]
        filt.append(f"[{k}:a]adelay={int(tf * 1000)}|{int(tf * 1000)}[a{k}]")
        k += 1
    filt.append("".join(f"[a{i}]" for i in range(k)) + f"amix=inputs={k}:normalize=0,apad[o]")
    wav = os.path.join(work, "pov.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filt), "-map", "[o]",
                    "-t", str(T_END), "-ac", "1", wav], check=True)
    return wav, words


# ---------------------------------------------------------------- render

def render_pov(ep, out_path, work=None):
    work = work or tempfile.mkdtemp()
    wav, words = build_audio(ep, work)
    n = int(T_END * FPS)
    loud = R.loudness_per_frame(wav, n)
    chart = Chart(ep)
    clipcam = ClipCam(ep["cam_clip"], work) if ep.get("cam_clip") and os.path.exists(ep["cam_clip"]["file"]) else None
    m = ep["marks"]
    peak_i = max(range(len(m)), key=lambda i: m[i])
    entry, exit_ = ep["entry"], ep["exit"]
    peak_pnl = (m[peak_i] - entry) * 100 * ep.get("contracts", 1)
    final_pnl = (exit_ - entry) * 100 * ep.get("contracts", 1)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out_path], stdin=subprocess.PIPE)
    for fi in range(n):
        t = fi / FPS
        img = Image.new("RGBA", (W, H), BG + (255,))
        lv = loud[fi]
        # Rica's face follows the trade
        if t < T_FILL:
            face = "calm"
        elif t < T_FILL + 1.4:
            face = "wow"
        elif t < T_RISE0 + 2:
            face = "calm"
        elif t < T_PEAK - 0.4:
            face = "hype"
        elif t < T_LEAVE1:
            face = "wow"
        elif t < T_SEE - 0.2:
            face = "calm"
        elif t < T_SEE + 1.2:
            face = "pain"
        else:
            face = "ugh"
        blink = (t % 3.3) < 0.11 and face != "wow"
        cam = clipcam.frame(t) if clipcam else cam_frame(t, lv, face, blink)
        if T_FILL + 1.4 <= t < T_FILL + 2.4:
            cam = punch(cam.convert("RGBA"), (t - T_FILL - 1.4) / 1.0, {"text": "WE'RE IN", "color": "green"})
        if T_PEAK - 0.1 <= t < T_PEAK + 0.9:
            cam = punch(cam.convert("RGBA"), (t - T_PEAK + 0.1) / 1.0, {"text": "LET'S GOOO", "color": "green"})
        if T_SEE <= t < T_SEE + 1.8:
            cam = punch(cam.convert("RGBA"), (t - T_SEE) / 1.8, {"text": "WAIT WHAT", "color": "red"})
        img.alpha_composite(cam.convert("RGBA"), (0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([28, 30, 50, 52], fill=RED)
        d.text((62, 41), "RICA", font=font("black", 34), fill=WHITE, anchor="lm", stroke_width=3, stroke_fill=(0, 0, 0))
        if clipcam:                                   # realistic AI host: say so on screen
            d.text((W - 24, 41), "AI host · real trades", font=font("bold", 26), fill=(235, 235, 240), anchor="rm",
                   stroke_width=3, stroke_fill=(0, 0, 0))
        # chart
        idx = mark_index(t, len(m), peak_i)
        filled = t >= T_FILL
        last = chart.draw(img, idx, t, live=filled)
        closed = t >= T_FALL1
        pnl = final_pnl if closed else (last - entry) * 100 * ep.get("contracts", 1)
        if filled:
            chart.bubble(img, pnl, closed)
        chart.signal_card(img, t)
        d = ImageDraw.Draw(img)
        # hook text on the chart, then the punchline
        f = font("black", 58)
        if t < T_SEE:
            for i, ln in enumerate(ep["hook"].split("\n")):
                d.text((W / 2, CHART_TOP + 120 + i * 74), ln, font=f, fill=(20, 22, 30), anchor="mm")
        else:
            k = ease((t - T_SEE) / 0.25)
            d.text((W / 2, CHART_TOP + 150), f"+${peak_pnl:.0f}  →  +${final_pnl:.0f}",
                   font=font("black", int(70 + 20 * k)), fill=DOWN, anchor="mm")
            d.text((W / 2, CHART_TOP + 240), "it sold while I was gone", font=font("bold", 40), fill=(60, 64, 76), anchor="mm")
        if filled and t < T_FILL + 1.8:
            filled_toast(img, CHART_TOP + 270, (t - T_FILL) / 1.8)
        if closed and t < T_FALL1 + 1.8:
            filled_toast(img, CHART_TOP + 270 if t < T_SEE else CHART_TOP + 300, (t - T_FALL1) / 1.8)
        # footer: what it is, faint
        d.text((24, H - 60), f"{ep['symbol']} · {ep.get('note', '')}", font=font("medium", 26), fill=(150, 154, 166), anchor="lm")
        d.text((W - 24, H - 60), "Desk Trader", font=font("bold", 26), fill=(150, 154, 166), anchor="rm")
        d.text((W // 2, H - 22), "Not financial advice", font=font("medium", 20), fill=(200, 203, 210), anchor="mm")
        # spoken-word captions over the webcam bottom
        cur = [w for w in words if w["t"] <= t < w["t"] + w["d"] + 0.5]
        if cur:
            grp = [w for w in words if w["scene"] == cur[-1]["scene"]]
            txt = " ".join(w["w"] for w in grp).upper()
            d.text((W / 2, 120), txt, font=font("black", 56), fill=WHITE, anchor="mm",
                   stroke_width=7, stroke_fill=(0, 0, 0))
        ff.stdin.write(img.convert("RGB").tobytes())
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    return out_path


if __name__ == "__main__":
    import json
    render_pov(json.load(open(sys.argv[1])), sys.argv[2])
