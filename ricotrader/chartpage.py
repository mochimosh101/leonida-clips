"""Desk Trader style chart page drawn from REAL minute prices, so every candle, fill, stop and target sits
at its true time and price. The app frame comes from a real screenshot; only the chart, axes and the
day-specific panels are redrawn for the replayed day."""
import json
import math

from PIL import Image, ImageDraw, ImageFilter

from .render import font

BASE = "ricotrader/screens/xpro-qqq.png"
BG = (17, 22, 31)
PANEL = (10, 14, 20)
GRID = (26, 32, 43)
UP, DOWN = (38, 200, 160), (240, 70, 90)
MUTED = (150, 156, 172)
PLOT = (470, 240, 1375, 845)        # x0, y0, x1, y1 of the candle area
AXIS = (1382, 1446)


def candles(bars1m, minutes=5):
    """1-minute [o,h,l,c] list starting 6:30 AM PT -> 5-minute candles."""
    out = []
    for i in range(0, len(bars1m), minutes):
        g = [b for b in bars1m[i:i + minutes] if b]
        if g:
            out.append([g[0][0], max(b[1] for b in g), min(b[2] for b in g), g[-1][3]])
    return out


def ema(vals, n):
    k, out, e = 2 / (n + 1), [], None
    for v in vals:
        e = v if e is None else v * k + e * (1 - k)
        out.append(e)
    return out


def make_page(bars1m, date_label, out_path, start_h=6.5, end_h=13.0, step=2.5):
    """Draw the page; returns the 'live' overlay spec (time->x, price->y) for the episode JSON."""
    im = Image.open(BASE).convert("RGB")
    W, H = im.size
    d = ImageDraw.Draw(im)
    cs = candles(bars1m)
    hi = max(c[1] for c in cs)
    lo = min(c[2] for c in cs)
    p0 = math.ceil(hi / step) * step + step / 2
    p1 = math.floor(lo / step) * step - step / 2
    x0, y0, x1, y1 = PLOT
    pxh = (x1 - x0) / (end_h - start_h)
    px = lambda h: x0 + (h - start_h) * pxh
    py = lambda q: y0 + (p0 - q) * (y1 - y0) / (p0 - p1)

    # wipe the old chart, legend, banner, axes and status line
    d.rectangle([462, 112, 1432, 905], fill=BG)
    d.rounded_rectangle([468, 118, 1425, 207], radius=8, fill=(19, 33, 41), outline=(40, 120, 140), width=1)
    d.text((482, 140), "Market replay · " + date_label, font=font("black", 15), fill=(235, 238, 245), anchor="lm")
    d.text((482, 168), "QQQ 5-minute candles from the real 1-minute prices. Every marker is a real fill from my account.",
           font=font("medium", 13), fill=MUTED, anchor="lm")
    d.text((1412, 140), "Replay", font=font("medium", 13), fill=MUTED, anchor="rm")
    # grid + price axis labels
    v = math.floor(p0 / step) * step
    grid = []
    while v >= p1:
        y = py(v)
        d.line([x0 - 8, y, x1, y], fill=GRID, width=1)
        d.text((AXIS[0] + 8, y), f"{v:.2f}", font=font("medium", 13), fill=MUTED, anchor="lm")
        grid.append(v)
        v -= step
    # time axis
    h = math.ceil(start_h * 2) / 2
    while h <= end_h + 1e-6:
        x = px(h)
        hh, mm = int(h), int(round((h - int(h)) * 60))
        lab = f"{(hh - 1) % 12 + 1}:{mm:02d} {'AM' if hh < 12 else 'PM'}"
        d.line([x, y0, x, y1], fill=(21, 27, 37), width=1)
        d.text((x, 862), lab, font=font("medium", 12), fill=MUTED, anchor="mm")
        h += 1.0
    # candles + EMAs
    cw = pxh / 12
    for i, (o, hgh, low, c) in enumerate(cs):
        cx = px(start_h + (i + 0.5) / 12)
        col = UP if c >= o else DOWN
        d.line([cx, py(hgh), cx, py(low)], fill=col, width=1)
        top, bot = py(max(o, c)), py(min(o, c))
        d.rectangle([cx - cw * 0.36, top, cx + cw * 0.36, max(bot, top + 1)], fill=col)
    closes = [c[3] for c in cs]
    for n, col in ((9, (255, 160, 40)), (21, (70, 170, 255))):
        e = ema(closes, n)
        d.line([(px(start_h + (i + 0.5) / 12), py(v)) for i, v in enumerate(e)], fill=col, width=2)
    d.text((x1 - 4, 228), "EMA 9", font=font("bold", 12), fill=(255, 160, 40), anchor="rm")
    d.text((x1 - 54, 228), "EMA 21", font=font("bold", 12), fill=(70, 170, 255), anchor="rm")
    d.text((470, 228), "QQQ · 5m · " + date_label, font=font("bold", 12), fill=MUTED, anchor="lm")
    d.text((1420, 891), "Chart: real 1-minute prices grouped into 5-minute candles", font=font("medium", 12),
           fill=MUTED, anchor="rm")
    # left panel: the old day's numbers would be wrong, so replace them with this day's facts
    d.rectangle([0, 110, 458, 674], fill=PANEL)
    d.rectangle([640, 50, 712, 74], fill=PANEL)                     # old "1 open" pill
    d.rectangle([320, 84, 430, 101], fill=PANEL)                    # old "MARKET CLOSED" pill
    d.text((424, 92), "REPLAY", font=font("bold", 11), fill=(80, 200, 255), anchor="rm")
    d.text((14, 128), "REPLAY · " + date_label, font=font("medium", 13), fill=(80, 200, 255), anchor="lm")
    d.text((14, 168), f"Open ${cs[0][0]:.2f}", font=font("black", 26), fill=(235, 238, 245), anchor="lm")
    d.text((14, 204), f"Day range ${lo:.2f} – ${hi:.2f}", font=font("medium", 15), fill=MUTED, anchor="lm")
    # status bar: no "closed / opens Monday" text for a replayed day
    d.rectangle([40, 50, 640, 74], fill=PANEL)
    d.text((54, 62), "REPLAY · " + date_label, font=font("bold", 13), fill=(200, 205, 225), anchor="lm")
    # right column belongs to another day: blur it out
    box = (1434, 80, W, H)
    im.paste(im.crop(box).filter(ImageFilter.GaussianBlur(16)), box[:2])
    im.save(out_path)
    return {"time": [start_h, x0, pxh], "price": [p0, y0, p1, y1], "plot": [x0, y0, x1, y1],
            "axis": list(AXIS), "step": step, "grid": grid, "bg": list(BG)}, cs


def xy(spec, h, q):
    (h0, x0, pxh), (p0, y0, p1, y1) = spec["time"], spec["price"]
    return round(x0 + (h - h0) * pxh, 1), round(y0 + (p0 - q) * (y1 - y0) / (p0 - p1), 1)


if __name__ == "__main__":
    import sys
    bars = json.load(open(sys.argv[1]))
    spec, _ = make_page(bars, sys.argv[2], sys.argv[3])
    print(json.dumps(spec))
