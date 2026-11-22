"""Make Rica's realistic webcam clips with xAI's Grok Imagine API (hands-off, runs on GitHub Actions).

  XAI_API_KEY=... python -m ricotrader.clips.make_clips [--only walkaway] [--force]

Reads ricotrader/clips/library.json. Makes the base photo once (rica-base.jpg), then each clip from it
(image-to-video, then extensions). Skips clips that already exist unless --force. Saves ricotrader/clips/<name>.mp4.
"""
import argparse
import base64
import json
import os
import sys
import time

import requests

API = "https://api.x.ai/v1"
DIR = os.path.dirname(os.path.abspath(__file__))


def hdr():
    return {"Authorization": f"Bearer {os.environ['XAI_API_KEY']}", "Content-Type": "application/json"}


def post(path, body):
    r = requests.post(API + path, headers=hdr(), json=body, timeout=120)
    if r.status_code >= 300:
        sys.exit(f"{path} failed: HTTP {r.status_code} {r.text[:400]}")
    return r.json()


def wait_video(rid, label):
    t0 = time.time()
    while time.time() - t0 < 1200:
        time.sleep(6)
        r = requests.get(f"{API}/videos/{rid}", headers=hdr(), timeout=60)
        if r.status_code >= 500:
            continue
        j = r.json()
        st = j.get("status")
        if st == "done":
            print(f"  {label}: done ({j.get('video', {}).get('duration')}s)")
            return j["video"]["url"]
        if st in ("failed", "expired"):
            sys.exit(f"{label} {st}: {j.get('error')}")
    sys.exit(f"{label}: timed out")


def download(url, path):
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    open(path, "wb").write(r.content)


def data_uri(path, mime):
    return f"data:{mime};base64," + base64.b64encode(open(path, "rb").read()).decode()


def make_base(lib, force):
    b = lib["base"]
    if os.path.exists(b["file"]) and not force:
        return
    print("base photo...")
    j = post("/images/generations", {"model": "grok-imagine-image-2.0", "prompt": b["prompt"], "n": 1,
                                     "aspect_ratio": b.get("aspect_ratio", "16:9"), "resolution": "2k",
                                     "response_format": "b64_json"})
    open(b["file"], "wb").write(base64.b64decode(j["data"][0]["b64_json"]))


def make_clip(lib, clip, force):
    out = os.path.join(DIR, f"{clip['name']}.mp4")
    if os.path.exists(out) and not force:
        print(f"{clip['name']}: exists, skipping")
        return
    print(f"{clip['name']}...")
    url = None
    for k, st in enumerate(clip["steps"]):
        prompt = f"{lib['style']} {st['prompt']}"
        if k == 0:
            body = {"model": st.get("model", "grok-imagine-video-1.5"), "prompt": prompt,
                    "image": {"url": data_uri(lib["base"]["file"], "image/jpeg")},
                    "duration": st["duration"], "resolution": st.get("resolution", "720p")}
            if not st.get("audio", False):
                body["generate_audio"] = False
            rid = post("/videos/generations", body)["request_id"]
        else:                                     # continue the same shot (extension keeps continuity)
            rid = post("/videos/extensions", {"model": "grok-imagine-video", "prompt": prompt,
                                              "duration": st["duration"], "video": {"url": url}})["request_id"]
        url = wait_video(rid, f"{clip['name']} step {k + 1}")
    download(url, out)
    print(f"  saved {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if not os.environ.get("XAI_API_KEY"):
        print("XAI_API_KEY not set yet, nothing to do.")
        return 0
    lib = json.load(open(os.path.join(DIR, "library.json")))
    make_base(lib, a.force and not a.only)
    for c in lib["clips"]:
        if not a.only or c["name"] in a.only.split(","):
            make_clip(lib, c, a.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
