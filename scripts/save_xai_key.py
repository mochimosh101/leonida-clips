"""Save your xAI (Grok) API key into the repo's GitHub secrets, with no pasting anywhere.

Run on your own computer, right after you click "Copy" on the new key at console.x.ai:
  pip install pynacl requests
  python scripts/save_xai_key.py

It reads the key from your clipboard, checks it with xAI, saves it as the GitHub secret XAI_API_KEY,
then clears your clipboard. Nothing secret is printed.
"""
import sys

import requests

from connect_channel import git_saved_token, set_secret_api, set_secret_gh


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
