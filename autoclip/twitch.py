"""Find and download top Twitch clips for a game."""
import datetime as dt
import os
import subprocess
from dataclasses import dataclass

import requests

HELIX = "https://api.twitch.tv/helix"


@dataclass
class Clip:
    id: str
    url: str
    title: str
    broadcaster_login: str
    broadcaster_name: str
    view_count: int
    duration: float
    language: str
    created_at: str


def _token() -> str:
    r = requests.post(
        "https://id.twitch.tv/oauth2/token",
        data={
            "client_id": os.environ["TWITCH_CLIENT_ID"],
            "client_secret": os.environ["TWITCH_CLIENT_SECRET"],
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Client-Id": os.environ["TWITCH_CLIENT_ID"], "Authorization": f"Bearer {token}"}


def _game_id(token: str, name: str) -> str:
    r = requests.get(f"{HELIX}/games", headers=_headers(token), params={"name": name}, timeout=30)
    r.raise_for_status()
    data = r.json()["data"]
    if not data:
        raise SystemExit(f"Twitch category not found: {name!r}")
    return data[0]["id"]


def _logins(token: str, ids: list[str]) -> dict[str, str]:
    out = {}
    for i in range(0, len(ids), 100):
        r = requests.get(f"{HELIX}/users", headers=_headers(token),
                         params=[("id", x) for x in ids[i:i + 100]], timeout=30)
        r.raise_for_status()
        out.update({u["id"]: u["login"] for u in r.json()["data"]})
    return out


def top_clips(cfg: dict) -> list[Clip]:
    token = _token()
    game = _game_id(token, cfg["game_name"])
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=cfg["lookback_hours"])
    r = requests.get(
        f"{HELIX}/clips",
        headers=_headers(token),
        params={"game_id": game, "started_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "first": 100},
        timeout=30,
    )
    r.raise_for_status()
    raw = r.json()["data"]
    logins = _logins(token, sorted({c["broadcaster_id"] for c in raw}))
    clips = [
        Clip(
            id=c["id"], url=c["url"], title=c["title"],
            broadcaster_login=logins.get(c["broadcaster_id"], c["broadcaster_name"].lower()),
            broadcaster_name=c["broadcaster_name"], view_count=c["view_count"],
            duration=c["duration"], language=c["language"], created_at=c["created_at"],
        )
        for c in raw
    ]
    return sorted(clips, key=lambda c: c.view_count, reverse=True)


def eligible(clip: Clip, cfg: dict, posted: set[str]) -> bool:
    if clip.id in posted or clip.view_count < cfg["min_views"]:
        return False
    if cfg["languages"] and clip.language not in cfg["languages"]:
        return False
    login = clip.broadcaster_login.lower()
    if login in {b.lower() for b in cfg["broadcaster_blocklist"]}:
        return False
    if not cfg["allow_any_broadcaster"]:
        return login in {b.lower() for b in cfg["broadcaster_allowlist"]}
    return True


def download(clip: Clip, out_path: str) -> str:
    subprocess.run(
        ["yt-dlp", "-q", "--no-warnings", "-f", "best[ext=mp4]/best", "-o", out_path, clip.url],
        check=True,
    )
    return out_path
