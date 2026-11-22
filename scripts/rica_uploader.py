"""Send Rica's clips from your Downloads folder to GitHub automatically.

Any file in Downloads named rica-<name>.mp4 / .jpg / .png goes to ricotrader/clips/ on the bot's branch
(rica-walkaway.mp4 -> ricotrader/clips/walkaway.mp4, rica-base.jpg stays rica-base.jpg). GitHub then
re-renders the videos by itself.

  python rica_uploader.py            # upload what's there now
  python rica_uploader.py --watch    # keep watching (checks every 30 s)
  python rica_uploader.py --install  # start watching automatically every time you log in to Windows

Uses your GitHub login from the GitHub CLI (gh) or the one Git already saved. Nothing secret is printed.
"""
import argparse
import base64
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

import requests

REPO = "mochimosh101/leonida-clips"
BRANCH = "claude/project-thread-c75y3q"
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
STATE = os.path.join(os.path.expanduser("~"), ".rica_uploader.json")


def token():
    gh = shutil.which("gh")
    if gh:
        r = subprocess.run([gh, "auth", "token"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    try:
        r = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                           capture_output=True, text=True, timeout=60)
        for line in r.stdout.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    sys.exit("No GitHub login found. Run 'gh auth login' once, then try again.")


def target(fn):
    name = os.path.basename(fn)
    return "ricotrader/clips/" + (name if name.startswith("rica-base") else name[len("rica-"):])


def upload(fn, tok, state):
    data = open(fn, "rb").read()
    digest = hashlib.sha256(data).hexdigest()
    if state.get(fn) == digest:
        return False
    path = target(fn)
    h = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    cur = requests.get(url, headers=h, params={"ref": BRANCH}, timeout=60)
    body = {"message": f"Add Rica clip {os.path.basename(path)}", "branch": BRANCH,
            "content": base64.b64encode(data).decode()}
    if cur.status_code == 200:
        body["sha"] = cur.json()["sha"]
    r = requests.put(url, headers=h, json=body, timeout=300)
    if r.status_code not in (200, 201):
        print(f"{os.path.basename(fn)}: upload failed (HTTP {r.status_code})")
        return False
    state[fn] = digest
    json.dump(state, open(STATE, "w"))
    print(f"{os.path.basename(fn)}: uploaded to {path}")
    return True


def scan(tok):
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    files = [f for ext in ("mp4", "jpg", "png") for f in glob.glob(os.path.join(DOWNLOADS, f"rica-*.{ext}"))]
    for f in sorted(files):
        if time.time() - os.path.getmtime(f) > 3:          # skip files still downloading
            upload(f, tok, state)


def install():
    py = sys.executable.replace("python.exe", "pythonw.exe")
    me = os.path.abspath(__file__)
    dst = os.path.join(os.path.expanduser("~"), "rica_uploader.py")
    if me != dst:
        shutil.copy(me, dst)
    cmd = f'"{py}" "{dst}" --watch'
    r = subprocess.run(["schtasks", "/Create", "/F", "/SC", "ONLOGON", "/TN", "RicaClipUploader", "/TR", cmd],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("Couldn't add the startup task: " + r.stderr.strip())
    subprocess.Popen([py, dst, "--watch"], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    print("Installed. The uploader runs in the background now and every time you log in.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--install", action="store_true")
    a = ap.parse_args()
    tok = token()
    if a.install:
        scan(tok)
        install()
        return 0
    while True:
        scan(tok)
        if not a.watch:
            return 0
        time.sleep(30)


if __name__ == "__main__":
    sys.exit(main())
