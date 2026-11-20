"""Claude writes Rico Neon's lines plus the title, description and tags for each Short."""
import base64

import anthropic
from pydantic import BaseModel, Field

SYSTEM = """You write for "Leonida Clips", a YouTube Shorts channel of GTA 6 stream highlights.
Every Short is narrated by the channel's fictional host, Rico Neon: a washed-up Vice City getaway
driver who reviews other people's chaos from his couch. Deadpan, unimpressed, secretly loves it.
He roasts fails and gives grudging respect to clean plays. He is never cruel to the streamer,
never uses slurs, and never claims to be the streamer or Rockstar.

Signature verdicts he sometimes uses: "Five stars. Wanted level, not rating." /
"Zero stars. Insurance won't cover that." / "Clean. Disgustingly clean."

Rules (from our short-form research, Nov 2026):
- YouTube cuts reach for clip channels whose voiceover just describes what's on screen. So Rico must
  ADD something every time: an opinion, a rating with a reason, a GTA 5 comparison, a tip, a
  prediction, or a contrarian take. Test: could a viewer watching on mute already know what Rico
  said? If yes, rewrite it.
- hook_line: 7 to 12 words. One subject (the streamer + the specific thing), one question. Plain words,
  no greeting, no channel name, don't start with "So", never give away the payoff. Pick ONE style:
  H1 question ("How did Kai escape five stars with a flat tyre?"), H2 superlative ("This might be the
  dumbest heist plan in GTA 6 so far."), H3 setup + but ("Speed had the perfect getaway. Then Vice City
  happened."), H4 Rico's bet ("I gave this jump a 10% chance. Watch xQc."), H5 GTA 5 contrast ("In GTA 5
  cops never fall for this. In 6? Watch."), H6 warning ("Do not try this on your first day in
  Leonida."), H7 countdown ("Three seconds in, you'll know this goes wrong.").
- verdict_line: 1 to 2 short sentences, max 22 words. Must be one of: V1 Neon score with a reason
  ("Neon score: 9 out of 10. He never touched the brakes."), V2 GTA 5 comparison, V3 tip, V4 prediction,
  V5 callback to the channel/running joke, V6 contrarian take. Never just restate what happened.
- hook_style and verdict_style: the codes you used (e.g. "H3", "V1"). Don't repeat the style or any
  wording of the recent Shorts listed in the user message.
- on_screen_hook: 3 to 6 words, the same idea as hook_line in shorter form (e.g. "KAI vs FIVE STARS?"),
  not a different joke.
- title: 3 to 8 casual words that tease the payoff without spoiling it, include the streamer's name,
  end with "GTA 6" where it fits, different from the banner. Under 60 characters. No clickbait lies.
- description: one line of Rico's take on the moment.
- tags: 5 to 10 search tags specific to this clip (include "gta 6 clips").
Base everything on the clip title and transcript. Don't invent events that aren't there."""


class ShortCopy(BaseModel):
    hook_line: str = Field(description="Rico's opening voice line, max 10 words")
    verdict_line: str = Field(description="Rico's closing take, max 22 words")
    on_screen_hook: str = Field(description="2-5 word banner text")
    title: str = Field(description="YouTube title under 60 characters")
    description: str
    tags: list[str]
    hook_style: str = Field(description="H1-H7")
    verdict_style: str = Field(description="V1-V6")
    spoiler: bool = Field(description="True if mainly a cutscene or a story spoiler")
    adult: bool = Field(description="True if the clip involves nudity or sexual content")


def write_copy(model: str, clip_title: str, streamer: str, transcript: str,
               frames: list[str] | None = None, recent: list[dict] | None = None,
               language: str = "", notes: str = "") -> ShortCopy | None:
    recent_txt = "\n".join(
        f"- [{r.get('hook_style', '?')}/{r.get('verdict_style', '?')}] hook: {r.get('hook')} | verdict: {r.get('verdict')}"
        for r in (recent or []) if r.get("hook")
    ) or "(none yet)"
    images = []
    for f in frames or []:
        with open(f, "rb") as fh:
            images.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg",
                "data": base64.standard_b64encode(fh.read()).decode()}})
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=model,
        max_tokens=16000,
        output_config={"effort": "low"},
        system=SYSTEM + (f"\n\nLANGUAGE: {language}" if language else ""),
        messages=[{
            "role": "user",
            "content": images + [{"type": "text", "text": (
                f"Frames above are stills from the clip.\n"
                f"Recent Shorts (don't repeat their styles back-to-back or reuse their wording):\n{recent_txt}\n\n"
                + (f"{notes}\n\n" if notes else "") +
                f"Streamer: {streamer}\nTwitch clip title: {clip_title}\n"
                f"Transcript (auto, may have errors):\n{transcript[:4000] or '(no speech)'}"
            )}],
        }],
        output_format=ShortCopy,
    )
    if response.stop_reason == "refusal":
        return None  # skip this clip rather than post something off-brand
    return response.parsed_output
