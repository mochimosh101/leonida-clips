"""Send Rica's clips from your Downloads folder to GitHub automatically.

Any file in Downloads named rica-<name>.mp4 / .jpg / .png goes to ricotrader/clips/ on the bot's branch
(rica-walkaway.mp4 -> ricotrader/clips/walkaway.mp4, rica-base.jpg stays rica-base.jpg). GitHub then
re-renders the videos by itself.

  python rica_uploader.py            # upload what's there now
  python rica_uploader.py --watch    # keep watching (checks every 30 s)
  python rica_uploader.py --install  # start watching automatically every time you log in to Windows

While watching it also listens on http://127.0.0.1:8765 (this PC only) so grok.com can hand clips over
directly, with no download or Save prompt, and it updates itself from GitHub when a newer version lands.

Uses your GitHub login from the GitHub CLI (gh) or the one Git already saved. Nothing secret is printed.
"""
import argparse
import base64
import http.server
import re
import threading
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
LOG = os.path.join(os.path.expanduser("~"), "rica_uploader.log")
VERSION = 2
PORT = 8765
ALLOWED_ORIGINS = ("https://grok.com", "https://www.grok.com")
NAME_OK = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    try:
        print(line, flush=True)
    except Exception:                      # pythonw has no console
        pass
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def token():
    gh = shutil.which("gh")
    if gh:
        r = subprocess.run([gh, "auth", "token"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    try:
        r = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                           capture_output=True, text=True, timeout=60, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
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
        log(f"{os.path.basename(fn)}: upload failed (HTTP {r.status_code})")
        return False
    state[fn] = digest
    json.dump(state, open(STATE, "w"))
    log(f"{os.path.basename(fn)}: uploaded to {path}")
    return True


def scan(tok):
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    files = [f for ext in ("mp4", "jpg", "png") for f in glob.glob(os.path.join(DOWNLOADS, f"rica-*.{ext}"))
             if " " not in os.path.basename(f)]      # skip browser duplicates like "rica-pain (1).mp4"
    for f in sorted(files):
        if time.time() - os.path.getmtime(f) > 3:          # skip files still downloading
            upload(f, tok, state)


class Receiver(http.server.BaseHTTPRequestHandler):
    """grok.com page -> POST /clip?name=say-x&ext=mp4 (video bytes). Saved to Downloads and uploaded at once."""
    tok = None

    def _cors(self):
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")

    def _reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        self._reply(200, {"ok": True, "version": VERSION})

    def do_POST(self):
        from urllib.parse import urlparse, parse_qs
        if self.headers.get("Origin", "") not in ALLOWED_ORIGINS:
            return self._reply(403, {"ok": False, "error": "origin"})
        q = parse_qs(urlparse(self.path).query)
        name, ext = q.get("name", [""])[0], q.get("ext", ["mp4"])[0]
        if not NAME_OK.match(name) or ext not in ("mp4", "jpg", "png"):
            return self._reply(400, {"ok": False, "error": "bad name"})
        n = int(self.headers.get("Content-Length", "0"))
        if n <= 0 or n > 200_000_000:
            return self._reply(400, {"ok": False, "error": "size"})
        data = self.rfile.read(n)
        fn = os.path.join(DOWNLOADS, f"rica-{name}.{ext}")
        with open(fn, "wb") as f:
            f.write(data)
        state = json.load(open(STATE)) if os.path.exists(STATE) else {}
        ok = upload(fn, self.tok, state)
        log(f"received {os.path.basename(fn)} from grok.com ({n} bytes)")
        self._reply(200, {"ok": True, "uploaded": ok, "path": target(fn), "bytes": n})

    def log_message(self, *a):
        pass


def serve(tok):
    Receiver.tok = tok
    try:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Receiver)
    except OSError as e:
        log(f"receiver not started: {e!r}")
        return
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"receiver listening on 127.0.0.1:{PORT}")


def self_update(tok):
    """Replace this script with a newer VERSION from the bot's branch, then restart."""
    h = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github.raw+json"}
    r = requests.get(f"https://api.github.com/repos/{REPO}/contents/scripts/rica_uploader.py",
                     headers=h, params={"ref": BRANCH}, timeout=60)
    if r.status_code != 200:
        return
    m = re.search(r"^VERSION = (\d+)", r.text, re.M)
    if not m or int(m.group(1)) <= VERSION:
        return
    me = os.path.abspath(__file__)
    with open(me, "w", encoding="utf-8") as f:
        f.write(r.text)
    log(f"updated to version {m.group(1)}, restarting")
    os.execv(sys.executable, [sys.executable, me] + sys.argv[1:])


def install():
    py = sys.executable.replace("python.exe", "pythonw.exe")
    me = os.path.abspath(__file__)
    dst = os.path.join(os.path.expanduser("~"), "rica_uploader.py")
    if me != dst:
        shutil.copy(me, dst)
    # Startup-folder launcher: works without admin rights (schtasks ONLOGON needs admin)
    startup = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
    os.makedirs(startup, exist_ok=True)
    with open(os.path.join(startup, "RicaClipUploader.cmd"), "w") as f:
        f.write(f'@start "" "{py}" "{dst}" --watch\r\n')
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
    log(f"uploader v{VERSION} started" + (" (watching)" if a.watch else ""))
    if a.watch:
        serve(tok)
    last_update = 0
    while True:
        if a.watch and time.time() - last_update > 1800:
            last_update = time.time()
            try:
                self_update(tok)
            except Exception as e:
                log(f"update check failed: {e!r}")
        try:
            scan(tok)
        except Exception as e:             # never die in the background; try again next round
            log(f"error: {e!r}")
        if not a.watch:
            return 0
        time.sleep(30)


if __name__ == "__main__":
    sys.exit(main())
