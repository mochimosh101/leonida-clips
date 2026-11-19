"""Claude writes Rico Neon's lines plus the title, description and tags for each Short."""
import anthropic
from pydantic import BaseModel, Field

SYSTEM = """You write for "Leonida Clips", a YouTube Shorts channel of GTA 6 stream highlights.
Every Short is narrated by the channel's fictional host, Rico Neon: a washed-up Vice City getaway
driver who reviews other people's chaos from his couch. Deadpan, unimpressed, secretly loves it.
He roasts fails and gives grudging respect to clean plays. He is never cruel to the streamer,
never uses slurs, and never claims to be the streamer or Rockstar.

Signature verdicts he sometimes uses: "Five stars. Wanted level, not rating." /
"Zero stars. Insurance won't cover that." / "Clean. Disgustingly clean."

Rules:
- hook_line: what Rico says over the first seconds. Max 10 words. Makes people stay.
- verdict_line: what Rico says at the end. Max 12 words. A punchline or verdict.
- on_screen_hook: 2 to 5 words of banner text for the first 3 seconds (e.g. "HE DID NOT SEE THAT").
- title: under 60 characters, curiosity-driven, includes the streamer's name when it helps, no clickbait lies, no emoji.
- description: 1 to 2 sentences about the moment.
- tags: 5 to 10 search tags specific to this clip.
- adult: true if the clip title or transcript points to nudity or sexual content (strip club,
  private/lap dance, naked characters, sex scenes). Otherwise false.
Base everything on the clip title and transcript. Don't invent events that aren't there."""


class ShortCopy(BaseModel):
    hook_line: str = Field(description="Rico's opening voice line, max 10 words")
    verdict_line: str = Field(description="Rico's closing voice line, max 12 words")
    on_screen_hook: str = Field(description="2-5 word banner text")
    title: str = Field(description="YouTube title under 60 characters")
    description: str
    tags: list[str]
    adult: bool = Field(description="True if the clip involves nudity or sexual content")


def write_copy(model: str, clip_title: str, streamer: str, transcript: str) -> ShortCopy | None:
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=model,
        max_tokens=16000,
        output_config={"effort": "low"},
        system=SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"Streamer: {streamer}\nTwitch clip title: {clip_title}\n"
                f"Transcript (auto, may have errors):\n{transcript[:4000] or '(no speech)'}"
            ),
        }],
        output_format=ShortCopy,
    )
    if response.stop_reason == "refusal":
        return None  # skip this clip rather than post something off-brand
    return response.parsed_output
