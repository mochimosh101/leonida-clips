"""One run: pick the best new GTA 6 clip(s), turn each into a Rico Neon Short, upload, record it.

Usage:
  python -m autoclip.main            # full run (needs all secrets)
  python -m autoclip.main --dry-run  # everything except the YouTube upload; output lands in out/
"""
import argparse
import json
import os
import sys
import tempfile

import yaml

from . import captions, edit, twitch, voice, writer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state", "posted.json")


def load_state() -> list[dict]:
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return []


def save_state(rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(rows, f, indent=2)


def make_short(clip: twitch.Clip, cfg: dict, work: str) -> tuple[str, writer.ShortCopy] | None:
    src = twitch.download(clip, os.path.join(work, f"{clip.id}.mp4"))
    transcript, words = captions.transcribe(src)
    copy = writer.write_copy(cfg["writer_model"], clip.title, clip.broadcaster_name, transcript)
    if copy is None:
        print(f"skip {clip.id}: writer declined")
        return None

    host = cfg["host"]
    hook_mp3 = voice.speak(copy.hook_line, os.path.join(work, "hook.mp3"), host)
    verdict_mp3 = voice.speak(copy.verdict_line, os.path.join(work, "verdict.mp3"), host)

    dur = min(edit.probe_duration(src), cfg["max_duration_s"])
    ass = captions.build_ass(
        [w for w in words if w.start < dur], copy.on_screen_hook, os.path.join(work, "caps.ass"),
        credit=f"twitch.tv/{clip.broadcaster_login}", duration=dur,
    )
    out_dir = os.path.join(ROOT, "out")
    os.makedirs(out_dir, exist_ok=True)
    out = edit.render(src, ass, hook_mp3, verdict_mp3, os.path.join(out_dir, f"{clip.id}.mp4"),
                      cfg["max_duration_s"], os.path.join(ROOT, host["avatar_path"]))
    return out, copy


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(os.path.join(ROOT, "config.yaml")) as f:
        cfg = yaml.safe_load(f)

    state = load_state()
    posted = {r["clip_id"] for r in state}
    candidates = [c for c in twitch.top_clips(cfg) if twitch.eligible(c, cfg, posted)]
    print(f"{len(candidates)} eligible clips")

    made = 0
    for clip in candidates:
        if made >= cfg["clips_per_run"]:
            break
        with tempfile.TemporaryDirectory() as work:
            try:
                result = make_short(clip, cfg, work)
            except Exception as e:  # one bad clip shouldn't stop the run
                print(f"skip {clip.id}: {e}", file=sys.stderr)
                continue
        if result is None:
            continue
        path, copy = result
        yt = cfg["youtube"]
        description = (
            f"{copy.description}\n\nClip from {clip.broadcaster_name} on Twitch: "
            f"https://twitch.tv/{clip.broadcaster_login}\n\n{yt['description_footer']}"
        )
        tags = list(dict.fromkeys(copy.tags + yt["base_tags"] + [clip.broadcaster_name]))
        video_id = None
        if not args.dry_run:
            video_id = upload_short(path, copy.title, description, tags, yt)
        state.append({
            "clip_id": clip.id, "streamer": clip.broadcaster_login, "views": clip.view_count,
            "title": copy.title, "hook": copy.hook_line, "verdict": copy.verdict_line,
            "youtube_id": video_id, "dry_run": args.dry_run,
        })
        print(f"made {path} -> {video_id or 'dry run'} | {copy.title}")
        made += 1

    if not args.dry_run:
        save_state(state)
    return 0


def upload_short(path, title, description, tags, yt):
    from . import youtube
    return youtube.upload(path, title, description, tags, yt)


if __name__ == "__main__":
    sys.exit(main())
