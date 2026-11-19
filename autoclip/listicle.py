"""Series Shorts: "10 Mistakes to Avoid in GTA 6", tips & tricks, hidden secrets... one tip per Short, Part 1..N.

Layout (copied from what's working on TikTok, Mochi 2026-11-19): big series title on top, gameplay in the
middle, "Part N" under it and the tip in a dark caption box. Rico reads the tip.

Tips come from a web search (GTA 6 launched after the model's training data, so Claude must not guess),
gameplay comes from today's top Twitch clips. The series plan is kept in state/series.json so each run
posts the next part.
"""
import json
import os
import random

import anthropic
from pydantic import BaseModel, Field

from . import edit, twitch, voice

W, H = 1080, 1920
GAME_W, GAME_H, GAME_Y = 1080, 608, 640

# Rotated so the channel doesn't post the same kind of list twice in a row.
TOPICS = [
    "mistakes to avoid in GTA 6",
    "GTA 6 tips and tricks most players don't know",
    "GTA 6 money tips for the first week",
    "hidden GTA 6 features and secrets",
    "ways to escape the cops in GTA 6",
    "GTA 6 things you should do first",
    "GTA 6 driving and car tips",
    "GTA 6 combat and weapon tips",
]


class Tip(BaseModel):
    caption: str = Field(description="On-screen tip, 5 to 12 words, sentence case, no emoji")
    narration: str = Field(description="What Rico says: 1 to 2 short sentences, max 30 words, adds the why or how")
    footage: str = Field(description="What gameplay would fit, e.g. 'police chase', 'car crash', 'shooting'")
    source_url: str = Field(description="The page this tip came from")


class SeriesPlan(BaseModel):
    series_title: str = Field(description="Top banner, max 32 characters, e.g. '10 Mistakes to avoid in GTA 6'")
    item_word: str = Field(description="How Rico counts them: 'Mistake', 'Tip', 'Secret', 'Trick'...")
    tips: list[Tip] = Field(description="Exactly as many tips as the title promises, best first")


class FootagePick(BaseModel):
    index: int = Field(description="Number of the clip that best fits the tip")


RESEARCH_PROMPT = """GTA 6 (Grand Theft Auto VI) is out now. Search the web for the best current, real,
player-tested "{topic}" from guides, news sites and Reddit published since launch. Then write a list of
{n} of them for a YouTube Shorts series called something like "{n} {topic_title}".

Only include tips you found in a source and that apply to GTA 6 itself (not GTA 5 or Online). Skip
story-mode spoilers (missions, endings, cutscenes) and anything about glitches that Rockstar may patch
or that break the rules. Order them from most useful or surprising to least.
Already used series titles (pick a different angle): {done}.
For each tip give: the tip, why it matters or how to do it, what gameplay would show it, and the source URL."""

FORMAT_PROMPT = """Turn these researched GTA 6 tips into a Shorts series plan for "Leonida Clips". The host,
Rico Neon, is a washed-up Vice City getaway driver: deadpan, a bit smug, actually helpful. Each narration
is Rico explaining one tip in his voice, plain words, no greeting, no channel name. Keep only tips that
name a source URL.

Research notes:
{notes}"""


def _research(client: anthropic.Anthropic, model: str, topic: str, done: list[str]) -> SeriesPlan | None:
    n = random.choice([5, 7, 10])
    messages = [{"role": "user", "content": RESEARCH_PROMPT.format(
        topic=topic, n=n, topic_title=topic.replace("in GTA 6", "").strip(), done=", ".join(done[-10:]) or "none")}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}]
    resp = client.messages.create(model=model, max_tokens=16000, output_config={"effort": "medium"},
                                  messages=messages, tools=tools)
    for _ in range(5):  # the server pauses long searches; send it back to continue
        if resp.stop_reason != "pause_turn":
            break
        messages = messages[:1] + [{"role": "assistant", "content": resp.content}]
        resp = client.messages.create(model=model, max_tokens=16000, output_config={"effort": "medium"},
                                      messages=messages, tools=tools)
    if resp.stop_reason == "refusal":
        return None
    notes = "\n".join(b.text for b in resp.content if b.type == "text").strip()
    if not notes:
        return None
    plan = client.messages.parse(
        model=model, max_tokens=8000, output_config={"effort": "low"},
        messages=[{"role": "user", "content": FORMAT_PROMPT.format(notes=notes)}],
        output_format=SeriesPlan,
    ).parsed_output
    if plan:
        plan.tips = [t for t in plan.tips if t.source_url.startswith("http")]
    return plan if plan and len(plan.tips) >= 3 else None


def _pick_footage(client: anthropic.Anthropic, model: str, tip: Tip, clips: list) -> int:
    listing = "\n".join(f"{i}. {c.title} ({c.broadcaster_name})" for i, c in enumerate(clips))
    try:
        pick = client.messages.parse(
            model=model, max_tokens=2000, output_config={"effort": "low"},
            messages=[{"role": "user", "content":
                       f"Which GTA 6 Twitch clip would make the best background gameplay for this tip?\n"
                       f"Tip: {tip.caption}\nIdeal footage: {tip.footage}\n\nClips:\n{listing}\n"
                       f"Prefer driving, chases, action or city footage; avoid anything sexual or story cutscenes."}],
            output_format=FootagePick,
        ).parsed_output
        if pick and 0 <= pick.index < len(clips):
            return pick.index
    except anthropic.APIError as e:
        print(f"footage pick failed ({e}); using the top clip")
    return 0


def _ass_text(s: str) -> str:
    return s.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", r"\N")


def _build_ass(path: str, title: str, part: int, caption: str, credit: str, dur: float, next_part: int | None):
    def ts(t):
        return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"

    end = ts(dur)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        "Style: Title,Montserrat ExtraBold,100,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,2,70,70,1360,1",
        "Style: Part,Montserrat ExtraBold,112,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,8,60,60,1330,1",
        "Style: Tip,Montserrat SemiBold,60,&H00FFFFFF,&H00FFFFFF,&H00303030,&H00303030,0,0,0,0,100,100,0,0,3,18,0,8,80,80,1500,1",
        "Style: Credit,Montserrat SemiBold,34,&H00C8C8C8,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,8,60,60,1262,1",
        "Style: Next,Montserrat ExtraBold,54,&H00B414FF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,2,60,60,110,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        f"Dialogue: 0,0:00:00.00,{end},Title,,0,0,0,,{_ass_text(title)}",
        f"Dialogue: 0,0:00:00.00,{end},Part,,0,0,0,,Part {part}",
        f"Dialogue: 0,0:00:00.00,{end},Tip,,0,0,0,,{{\\fad(250,0)}}{_ass_text(caption)}",
        f"Dialogue: 0,0:00:00.00,{end},Credit,,0,0,0,,{_ass_text(credit)}",
    ]
    if next_part:
        lines.append(f"Dialogue: 0,{ts(max(0, dur - 2.5))},{end},Next,,0,0,0,,{{\\fad(200,0)}}FOLLOW FOR PART {next_part}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def render(src: str, narration_mp3: str, ass_path: str, out: str, dur: float, start: float = 0.0) -> str:
    import subprocess
    ass = ass_path.replace("\\", "/").replace(":", "\\:")
    v = (f"color=c=black:s={W}x{H}:d={dur:.2f}:r=30[bg];"
         f"[0:v]scale={GAME_W}:{GAME_H}:force_original_aspect_ratio=increase,crop={GAME_W}:{GAME_H},setsar=1[g];"
         f"[bg][g]overlay=0:{GAME_Y}:shortest=1[base];[base]ass='{ass}'[vout]")
    narr = "[1:a]adelay=300|300,volume=1.6[n]"
    if edit.has_audio(src):
        a = f"{narr};[0:a]aresample=48000,volume=0.12[bgm];[bgm][n]amix=inputs=2:normalize=0:duration=first[aout]"
    else:
        a = f"{narr};[n]apad=whole_dur={dur:.2f}[aout]"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", src,
         "-i", narration_mp3, "-filter_complex", v + ";" + a, "-map", "[vout]", "-map", "[aout]", "-t", f"{dur:.2f}",
         "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out],
        check=True,
    )
    return out


def load_series(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"current": None, "done": [], "topic_index": 0}


def save_series(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def next_part(cfg: dict, series_path: str, footage: list, work: str, out_dir: str):
    """Make the next part of the current series (planning a new series when needed).

    Returns (meta, path) or None. `meta` has title/description/tags and fields for posted.json.
    Call mark_posted() after a successful upload so a failed upload retries the same part.
    """
    client = anthropic.Anthropic()
    model = cfg["writer_model"]
    data = load_series(series_path)
    cur = data.get("current")
    if not cur or cur["next_part"] > len(cur["tips"]):
        if cur:
            data["done"].append(cur["series_title"])
        topic = TOPICS[data.get("topic_index", 0) % len(TOPICS)]
        data["topic_index"] = data.get("topic_index", 0) + 1
        print(f"planning a new series: {topic}")
        plan = _research(client, model, topic, data["done"])
        if plan is None:
            print("series research came back empty; skipping this slot")
            return None
        cur = {"series_title": plan.series_title, "item_word": plan.item_word, "topic": topic,
               "tips": [t.model_dump() for t in plan.tips], "next_part": 1}
        data["current"] = cur
        save_series(series_path, data)

    part = cur["next_part"]
    tip = Tip(**cur["tips"][part - 1])
    total = len(cur["tips"])
    clip = footage[_pick_footage(client, model, tip, footage)]
    src = twitch.download(clip, os.path.join(work, f"{clip.id}.mp4"))

    said = f"{cur['item_word']} number {part}. {tip.narration}"
    if part < total:
        said += f" Follow for part {part + 1}."
    narration = voice.speak(said, os.path.join(work, "listicle.mp3"), cfg["host"])
    clip_len = edit.probe_duration(src)
    dur = min(max(edit.probe_duration(narration) + 1.2, 9.0), clip_len, 45.0)
    start = max(0.0, min(2.0, clip_len - dur))
    ass = _build_ass(os.path.join(work, "listicle.ass"), cur["series_title"], part, tip.caption,
                     f"gameplay: twitch.tv/{clip.broadcaster_login}", dur, part + 1 if part < total else None)
    os.makedirs(out_dir, exist_ok=True)
    slug = "".join(ch for ch in cur["series_title"].lower() if ch.isalnum())[:30]
    path = render(src, narration, ass, os.path.join(out_dir, f"series-{slug}-part{part}.mp4"), dur, start)

    title = f"{cur['series_title']} (Part {part})"[:95]
    description = (f"{cur['item_word']} {part} of {total}: {tip.caption}\n\n{tip.narration}\n\n"
                   f"Gameplay: {clip.broadcaster_name} on Twitch https://twitch.tv/{clip.broadcaster_login}\n"
                   f"Source: {tip.source_url}")
    tags = ["gta 6", "gta 6 tips", "gta 6 tips and tricks", "gta vi", "gta 6 guide", "leonida",
            cur["item_word"].lower() + "s", clip.broadcaster_name]
    meta = {"title": title, "description": description, "tags": tags,
            "row": {"clip_id": f"series:{slug}:{part}", "format": "series", "series": cur["series_title"],
                    "part": part, "of": total, "footage_clip": clip.id, "streamer": clip.broadcaster_login,
                    "title": title, "hook": tip.caption, "source_url": tip.source_url}}
    return meta, path


def mark_posted(series_path: str) -> None:
    data = load_series(series_path)
    if data.get("current"):
        data["current"]["next_part"] += 1
        save_series(series_path, data)
