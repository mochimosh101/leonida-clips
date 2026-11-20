"""One run: pick the best new GTA 6 clip(s), turn each into a Rico Neon Short, upload, record it.

Usage:
  python -m autoclip.main            # full run (needs all secrets)
  python -m autoclip.main --dry-run  # everything except the YouTube upload; output lands in out/
"""
import argparse
import json
import re
import os
import random
import sys
import tempfile
import datetime as dt

import yaml

from . import captions, edit, learned, twitch, voice, writer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state", "posted.json")  # overridden by config "state_file"
SPOILER_WORDS = re.compile(r"spoiler|cutscene|cinematic|ending|final mission|story mode ending", re.I)
ADULT_WORDS = re.compile(r"strip|naked|nude|nsfw|lap ?dance|private dance|boob|topless|stripper|hooker|sex", re.I)


def load_state() -> list[dict]:
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return []


def save_state(rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(rows, f, indent=2)


def make_short(clip: twitch.Clip, cfg: dict, work: str, recent: list[dict] | None = None):
    """Returns (copy, [(path, variant)]) where variant is "normal", "uncensored" or "censored"."""
    src = twitch.download(clip, os.path.join(work, f"{clip.id}.mp4"))
    transcript, words = captions.transcribe(src, language=cfg.get("whisper_language"))
    frames = edit.sample_frames(src, work)  # lets Claude spot nudity that isn't in the words
    copy = writer.write_copy(cfg["writer_model"], clip.title, clip.broadcaster_name, transcript, frames,
                             recent, cfg.get("writer_language", ""), learned.writer_notes(cfg))
    if copy is None:
        print(f"skip {clip.id}: writer declined")
        return None
    if copy.spoiler or SPOILER_WORDS.search(clip.title):
        print(f"skip {clip.id}: cutscene/story spoiler (Rockstar takedown risk)")
        return None
    if ADULT_WORDS.search(clip.title):
        copy.adult = True
    policy = cfg.get("adult_clips", "skip")
    if copy.adult and policy == "skip":
        print(f"skip {clip.id}: adult content")
        return None

    # Daily reviewer's odds (state/learned.json): styles that get more views are picked more often
    caption_style = learned.pick(cfg, "caption_style", captions.CAPTION_STYLES)
    copy.__dict__["caption_style"] = caption_style  # logged in posted.json for the weekly comparison
    # YouTube "altered or synthetic content" label: off unless the video has realistic AI imagery (Mochi 2026-11-19)
    copy.__dict__["synthetic_label"] = bool(cfg.get("synthetic_label", False))
    host = cfg["host"]
    hook_mp3 = voice.speak(copy.hook_line, os.path.join(work, "hook.mp3"), host)
    verdict_mp3 = voice.speak(copy.verdict_line, os.path.join(work, "verdict.mp3"), host)

    dur = min(edit.probe_duration(src), cfg["max_duration_s"])
    mid_mp3 = mid_at = None
    if copy.mid_line and dur >= 20:  # more of Rico in every Short = more original content
        mid_mp3 = voice.speak(copy.mid_line, os.path.join(work, "mid.mp3"), host)
        mid_at = edit.quiet_spot([w for w in words if w.start < dur], dur)
    ass = captions.build_ass(
        [w for w in words if w.start < dur], copy.on_screen_hook, os.path.join(work, "caps.ass"),
        credit=f"twitch.tv/{clip.broadcaster_login}", duration=dur, style=caption_style,
    )
    out_dir = os.path.join(ROOT, "out")
    os.makedirs(out_dir, exist_ok=True)
    avatar = os.path.join(ROOT, host["avatar_path"])

    def _render(source, name):
        return edit.render(source, ass, hook_mp3, verdict_mp3, os.path.join(out_dir, name),
                           cfg["max_duration_s"], avatar, mid_mp3=mid_mp3, mid_at=mid_at)

    if not copy.adult:
        return copy, [(_render(src, f"{clip.id}.mp4"), "normal")]

    variants = [(_render(src, f"{clip.id}-uncensored.mp4"), "uncensored")]
    if policy == "both":
        from . import censor
        clean = os.path.join(work, f"{clip.id}-censored-src.mp4")
        hits = censor.censor(src, clean)
        print(f"censor {clip.id}: blurred {hits} frames")
        if hits:
            variants.append((_render(clean, f"{clip.id}-censored.mp4"), "censored"))
        else:
            print(f"censor {clip.id}: nothing detected to blur, posting uncensored only")
    return copy, variants


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--count", type=int, default=0, help="Shorts to make this run (default: clips_per_run)")
    ap.add_argument("--mode", choices=["any", "family", "adult", "series"], default="any",
                    help="family = skip naked/sexual clips; adult = only naked/sexual clips; "
                         "series = next part of a tips/mistakes series")
    ap.add_argument("--config", default="config.yaml", help="e.g. config.es.yaml for the Spanish channel")
    ap.add_argument("--clip-id", default="", help="Make these Twitch clip ids (comma-separated), even if posted before")
    args = ap.parse_args()

    with open(os.path.join(ROOT, args.config)) as f:
        cfg = yaml.safe_load(f)
    if cfg.get("state_file"):
        global STATE
        STATE = os.path.join(ROOT, cfg["state_file"])

    if args.mode == "family":
        cfg["adult_clips"] = "skip"
    elif args.mode == "adult" and cfg.get("adult_clips", "skip") == "skip":
        cfg["adult_clips"] = "public"

    state = load_state()
    posted = {r["clip_id"] for r in state}
    if args.mode == "series":
        return run_series(cfg, args, state)
    if args.clip_id:
        candidates = twitch.clips_by_id([c.strip() for c in args.clip_id.split(",") if c.strip()])
    else:
        candidates = [c for c in twitch.top_clips(cfg) if twitch.eligible(c, cfg, posted)]
    if args.mode == "adult" and not args.clip_id:
        adult = [c for c in candidates if ADULT_WORDS.search(c.title)]
        if adult:
            candidates = adult
        else:  # no 18+ clip today: fill the slot with a family-friendly one instead
            print("no 18+ clips found; using a family-friendly clip for this slot")
            cfg["adult_clips"] = "skip"
    print(f"{len(candidates)} eligible clips (mode: {args.mode})")

    made = 0
    for clip in candidates:
        if cfg.get("adult_clips", "skip") == "skip" and ADULT_WORDS.search(clip.title):
            print(f"skip {clip.id}: adult title")
            continue
        if made >= (args.count or cfg["clips_per_run"]):
            break
        with tempfile.TemporaryDirectory() as work:
            try:
                recent = [r for r in state if not r.get("dry_run")][-9:]
                result = make_short(clip, cfg, work, recent)
            except Exception as e:  # one bad clip shouldn't stop the run
                print(f"skip {clip.id}: {e}", file=sys.stderr)
                continue
        if result is None:
            continue
        copy, variants = result
        yt = cfg["youtube"]
        description = (
            f"{copy.description}\n\n"
            + yt.get("clip_credit", "Clip from {name} on Twitch:").format(name=clip.broadcaster_name)
            + f" https://twitch.tv/{clip.broadcaster_login}\n\n{yt['description_footer']}"
        )
        tags = list(dict.fromkeys(copy.tags + yt["base_tags"] + [clip.broadcaster_name]))
        for path, variant in variants:
            title = copy.title
            if variant == "uncensored" and len(variants) > 1:
                title = f"{copy.title[:85]} (Uncensored 18+)"
            elif variant == "censored":
                title = f"{copy.title[:90]} (Censored)"
            age_restricted = variant == "uncensored"
            video_id = None
            if not args.dry_run:
                yv = yt
                if age_restricted and cfg.get("adult_clips") == "private":
                    yv = {**yt, "privacy_status": "private"}  # Mochi sets 18+ in Studio, then publishes
                try:
                    video_id = upload_short(path, title, description, tags, yv, age_restricted=age_restricted,
                                            synthetic_label=copy.__dict__.get("synthetic_label", False))
                except Exception as e:
                    if type(e).__name__ != "UploadLimitReached":
                        raise
                    print("YouTube daily upload limit reached for this channel; stopping this run "
                          "(the clip stays unused and will be tried again in a later slot).")
                    save_state(state)
                    return 0
            state.append({
                "clip_id": clip.id, "streamer": clip.broadcaster_login, "views": clip.view_count,
                "title": title, "hook": copy.hook_line, "mid": copy.mid_line, "verdict": copy.verdict_line,
                "hook_style": copy.hook_style, "verdict_style": copy.verdict_style,
                "caption_style": copy.__dict__.get("caption_style"),
                "synthetic_label": copy.__dict__.get("synthetic_label"),
                "adult": copy.adult, "variant": variant, "youtube_id": video_id, "dry_run": args.dry_run,
                "posted_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            if not args.dry_run:
                save_state(state)  # save after every upload so a later failure can't cause a repost
            print(f"made {path} -> {video_id or 'dry run'} | {title}")
        made += 1

    if not args.dry_run:
        save_state(state)
    return 0


def run_series(cfg: dict, args, state: list[dict]) -> int:
    """One part of the current tips/mistakes series (see listicle.py)."""
    from . import listicle
    series_path = os.path.join(ROOT, cfg.get("series_file", "state/series.json"))
    footage = [c for c in twitch.top_clips(cfg)
               if c.view_count >= cfg["min_views"] and not ADULT_WORDS.search(c.title)
               and not SPOILER_WORDS.search(c.title)][:25]
    used = {r.get("footage_clip") for r in state[-12:] if r.get("format") == "series"}
    fresh = [c for c in footage if c.id not in used]
    footage = fresh if len(fresh) >= 3 else footage  # vary the gameplay between parts
    if not footage:
        print("no usable gameplay clips right now; skipping this slot")
        return 0
    with tempfile.TemporaryDirectory() as work:
        made = listicle.next_part(cfg, series_path, footage, work, os.path.join(ROOT, "out"))
        if made is None:
            return 0
        meta, path = made
        video_id = None
        if not args.dry_run:
            try:
                video_id = upload_short(path, meta["title"], meta["description"], meta["tags"], cfg["youtube"],
                                        synthetic_label=bool(cfg.get("synthetic_label", False)))
            except Exception as e:
                if type(e).__name__ != "UploadLimitReached":
                    raise
                print("YouTube daily upload limit reached; this part will be posted in a later slot.")
                return 0
            listicle.mark_posted(series_path)
            state.append({**meta["row"], "youtube_id": video_id, "dry_run": False,
                          "posted_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
            save_state(state)
        print(f"made {path} -> {video_id or 'dry run'} | {meta['title']}")
    return 0


def upload_short(path, title, description, tags, yt, age_restricted=False, synthetic_label=False):
    from . import youtube
    return youtube.upload(path, title, description, tags, yt, age_restricted=age_restricted,
                          synthetic_label=synthetic_label)


if __name__ == "__main__":
    sys.exit(main())
