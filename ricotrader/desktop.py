"""A Windows desktop with a Chrome window showing real Desk Trader page screenshots.

The video shows a moving "camera" over that 1920x1080 desktop: it eases between focus boxes,
a mouse pointer travels to the tab/button being clicked, and the page swaps on the click,
like an edited screen recording.

Episode JSON (stream layout) adds:
  "screen": {
    "url": "desktrader.example/app", "urls": {"history": ".../history"}, "titles": {...},   # per-page optional
    "pages": {"history": "ricotrader/screens/history.png", ...},   # browser-content screenshots
    "blur": {"history": [[x0, y0, x1, y1], ...]}                   # boxes in screenshot pixels
  }
and per scene:
  "screen": {"page": "history", "focus": [x0, y0, x1, y1], "click": [x, y]}   # desktop coords
"""
import datetime
import math
import os

from PIL import Image, ImageDraw, ImageFilter

from ricotrader.render import font, mix

DW, DH = 1920, 1080
TASKBAR = 48
TABBAR = 42
ADDR = 46
CONTENT = (0, TABBAR + ADDR, DW, DH - TASKBAR)      # where the page screenshot goes
_desk_cache = {}
MIN_VIEW_W = 900


def _wallpaper():
    img = Image.new("RGB", (DW, DH))
    d = ImageDraw.Draw(img)
    for y in range(DH):
        d.line([0, y, DW, y], fill=mix((18, 40, 92), (70, 120, 200), y / DH))
    glow = Image.new("RGBA", (DW, DH), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([DW * 0.25, DH * 0.15, DW * 0.95, DH * 1.2], fill=(120, 170, 255, 120))
    img.paste(glow.filter(ImageFilter.GaussianBlur(160)), (0, 0), glow.filter(ImageFilter.GaussianBlur(160)))
    return img


def _taskbar(d):
    d.rectangle([0, DH - TASKBAR, DW, DH], fill=(32, 32, 38))
    cx = DW // 2 - 110
    # start button (four squares)
    for i, (dx, dy) in enumerate([(0, 0), (11, 0), (0, 11), (11, 11)]):
        d.rectangle([cx + dx, DH - 34 + dy, cx + dx + 9, DH - 34 + dy + 9], fill=(80, 170, 255))
    icons = [(255, 200, 60), (66, 133, 244), (90, 90, 100), (0, 200, 140)]
    for i, c in enumerate(icons):
        x = cx + 50 + i * 48
        d.rounded_rectangle([x, DH - 38, x + 28, DH - 10], radius=6, fill=c)
        if i == 1:  # chrome = active
            d.rectangle([x + 6, DH - 5, x + 22, DH - 3], fill=(120, 180, 255))
    now = datetime.datetime(2026, 11, 20, 13, 5)
    d.text((DW - 20, DH - 33), now.strftime("%-I:%M %p"), font=font("medium", 16), fill=(235, 235, 240), anchor="rm")
    d.text((DW - 20, DH - 14), now.strftime("%-m/%-d/%Y"), font=font("medium", 16), fill=(235, 235, 240), anchor="rm")


def _chrome(d, url, title):
    d.rectangle([0, 0, DW, TABBAR + ADDR], fill=(32, 33, 36))
    d.rounded_rectangle([10, 8, 290, TABBAR + 8], radius=10, fill=(53, 54, 58))
    d.ellipse([24, 18, 40, 34], fill=(0, 229, 255))
    d.text((50, 26), title, font=font("medium", 17), fill=(232, 234, 237), anchor="lm")
    d.text((270, 26), "×", font=font("medium", 18), fill=(180, 180, 185), anchor="mm")
    d.text((312, 26), "+", font=font("medium", 24), fill=(180, 180, 185), anchor="mm")
    for i, ch in enumerate(["–", "□", "×"]):
        d.text((DW - 130 + i * 46, 22), ch, font=font("medium", 20), fill=(220, 220, 225), anchor="mm")
    y = TABBAR + ADDR // 2
    for i, ch in enumerate(["←", "→", "⟳"]):
        d.text((26 + i * 38, y), ch, font=font("medium", 22), fill=(200, 200, 205), anchor="mm")
    d.rounded_rectangle([140, TABBAR + 7, DW - 120, TABBAR + ADDR - 7], radius=16, fill=(53, 54, 58))
    d.text((166, y), "🔒" if False else "⊙", font=font("medium", 16), fill=(180, 180, 185), anchor="mm")
    d.text((186, y), url, font=font("medium", 18), fill=(232, 234, 237), anchor="lm")


def make_desktop(page_path, url, title="Desk Trader", blur_boxes=()):
    key = (page_path, url, title, tuple(map(tuple, blur_boxes)))
    if key in _desk_cache:
        return _desk_cache[key]
    img = _wallpaper()
    d = ImageDraw.Draw(img)
    page = Image.open(page_path).convert("RGB")
    for b in blur_boxes:  # hide balances / personal info before scaling
        region = page.crop(tuple(b)).filter(ImageFilter.GaussianBlur(14))
        page.paste(region, tuple(b[:2]))
    cw, ch = CONTENT[2] - CONTENT[0], CONTENT[3] - CONTENT[1]
    scale = _fit_scale(page.width, page.height, page_path)
    page = page.resize((int(page.width * scale), int(page.height * scale)), Image.LANCZOS).crop((0, 0, cw, ch))
    if page.width < cw:   # page is taller than the window: extend its right edge (scrollbar track) to fill
        edge = page.crop((page.width - 2, 0, page.width, page.height)).resize((cw - page.width, page.height))
        img.paste(edge, (CONTENT[0] + page.width, CONTENT[1]))
    img.paste(page, (CONTENT[0], CONTENT[1]))
    _chrome(d, url, title)
    _taskbar(d)
    _desk_cache[key] = img
    return img


FIT_HEIGHT = set()   # page paths shown whole (fit to window height) instead of fit to width


def _fit_scale(w, h, path=None):
    cw, ch = CONTENT[2] - CONTENT[0], CONTENT[3] - CONTENT[1]
    return ch / h if path in FIT_HEIGHT else cw / w


def page_scale(page_path):
    """Screenshot px -> desktop px factor, to translate focus boxes given in screenshot pixels."""
    w, h = Image.open(page_path).size
    return _fit_scale(w, h, page_path)


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def lerp_box(a, b, k):
    return [a[i] + (b[i] - a[i]) * k for i in range(4)]


def fit_aspect(box, aspect):
    """Grow the box to the output aspect (w/h) around its center, kept inside the desktop."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    cx_, cy_ = (x0 + x1) / 2, (y0 + y1) / 2
    if w < MIN_VIEW_W:                 # never zoom past ~1.2x of the real screenshot pixels (keeps text sharp)
        w = MIN_VIEW_W
        x0, x1 = cx_ - w / 2, cx_ + w / 2
    if w / h > aspect:
        h = w / aspect
    else:
        w = h * aspect
    w, h = min(w, DW), min(h, DH)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    x0 = min(max(0, cx - w / 2), DW - w)
    y0 = min(max(0, cy - h / 2), DH - h)
    return [x0, y0, x0 + w, y0 + h]


def draw_pointer(img, x, y, pressed=False, ripple=0.0):
    d = ImageDraw.Draw(img)
    if ripple > 0:
        r = 10 + 40 * ripple
        d.ellipse([x - r, y - r, x + r, y + r], outline=(255, 214, 64), width=4)
    s = 1.5
    pts = [(0, 0), (0, 30), (8, 23), (14, 36), (20, 33), (14, 21), (24, 21)]
    pts = [(x + px * s, y + py * s + (2 if pressed else 0)) for px, py in pts]
    d.polygon(pts, fill=(255, 255, 255), outline=(0, 0, 0))


def _to_desk(page_path, x, y):
    k = page_scale(page_path)
    return CONTENT[0] + x * k, CONTENT[1] + y * k


def draw_fill(d, x, y, side, label, k, a, up=None, stem=34):
    """App-style fill marker: arrow + tag. (x, y) already in crop coords; k = page->desktop scale."""
    col = (38, 214, 120) if side == "buy" else (255, 77, 106) if side == "loss" else (255, 196, 40)
    r = 9 * k * (0.6 + 0.4 * a)
    d.ellipse([x - r, y - r, x + r, y + r], fill=col, outline=(255, 255, 255), width=max(2, int(2 * k)))
    f = font("black", int(17 * k))
    tw = d.textlength(label, font=f)
    up = (side == "buy") if up is None else up      # True = tag hangs below the marker
    ty = y + (stem if up else -stem) * k
    d.line([x, y + (r if up else -r), x, ty + (-12 if up else 12) * k], fill=col, width=max(2, int(2 * k)))
    d.rounded_rectangle([x - tw / 2 - 10 * k, ty - 14 * k, x + tw / 2 + 10 * k, ty + 14 * k], radius=int(6 * k), fill=col)
    d.text((x, ty), label, font=f, fill=(10, 12, 18), anchor="mm")


class ScreenCam:
    """Per-frame view of the desktop for a given output box size."""

    def __init__(self, ep, out_w, out_h):
        self.cfg = ep["screen"]
        self.out_w, self.out_h = out_w, out_h
        self.aspect = out_w / out_h
        self.full = fit_aspect([0, 0, DW, DH * 0.62], self.aspect)
        for name in self.cfg.get("fit_height", []):
            FIT_HEIGHT.add(self.cfg["pages"][name])

    def desktop(self, page):
        p = self.cfg["pages"][page]
        url = self.cfg.get("urls", {}).get(page, self.cfg.get("url", ""))
        title = self.cfg.get("titles", {}).get(page, self.cfg.get("title", "Desk Trader"))
        return make_desktop(p, url, title,
                            self.cfg.get("blur", {}).get(page, []))

    def live_now(self, scenes, si, p):
        """Chart clock (hour of day, price) for this frame: steps forward one 5-minute candle at a time."""
        prev = self.cfg.get("live_start")
        cur = None
        for j in range(si):
            prev = scenes[j].get("screen", {}).get("now", prev)
        cur = scenes[si].get("screen", {}).get("now")
        if prev is None:
            prev = cur
        if cur is None:
            return prev
        k = ease((p - 0.05) / 0.4)    # the chart catches up to 'now' in the first ~half of the line
        h = prev[0] + (cur[0] - prev[0]) * k
        h = math.floor(h * 12) / 12 if k < 1 else cur[0]
        price = prev[1] + (cur[1] - prev[1]) * k
        return h, price

    def draw_live(self, d, L, now, k, ib, t):
        """Hide the candles that haven't happened yet and move a live price tag, so the chart plays like live."""
        X = lambda x: CONTENT[0] + x * k - ib[0]
        Y = lambda y: CONTENT[1] + y * k - ib[1]
        (h0, x0, pxh), (p0, y0, p1, y1) = L["time"], L["price"]
        px = lambda h: x0 + (h - h0) * pxh
        py = lambda pr: y0 + (p0 - pr) * (y1 - y0) / (p0 - p1)
        a0, b0, a1, b1 = L["plot"]
        cx = px(now[0] + 1 / 12)                       # right edge of the current candle
        bg = tuple(L.get("bg", (17, 22, 31)))
        if cx < a1:
            d.rectangle([X(max(cx, a0)), Y(b0), X(a1), Y(b1)], fill=bg)
            for gy in L.get("grid", []):
                d.line([X(max(cx, a0)), Y(gy), X(a1), Y(gy)], fill=(26, 32, 43), width=max(1, int(k)))
        ax0, ax1 = L["axis"]
        d.rectangle([X(ax0), Y(b0 - 10), X(ax1), Y(b1)], fill=bg)
        f = font("medium", int(13 * k))
        v = p0
        while v >= p1 - 0.01:
            d.text((X(ax0 + 8), Y(py(v))), f"{v:.2f}", font=f, fill=(150, 156, 172), anchor="lm")
            v -= L.get("step", 2.5)
        price = now[1] + math.sin(t * 7.3) * 0.06 + math.sin(t * 2.9) * 0.05
        yy = Y(py(price))
        x = X(a0)
        while x < X(ax0):                               # dashed live-price line
            d.line([x, yy, min(x + 6 * k, X(ax0)), yy], fill=(80, 200, 255), width=max(1, int(k)))
            x += 11 * k
        d.ellipse([X(cx) - 5 * k, yy - 5 * k, X(cx) + 5 * k, yy + 5 * k], fill=(80, 200, 255))
        fb = font("black", int(14 * k))
        d.rounded_rectangle([X(ax0 + 1), yy - 11 * k, X(ax1 - 2), yy + 11 * k], radius=int(3 * k), fill=(80, 200, 255))
        d.text(((X(ax0 + 1) + X(ax1 - 2)) / 2, yy), f"{price:.2f}", font=fb, fill=(8, 12, 20), anchor="mm")

    def draw_overlays(self, img, scenes, si, p, page, ib, t=0.0):
        """Real fills (markers on the chart) and rows in the app's Today's trades list, page-pixel coords."""
        cfg = self.cfg.get("overlays", {}).get(page)
        if not cfg:
            return
        path = self.cfg["pages"][page]
        k = page_scale(path)
        d = ImageDraw.Draw(img)
        if cfg.get("live"):
            now = self.live_now(scenes, si, p)
            if now:
                self.draw_live(d, cfg["live"], now, k, ib, t)
        fills, rows = [], []
        for j in range(si + 1):
            sc = scenes[j].get("screen", {})
            for f in sc.get("fills", []):
                a = 1.0 if j < si else ease((p - f.get("at", 0.25)) / 0.08)
                if a > 0:
                    fills.append((f, a))
            for r in sc.get("rows", []):
                a = 1.0 if j < si else ease((p - r.get("at", 0.3)) / 0.08)
                if a > 0:
                    rows.append((r, a))
        L = cfg.get("list")
        if L and rows:
            x0, y0, x1, y1 = L["box"]
            dx0, dy0 = _to_desk(path, x0, y0)
            dx1, dy1 = _to_desk(path, x1, y1)
            d.rectangle([dx0 - ib[0], dy0 - ib[1], dx1 - ib[0], dy1 - ib[1]], fill=tuple(L.get("bg", (17, 22, 31))))
            for n, (r, a) in enumerate(reversed(rows)):   # newest on top, like the app
                ry = dy0 - ib[1] + (8 + n * 46) * k
                if ry > dy1 - ib[1] - 30 * k:
                    break
                rx = dx0 - ib[0] + 10 * k
                col = (38, 214, 120) if r["pnl"] >= 0 else (255, 77, 106)
                d.rounded_rectangle([rx, ry, dx1 - ib[0] - 10 * k, ry + 40 * k], radius=int(6 * k), fill=(24, 30, 42))
                d.rectangle([rx, ry, rx + 4 * k, ry + 40 * k], fill=col)
                d.text((rx + 14 * k, ry + 13 * k), r["sym"], font=font("black", int(15 * k)), fill=(235, 238, 245), anchor="lm")
                d.text((rx + 14 * k, ry + 30 * k), r["time"] + " · " + r.get("what", "sold"), font=font("medium", int(12 * k)),
                       fill=(140, 146, 170), anchor="lm")
                txt = ("+$" if r["pnl"] >= 0 else "-$") + f"{abs(r['pnl']):.0f}"
                d.text((dx1 - ib[0] - 22 * k, ry + 20 * k), txt, font=font("black", int(17 * k)), fill=col, anchor="rm")
        for f, a in fills:
            x, y = _to_desk(path, f["x"], f["y"])
            draw_fill(d, x - ib[0], y - ib[1], f.get("side", "buy"), f["label"], k, a, f.get("below"), f.get("stem", 34))

    def frame(self, scenes, si, p, t, timeline):
        """Return an RGB image (out_w x out_h) plus the pointer position in output coords."""
        cur = scenes[si].get("screen", {})
        prev = {}
        for j in range(si - 1, -1, -1):
            if scenes[j].get("screen"):
                prev = scenes[j]["screen"]
                break
        if not prev and cur.get("from_focus"):      # cold open: start already zoomed in, not on the full desktop
            prev = {"focus": cur["from_focus"], "page": cur.get("page")}
        first_page = next((s["screen"]["page"] for s in scenes if s.get("screen")), None)
        page_prev = prev.get("page", first_page)
        page_cur = cur.get("page", page_prev)
        click = cur.get("click")
        click_at = 0.22 if click else 0.0
        page = page_cur if p >= click_at else page_prev
        pad = lambda b: [b[0] - 50, b[1] - 30, b[2] + 50, b[3] + 30]   # breathing room around the focus
        box_prev = fit_aspect(pad(prev.get("focus", self.full)), self.aspect)
        box_cur = fit_aspect(pad(cur["focus"]), self.aspect) if cur.get("focus") else box_prev
        def keep_in(b, xr=1440):                      # never show the blurred strip right of the app
            if b[2] - b[0] <= xr and b[2] > xr:
                b = [b[0] - (b[2] - xr), b[1], xr, b[3]]
            return b
        box_prev, box_cur = keep_in(box_prev), keep_in(box_cur)
        # camera: hold wide on the click, then move to the new focus
        k = ease((p - click_at) / 0.18) if click else ease(p / 0.15)
        box = lerp_box(box_prev, box_cur, k)
        # slow push-in after arriving
        push = 1 - 0.04 * ease((p - 0.4) / 0.6)
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        bw, bh = (box[2] - box[0]) * push, (box[3] - box[1]) * push
        box = [cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2]
        ib = (max(0, int(box[0]) - 1), max(0, int(box[1]) - 1), min(DW, int(box[2]) + 2), min(DH, int(box[3]) + 2))
        img = self.desktop(page).crop(ib)
        self.draw_overlays(img, scenes, si, p, page, ib, t)
        # one high-quality resample with a sub-pixel box: sharp text and smooth (non-jittery) camera moves
        img = img.resize((self.out_w, self.out_h), Image.LANCZOS,
                         box=(box[0] - ib[0], box[1] - ib[1], box[2] - ib[0], box[3] - ib[1]))
        img = img.filter(ImageFilter.UnsharpMask(radius=1.1, percent=55, threshold=2))
        # pointer travels from the previous click to this one
        start = prev.get("click", [DW * 0.6, DH * 0.5])
        end = click or start
        km = ease(p / max(click_at, 0.01)) if click else 1
        mx = start[0] + (end[0] - start[0]) * km + (0 if click else math.sin(t * 0.8) * 30)
        my = start[1] + (end[1] - start[1]) * km + (0 if click else math.cos(t * 1.1) * 18)
        ox = (mx - box[0]) / (box[2] - box[0]) * self.out_w
        oy = (my - box[1]) / (box[3] - box[1]) * self.out_h
        ripple = 0.0
        if click and click_at <= p < click_at + 0.08:
            ripple = (p - click_at) / 0.08
        img = img.convert("RGBA")
        draw_pointer(img, ox, oy, pressed=ripple > 0, ripple=ripple)
        return img
