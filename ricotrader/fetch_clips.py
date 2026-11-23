"""Download Rica's Grok clips straight from Grok's asset server by post id, so no browser Save prompt is
ever needed. ricotrader/clips/grok-ids.json maps clip name -> Grok post id; any clip not yet in
ricotrader/clips/ is fetched. Runs inside GitHub Actions before rendering."""
import json
import os
import sys
import time

import requests

USER = "a7801b5c-8c0f-42b0-b331-a3e8cd37f54c"
URL = "https://assets.grok.com/users/{u}/generated/{p}/generated_video.mp4?cache=1"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")


def main(ids_path="ricotrader/clips/grok-ids.json", out_dir="ricotrader/clips"):
    if not os.path.exists(ids_path):
        return 0
    ids = json.load(open(ids_path))
    missing = 0
    for name, post in ids.items():
        dst = os.path.join(out_dir, name + ".mp4")
        if os.path.exists(dst) and os.path.getsize(dst) > 100_000:
            continue
        ok = False
        for attempt in range(3):
            try:
                r = requests.get(URL.format(u=USER, p=post), timeout=60,
                                 headers={"User-Agent": UA, "Referer": "https://grok.com/"})
                if r.status_code == 200 and len(r.content) > 100_000:
                    open(dst, "wb").write(r.content)
                    print(f"fetched {name} ({len(r.content)} bytes)")
                    ok = True
                    break
                print(f"{name}: HTTP {r.status_code}, {len(r.content)} bytes")
            except requests.RequestException as e:
                print(f"{name}: {e}")
            time.sleep(3 * (attempt + 1))
        missing += not ok
    print(f"{missing} clip(s) still missing")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
