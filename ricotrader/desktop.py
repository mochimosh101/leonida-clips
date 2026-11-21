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
    scale = cw / page.width
    page = page.resize((cw, int(page.height * scale)), Image.LANCZOS).crop((0, 0, cw, ch))
    img.paste(page, (CONTENT[0], CONTENT[1]))
    _chrome(d, url, title)
    _taskbar(d)
    _desk_cache[key] = img
    return img


def page_scale(page_path):
    """Screenshot px -> desktop px factor, to translate focus boxes given in screenshot pixels."""
    w = Image.open(page_path).width
    return (CONTENT[2] - CONTENT[0]) / w


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def lerp_box(a, b, k):
    return [a[i] + (b[i] - a[i]) * k for i in range(4)]


def fit_aspect(box, aspect):
    """Grow the box to the output aspect (w/h) around its center, kept inside the desktop."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
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


class ScreenCam:
    """Per-frame view of the desktop for a given output box size."""

    def __init__(self, ep, out_w, out_h):
        self.cfg = ep["screen"]
        self.out_w, self.out_h = out_w, out_h
        self.aspect = out_w / out_h
        self.full = fit_aspect([0, 0, DW, DH * 0.62], self.aspect)

    def desktop(self, page):
        p = self.cfg["pages"][page]
        url = self.cfg.get("urls", {}).get(page, self.cfg.get("url", ""))
        title = self.cfg.get("titles", {}).get(page, self.cfg.get("title", "Desk Trader"))
        return make_desktop(p, url, title,
                            self.cfg.get("blur", {}).get(page, []))

    def frame(self, scenes, si, p, t, timeline):
        """Return an RGB image (out_w x out_h) plus the pointer position in output coords."""
        cur = scenes[si].get("screen", {})
        prev = {}
        for j in range(si - 1, -1, -1):
            if scenes[j].get("screen"):
                prev = scenes[j]["screen"]
                break
        first_page = next((s["screen"]["page"] for s in scenes if s.get("screen")), None)
        page_prev = prev.get("page", first_page)
        page_cur = cur.get("page", page_prev)
        click = cur.get("click")
        click_at = 0.22 if click else 0.0
        page = page_cur if p >= click_at else page_prev
        pad = lambda b: [b[0] - 50, b[1] - 30, b[2] + 50, b[3] + 30]   # breathing room around the focus
        box_prev = fit_aspect(pad(prev.get("focus", self.full)), self.aspect)
        box_cur = fit_aspect(pad(cur["focus"]), self.aspect) if cur.get("focus") else box_prev
        # camera: hold wide on the click, then move to the new focus
        k = ease((p - click_at) / 0.18) if click else ease(p / 0.15)
        box = lerp_box(box_prev, box_cur, k)
        # slow push-in after arriving
        push = 1 - 0.04 * ease((p - 0.4) / 0.6)
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        bw, bh = (box[2] - box[0]) * push, (box[3] - box[1]) * push
        box = [cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2]
        img = self.desktop(page).crop(tuple(int(v) for v in box)).resize((self.out_w, self.out_h), Image.BILINEAR)
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
