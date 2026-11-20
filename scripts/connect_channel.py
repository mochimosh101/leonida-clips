"""Connect a YouTube channel to the bot, with no copy and paste.

Run on your own computer:
  pip install google-auth-oauthlib google-api-python-client pynacl requests
  python scripts/connect_channel.py --suffix ES --expect "Español"

What it does:
  1. Finds the Google OAuth client file (client_secret_*.json, newest one in Downloads,
     or --client-json PATH).
  2. Opens Google's sign-in page in your browser. You pick the channel and click Allow.
  3. Checks which channel you picked (stops if it isn't the expected one).
  4. Saves the sign-in straight into the repo's GitHub secrets:
       YOUTUBE_REFRESH_TOKEN_<SUFFIX>, plus YOUTUBE_CLIENT_ID_<SUFFIX> and
       YOUTUBE_CLIENT_SECRET_<SUFFIX> so the workflow uses the same client.
     Uses the GitHub CLI (gh) if it is signed in, otherwise the GitHub login Git already saved.
Nothing secret is printed.
"""
import argparse
import base64
import glob
import json
import os
import shutil
import subprocess
import sys

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
REPO = "mochimosh101/leonida-clips"


def find_client_json(path: str | None) -> str:
    if path:
        return path
    hits = glob.glob(os.path.join(os.path.expanduser("~"), "Downloads", "client_secret_*.json"))
    if not hits:
        sys.exit("No client_secret_*.json found in Downloads. Download it from Google Cloud > Credentials.")
    return max(hits, key=os.path.getmtime)


def sign_in(client_path: str):
    from google_auth_oauthlib.flow import InstalledAppFlow

    info = json.load(open(client_path))
    kind = "installed" if "installed" in info else "web"
    flow = InstalledAppFlow.from_client_secrets_file(client_path, SCOPES)
    port = 0 if kind == "installed" else 8080  # web clients need http://localhost:8080/ registered
    print("A browser window will open. Pick the channel, then click Allow (or Continue).")
    creds = flow.run_local_server(port=port, access_type="offline", prompt="consent select_account",
                                  open_browser=True)
    if not creds.refresh_token:
        sys.exit("Google did not return a refresh token. Run the script again.")
    client = info[kind]
    return creds, client["client_id"], client["client_secret"]


def channel_title(creds) -> str:
    from googleapiclient.discovery import build

    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    items = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
    return items[0]["snippet"]["title"] if items else "(no channel)"


def set_secret_gh(name: str, value: str) -> bool:
    gh = shutil.which("gh")
    if not gh:
        return False
    if subprocess.run([gh, "auth", "status"], capture_output=True).returncode != 0:
        return False
    r = subprocess.run([gh, "secret", "set", name, "--repo", REPO], input=value.encode(),
                       capture_output=True)
    return r.returncode == 0


def git_saved_token() -> str | None:
    try:
        r = subprocess.run(["git", "credential", "fill"], input=b"protocol=https\nhost=github.com\n\n",
                           capture_output=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    for line in r.stdout.decode().splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    return None


def set_secret_api(name: str, value: str, token: str) -> bool:
    import requests
    from nacl import encoding, public

    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    key = requests.get(f"https://api.github.com/repos/{REPO}/actions/secrets/public-key", headers=h, timeout=30)
    if key.status_code != 200:
        return False
    k = key.json()
    box = public.SealedBox(public.PublicKey(k["key"].encode(), encoding.Base64Encoder()))
    enc = base64.b64encode(box.encrypt(value.encode())).decode()
    r = requests.put(f"https://api.github.com/repos/{REPO}/actions/secrets/{name}", headers=h,
                     json={"encrypted_value": enc, "key_id": k["key_id"]}, timeout=30)
    return r.status_code in (201, 204)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-json")
    ap.add_argument("--suffix", default="ES", help="secret name suffix, e.g. ES")
    ap.add_argument("--expect", default="", help="text the channel name must contain")
    args = ap.parse_args()

    creds, client_id, client_secret = sign_in(find_client_json(args.client_json))
    title = channel_title(creds)
    print(f"Signed in to channel: {title}")
    if args.expect and args.expect.lower() not in title.lower():
        sys.exit(f"That's not the expected channel (wanted one containing {args.expect!r}). "
                 "Run again and pick the right channel.")

    secrets = {
        f"YOUTUBE_REFRESH_TOKEN_{args.suffix}": creds.refresh_token,
        f"YOUTUBE_CLIENT_ID_{args.suffix}": client_id,
        f"YOUTUBE_CLIENT_SECRET_{args.suffix}": client_secret,
    }
    token = None
    for name, value in secrets.items():
        ok = set_secret_gh(name, value)
        if not ok:
            token = token or git_saved_token()
            ok = bool(token) and set_secret_api(name, value, token)
        print(f"{name}: {'saved' if ok else 'FAILED'}")
        if not ok:
            sys.exit("Couldn't save to GitHub. Sign in with 'gh auth login' and run again.")
    print("Done. The bot can now post to", title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
