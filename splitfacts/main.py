"""Split-screen "did you know" GTA 6 fact Shorts.

Layout (Mochi's reference TikTok, 2026-11-24): top half = GTA 6 gameplay (today's Twitch clips, muted),
bottom half = our own block-parkour run (splitfacts/parkour.py, drawn by code so it can't get a copyright
claim), a voice reads one surprising fact, and each spoken word pops up big in the middle of the screen.

Facts are researched with web search in batches (GTA 6 came out after the model's training, so nothing
is guessed) and queued in state/facts.json; each run posts the next one.

  python -m splitfacts.main --dry-run         # make the Short into out/ without uploading
"""
import argparse
import asyncio
import datetime as dt
import json
import os
import random
import subprocess
import sys
import tempfile

import yaml
from pydantic import BaseModel, Field

from autoclip import edit
from . import parkour

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H, HALF = 1080, 1920, 960


class Fact(BaseModel):
    hook: str = Field(description="Spoken first line, max 12 words, starts with 'Did you know' or a curiosity "
                                  "opener like 'GTA 6 hides a detail most players miss'")
    narration: str = Field(description="The rest of what the voice says: 45 to 70 words, plain casual English, "
                                       "explains the fact and why it's cool, ends with a short punchline")
    title: str = Field(description="YouTube title, max 70 characters, curiosity style, includes 'GTA 6'")
    banner: str = Field(description="Short white-box text shown at the top for the first seconds, max 28 characters")
    footage: str = Field(description="What gameplay would fit, e.g. 'driving in Vice City', 'police chase'")
    source_url: str = Field(description="The page this fact came from")


class FactBatch(BaseModel):
    facts: list[Fact]


RESEARCH_PROMPT = """GTA 6 (Grand Theft Auto VI) is out now. Search the web (news sites, guides, Reddit, X posts
covered by news) for {n} surprising, real, verifiable GTA 6 details for a "Did you know?" Shorts channel:
hidden details, realistic systems, easter eggs, map facts, wildlife, NPC behaviour, physics, records,
behind-the-scenes development facts. Only things you found in a source and that are about GTA 6 itself.
No story spoilers (missions, endings, character deaths), no glitches/exploits, nothing sexual.
Skip anything already used: {done}.
For each: the fact, a one-line why-it's-cool, what gameplay would show it, and the source URL."""

FORMAT_PROMPT = """Turn these researched GTA 6 facts into scripts for a split-screen "Did you know" Shorts
channel. The voice is a hyped but natural narrator talking to a friend: short sentences, no greeting, no
channel name, no emoji, no "subscribe" (the ending is added automatically). Make the hook instantly
intriguing; put the most surprising part early. Keep only facts that name a source URL.

Research notes:
{notes}"""


# ---------- facts queue ----------

def load_state(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"queue": [], "done": [], "posted": []}


def save_state(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def research(cfg: dict, done: list[str]) -> list[Fact]:
    import anthropic
    client = anthropic.Anthropic()
    model = cfg["writer_model"]
    messages = [{"role": "user", "content": RESEARCH_PROMPT.format(
        n=cfg.get("facts_per_batch", 10), done="; ".join(done[-40:]) or "none")}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}]
    resp = client.messages.create(model=model, max_tokens=16000, output_config={"effort": "medium"},
                                  messages=messages, tools=tools)
    for _ in range(5):  # long searches pause; send them back to continue
        if resp.stop_reason != "pause_turn":
            break
        messages = messages[:1] + [{"role": "assistant", "content": resp.content}]
        resp = client.messages.create(model=model, max_tokens=16000, output_config={"effort": "medium"},
                                      messages=messages, tools=tools)
    notes = "\n".join(b.text for b in resp.content if b.type == "text").strip()
    if not notes:
        return []
    batch = client.messages.parse(
        model=model, max_tokens=8000, output_config={"effort": "low"},
        messages=[{"role": "user", "content": FORMAT_PROMPT.format(notes=notes)}],
        output_format=FactBatch,
    ).parsed_output
    return [f for f in (batch.facts if batch else []) if f.source_url.startswith("http")]


# ---------- voice with word timings ----------

def speak(text: str, out_mp3: str, v: dict) -> list[tuple[float, float, str]]:
    """Edge voice + the exact time each word is spoken (for the one-word captions).

    Edge's service sometimes answers with no audio; try again, then fall back to similar voices.
    If no word timings come back, spread the words evenly over the audio.
    """
    import edge_tts

    async def run(voice, boundary):
        kw = {"boundary": "WordBoundary"} if boundary else {}
        tts = edge_tts.Communicate(text, voice, rate=v["edge_rate"], pitch=v["edge_pitch"], **kw)
        words = []
        with open(out_mp3, "wb") as f:
            async for chunk in tts.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    s = chunk["offset"] / 1e7
                    words.append((s, s + chunk["duration"] / 1e7, chunk["text"]))
        return words

    last = None
    for voice in [v["edge_voice"]] + v.get("fallback_voices", ["en-US-AndrewNeural", "en-US-BrianNeural"]):
        for boundary in (True, True, False):
            try:
                words = asyncio.run(run(voice, boundary))
            except TypeError:       # older edge-tts has no boundary option (it always sends words)
                continue
            except Exception as e:  # noqa: BLE001  (NoAudioReceived, network hiccups)
                last = e
                print(f"edge voice {voice} failed ({type(e).__name__}); retrying")
                continue
            if not words:
                toks = text.split()
                d = edit.probe_duration(out_mp3)
                step = d / max(1, len(toks))
                words = [(i * step, (i + 1) * step, t.strip(".,!?")) for i, t in enumerate(toks)]
            print(f"voice: {voice}")
            return words
    raise RuntimeError(f"no Edge voice worked: {last}")


# ---------- captions ----------

def _ts(t: float) -> str:
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def _esc(s: str) -> str:
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def _ascii(s: str) -> str:
    """Drop emoji: the caption font has no emoji glyphs and would draw empty boxes."""
    return "".join(ch for ch in s if ord(ch) < 0x2000).strip()


def build_ass(path: str, words, banner: str, dur: float, lead: float) -> str:
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        "Style: Word,Montserrat Black,118,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,9,4,5,40,40,0,1",
        "Style: Hot,Montserrat Black,118,&H0000E5FF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,9,4,5,40,40,0,1",
        "Style: Banner,Montserrat ExtraBold,64,&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,3,18,0,8,80,80,150,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        f"Dialogue: 0,{_ts(0)},{_ts(min(dur, 3.2))},Banner,,0,0,0,,{{\\fad(0,250)}}{_esc(_ascii(banner))}",
    ]
    pop = r"{\pos(540,960)\fscx125\fscy125\t(0,90,\fscx100\fscy100)}"
    for i, (s, e, w) in enumerate(words):
        nxt = words[i + 1][0] if i + 1 < len(words) else e + 0.4
        end = max(e, nxt)
        style = "Hot" if (any(ch.isdigit() for ch in w) or w.isupper() and len(w) > 1) else "Word"
        lines.append(f"Dialogue: 1,{_ts(s + lead)},{_ts(end + lead)},{style},,0,0,0,,{pop}{_esc(w.upper())}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


# ---------- render ----------

def render(top_src: str, bottom_src: str, voice_mp3: str, ass_path: str, out: str, dur: float, lead: float,
           top_start: float = 0.0) -> str:
    ass = ass_path.replace("\\", "/").replace(":", "\\:")
    ms = int(lead * 1000)
    v = (f"[0:v]scale={W}:{HALF}:force_original_aspect_ratio=increase,crop={W}:{HALF},setsar=1,fps=30[top];"
         f"[1:v]scale={W}:{HALF},setsar=1,fps=30[bot];"
         f"[top][bot]vstack=inputs=2[st];"
         f"[st]drawbox=x=0:y={HALF - 3}:w={W}:h=6:color=black@0.9:t=fill[base];"
         f"[base]ass='{ass}'[vout]")
    a = f"[2:a]adelay={ms}|{ms},volume=1.5,apad=whole_dur={dur:.2f}[aout]"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-stream_loop", "-1", "-ss", f"{top_start:.2f}", "-i", top_src,
         "-i", bottom_src, "-i", voice_mp3,
         "-filter_complex", v + ";" + a, "-map", "[vout]", "-map", "[aout]", "-t", f"{dur:.2f}",
         "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out],
        check=True,
    )
    return out


ENDINGS = [
    "Follow for more GTA 6 facts.",
    "Follow, there's way more where that came from.",
    "Which one did you already know? Follow for part two.",
]


def make(cfg: dict, fact: Fact, top_src: str, work: str, out_path: str, seed: int | None = None) -> dict:
    ending = random.choice(ENDINGS)
    said = f"{fact.hook} {fact.narration} {ending}"
    mp3 = os.path.join(work, "voice.mp3")
    words = speak(said, mp3, cfg["voice"])
    lead = 0.25
    dur = min(58.0, edit.probe_duration(mp3) + lead + 0.6)
    bottom = parkour.make(os.path.join(work, "parkour.mp4"), seconds=dur + 0.5, seed=seed)
    ass = build_ass(os.path.join(work, "words.ass"), words, fact.banner, dur, lead)
    top_len = edit.probe_duration(top_src)
    start = random.uniform(0, max(0.0, top_len - dur)) if top_len > dur else 0.0
    render(top_src, bottom, mp3, ass, out_path, dur, lead, start)
    return {"duration": round(dur, 1), "ending": ending, "spoken": said}


# ---------- one run ----------

def pick_clip(cfg: dict, used: set[str]):
    from autoclip import twitch
    clips = [c for c in twitch.top_clips(cfg) if twitch.eligible(c, cfg, used) and c.duration >= 15]
    if not clips:
        clips = [c for c in twitch.top_clips(cfg) if c.duration >= 10]
    return clips[:12]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.facts.yaml")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--top-video", help="Use this local file for the top half instead of a Twitch clip (testing)")
    a = ap.parse_args()
    with open(os.path.join(ROOT, a.config)) as f:
        cfg = yaml.safe_load(f)
    state_path = os.path.join(ROOT, cfg["state_file"])
    data = load_state(state_path)

    if not data["queue"]:
        print("researching a new batch of facts")
        facts = research(cfg, data["done"])
        if not facts:
            print("fact research came back empty; skipping this slot")
            return 0
        data["queue"] = [x.model_dump() for x in facts]
        save_state(state_path, data)
        for x in facts:
            print(f"  - {x.title} | {x.source_url}")
    fact = Fact(**data["queue"][0])

    work = tempfile.mkdtemp(prefix="facts-")
    clip = None
    if a.top_video:
        top = a.top_video
    else:
        from autoclip import twitch
        used = {p.get("footage_clip") for p in data["posted"]}
        clips = pick_clip(cfg, used)
        if not clips:
            print("no GTA 6 Twitch clips for the top half right now; skipping")
            return 0
        clip = random.choice(clips[:5])
        top = twitch.download(clip, os.path.join(work, f"{clip.id}.mp4"))

    os.makedirs(os.path.join(ROOT, "out"), exist_ok=True)
    n = len(data["posted"]) + 1
    out = os.path.join(ROOT, "out", f"fact-{n}.mp4")
    info = make(cfg, fact, top, work, out, seed=random.randrange(10**6))
    print(f"made {out} ({info['duration']}s): {fact.title}")

    credit = f"\nTop gameplay: {clip.broadcaster_name} on Twitch https://twitch.tv/{clip.broadcaster_login}" if clip else ""
    description = (f"{fact.hook} {fact.narration}\n{credit}\nSource: {fact.source_url}\n"
                   f"Parkour gameplay: made by us.\n\n#GTA6 #GTAVI #GTA6Facts #DidYouKnow #Shorts")
    tags = cfg["youtube"]["base_tags"] + ([clip.broadcaster_name] if clip else [])
    if a.dry_run:
        print("dry run: not uploading")
        return 0
    if not os.environ.get("YOUTUBE_REFRESH_TOKEN"):
        print("facts channel not connected yet (YOUTUBE_REFRESH_TOKEN_FACTS missing); not uploading")
        return 0
    from autoclip import youtube
    try:
        vid = youtube.upload(out, fact.title, description, tags, cfg["youtube"],
                             synthetic_label=cfg.get("synthetic_label", False))
    except youtube.UploadLimitReached:
        print("YouTube daily upload limit reached; this fact will be posted in a later slot")
        return 0
    print(f"uploaded https://youtube.com/shorts/{vid}")
    data["queue"].pop(0)
    data["done"].append(fact.title)
    data["posted"].append({"video_id": vid, "title": fact.title, "hook": fact.hook, "source_url": fact.source_url,
                           "footage_clip": clip.id if clip else None, "streamer": clip.broadcaster_login if clip else None,
                           "ending": info["ending"], "duration": info["duration"], "format": "facts",
                           "posted_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    save_state(state_path, data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
