"""Transcribe a clip and build bold, word-highlighted Shorts captions (ASS)."""
from dataclasses import dataclass


@dataclass
class Word:
    start: float
    end: float
    text: str


def transcribe(video_path: str, model_size: str = "small", language: str | None = None) -> tuple[str, list[Word]]:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(video_path, word_timestamps=True, vad_filter=True,
                                   language=language or None)
    words: list[Word] = []
    for seg in segments:
        for w in seg.words or []:
            t = w.word.strip()
            if t:
                words.append(Word(w.start, w.end, t))
    return " ".join(w.text for w in words), words


def _ts(t: float) -> str:
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(s: str) -> str:
    return s.replace("\\", "").replace("{", "(").replace("}", ")").upper()


HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Montserrat ExtraBold,86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,5,60,60,0,1
Style: Credit,Montserrat ExtraBold,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,0,2,60,60,120,1
Style: Hook,Montserrat ExtraBold,72,&H00FFFFFF,&H00FFFFFF,&H00B414FF,&H00B414FF,-1,0,0,0,100,100,0,0,3,4,0,8,60,60,170,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

PINK = r"{\c&HB414FF&}"   # BGR for #FF14B4
# Caption looks the bot rotates between, so we can see which one keeps people watching.
# (highlight colour in ASS BGR, words per chunk, font size, pop the spoken word)
CAPTION_STYLES = {
    "A": (r"{\c&HB414FF&}", 3, 86, False),   # pink highlight, 3 words (original)
    "B": (r"{\c&H40D6FF&}", 2, 96, True),    # yellow highlight, 2 words, spoken word pops
    "C": (r"{\c&HFFE500&}", 1, 110, True),   # cyan, one big word at a time, pops
}
WHITE = r"{\c&HFFFFFF&}"


def build_ass(words: list[Word], hook_text: str, out_path: str,
              offset: float = 0.0, per_line: int = 3, caption_y: int = 1290,
              credit: str = "", duration: float = 60.0, style: str = "A") -> str:
    color, per_line, size, pop = CAPTION_STYLES.get(style, CAPTION_STYLES["A"])
    """Captions in 3-word chunks; the word being spoken turns pink. Hook banner on top for 3s."""
    lines = [HEADER.replace("Style: Cap,Montserrat ExtraBold,86,", f"Style: Cap,Montserrat ExtraBold,{size},")]
    if hook_text:
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(3.0)},Hook,,0,0,0,,{_esc(hook_text)}")
    if credit:
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(duration)},Credit,,0,0,0,,{credit}")
    for i in range(0, len(words), per_line):
        chunk = words[i:i + per_line]
        for j, w in enumerate(chunk):
            start = w.start + offset
            end = (chunk[j + 1].start if j + 1 < len(chunk) else w.end) + offset
            text = " ".join(
                ((color + (r"{\fscx118\fscy118}" if pop else "") + _esc(x.text) + WHITE
                  + (r"{\fscx100\fscy100}" if pop else "")) if k == j else _esc(x.text))
                for k, x in enumerate(chunk)
            )
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{{\\pos(540,{caption_y})}}{text}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return out_path
