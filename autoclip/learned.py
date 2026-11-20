"""What the daily reviewer learned, read back by the bot so better-performing styles get used more.

state/learned.json is written by autoclip/review.py once a day. Each channel ("en", "es") has:
  weights: {factor: {option: share}}  e.g. caption_style {"A": 0.2, "B": 0.5, "C": 0.3}
  lessons: short plain-English rules for the writer (from Claude reading the stats)
If the file is missing or a factor has no data yet, every option is equally likely (a fair A/B test).
Every option always keeps some share, so the bot keeps testing the losers in case things change.
"""
import json
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "state", "learned.json")

# Every A/B option the bot can choose from. Keep in sync with captions.py / writer.py / listicle.py.
OPTIONS = {
    "caption_style": ["A", "B", "C"],
    "hook_style": [f"H{i}" for i in range(1, 8)],
    "verdict_style": [f"V{i}" for i in range(1, 7)],
    "title_style": ["count", "utility"],
    "look": ["clean", "sticker"],
}


def channel_key(cfg: dict) -> str:
    return cfg.get("channel_key", "en")


def load(cfg: dict) -> dict:
    try:
        with open(PATH) as f:
            return json.load(f).get("channels", {}).get(channel_key(cfg), {})
    except (OSError, ValueError):
        return {}


def pick(cfg: dict, factor: str, options=None) -> str:
    """Weighted random choice for an A/B factor (uniform until the reviewer has data)."""
    options = sorted(options or OPTIONS[factor])
    w = load(cfg).get("weights", {}).get(factor, {})
    weights = [max(float(w.get(o, 0) or 0), 0.0) for o in options]
    if sum(weights) <= 0:
        return random.choice(options)
    floor = 0.05 * sum(weights)  # a new option nobody has scored still gets tried
    return random.choices(options, weights=[x or floor for x in weights])[0]


def writer_notes(cfg: dict) -> str:
    """Text added to the writer's prompt: which hook/verdict styles are winning and what to keep doing."""
    data = load(cfg)
    lines = []
    for factor, label in (("hook_style", "Hook styles"), ("verdict_style", "Verdict styles")):
        w = data.get("weights", {}).get(factor, {})
        tested = data.get("tested", {}).get(factor, {})
        fair = 1 / len(w) if w else 0
        # only recommend styles with real evidence: 3+ Shorts and doing better than an even split
        best = [o for o in sorted(w, key=w.get, reverse=True) if tested.get(o, 0) >= 3 and w[o] > fair * 1.1][:3]
        if best:
            lines.append(f"- {label} getting the most views on this channel lately: {', '.join(best)} "
                         f"(prefer them, but still vary)")
    for lesson in data.get("lessons", [])[:5]:
        lines.append(f"- {lesson}")
    if not lines:
        return ""
    return "What's working on this channel (from the daily stats review):\n" + "\n".join(lines)
