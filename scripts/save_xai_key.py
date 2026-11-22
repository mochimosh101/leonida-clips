"""Save your xAI (Grok) API key into the repo's GitHub secrets, with no pasting anywhere.

Run on your own computer, right after you click "Copy" on the new key at console.x.ai:
  pip install pynacl requests
  python scripts/save_xai_key.py

It reads the key from your clipboard, checks it with xAI, saves it as the GitHub secret XAI_API_KEY,
then clears your clipboard. Nothing secret is printed.
"""
import base64
import shutil
import subprocess
import sys

import requests

REPO = "mochimosh101/leonida-clips"


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


def clipboard() -> str:
    import tkinter
    r = tkinter.Tk()
    r.withdraw()
    try:
        return r.clipboard_get().strip()
    finally:
        r.destroy()


def clear_clipboard():
    import tkinter
    r = tkinter.Tk()
    r.withdraw()
    r.clipboard_clear()
    r.update()
    r.destroy()


def main() -> int:
    key = clipboard()
    if not key.startswith("xai-"):
        sys.exit("Your clipboard doesn't hold an xAI key (they start with 'xai-'). Click Copy on the key and run again.")
    r = requests.get("https://api.x.ai/v1/api-key", headers={"Authorization": f"Bearer {key}"}, timeout=30)
    if r.status_code != 200:
        sys.exit(f"xAI didn't accept that key (HTTP {r.status_code}). Copy it again and rerun.")
    ok = set_secret_gh("XAI_API_KEY", key)
    if not ok:
        token = git_saved_token()
        ok = bool(token) and set_secret_api("XAI_API_KEY", key, token)
    if not ok:
        sys.exit("Couldn't save to GitHub. Sign in with 'gh auth login' and run again.")
    clear_clipboard()
    print("XAI_API_KEY: saved. You can close this window.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
