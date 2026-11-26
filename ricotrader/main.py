"""Post the next Rico trading Short.

Episodes (JSON, see render.py) are written into ricotrader/queue/ from Mochi's real Desk Trader data.
This picks the oldest queued episode, renders it, uploads it to the Rico trading channel and moves
the JSON to ricotrader/posted/ with the video id.

  python -m ricotrader.main             # render + upload next episode
  python -m ricotrader.main --dry-run   # render only (out/rico-*.mp4)
  python -m ricotrader.main --episode ricotrader/episodes/sample-win-rate.json --dry-run
"""
import argparse
import glob
import json
import os
import shutil

from ricotrader.render import render
from ricotrader.stream import render_stream

DISCLAIMER = ("These are my real trades, shown for education and entertainment only. "
              "Not financial advice. Trading options and shares can lose money. Do your own research.")

YT = {"category_id": "27", "privacy_status": "public", "made_for_kids": False}  # 27 = Education


def describe(ep):
    lines = [ep.get("description", ep["title"]), "", DISCLAIMER, "",
             "Rica is an AI host. The trades and numbers are real results from my own trading account.",
             "", "#trading #daytrading #options #stockmarket #shorts"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--episode")
    a = ap.parse_args()
    path = a.episode or (sorted(glob.glob("ricotrader/queue/*.json")) or [None])[0]
    if not path:
        print("Queue is empty, nothing to post.")
        return
    ep = json.load(open(path))
    os.makedirs("out", exist_ok=True)
    mp4 = os.path.join("out", "rico-" + os.path.basename(path).replace(".json", ".mp4"))
    (render_stream if ep.get("layout") == "stream" else render)(ep, mp4)
    print("rendered", mp4)
    if ep.get("layout") == "stream":
        from ricotrader.qa import check
        errs, notes = check(ep, mp4)
        print("\n".join(notes))
        if errs:                                  # never post a video that could look glitched or wrong
            raise SystemExit("QA FAILED, not uploading:\n- " + "\n- ".join(errs))
    if a.dry_run:
        return
    from autoclip.youtube import upload
    tags = ep.get("tags", []) + ["trading", "day trading", "options trading", "trading lessons", "stock market"]
    vid = upload(mp4, ep["title"], describe(ep), tags, YT, synthetic_label=False)
    print(f"uploaded https://youtube.com/shorts/{vid}")
    ep["video_id"] = vid
    for old in ep.get("replaces", []):             # a fixed re-make: hide the old glitchy upload only now that the new one is up
        try:
            from autoclip.youtube import _client
            _client().videos().update(part="status", body={"id": old, "status": {
                "privacyStatus": "private", "selfDeclaredMadeForKids": False}}).execute()
            print("set private:", old)
        except Exception as e:
            print("could not set private", old, e)
    dest = os.path.join("ricotrader/posted", os.path.basename(path))
    json.dump(ep, open(dest, "w"), indent=2)
    if path.startswith("ricotrader/queue/"):
        os.remove(path)


if __name__ == "__main__":
    main()
