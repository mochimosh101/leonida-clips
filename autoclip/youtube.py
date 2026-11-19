"""Upload a finished Short with the YouTube Data API (OAuth refresh token stored as a secret)."""
import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _client():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(path: str, title: str, description: str, tags: list[str], yt: dict,
           age_restricted: bool = False) -> str:
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
            "tags": tags[:30],
            "categoryId": yt["category_id"],
        },
        "status": {
            "privacyStatus": yt["privacy_status"],
            "selfDeclaredMadeForKids": yt["made_for_kids"],
            "containsSyntheticMedia": True,  # Rico's voice is AI; YouTube asks for this, no monetization hit
        },
    }
    if age_restricted:
        # Ask YouTube to mark it 18+. If the API refuses this field, upload without it.
        try:
            resp = _send(path, "snippet,status,contentDetails",
                         {**body, "contentDetails": {"contentRating": {"ytRating": "ytAgeRestricted"}}})
            rating = resp.get("contentDetails", {}).get("contentRating", {}).get("ytRating")
            print(f"18+ requested for {resp['id']}: YouTube reports ytRating={rating}")
            return resp["id"]
        except HttpError as e:
            print(f"18+ field refused ({e.status_code}); uploading without it")
    return _send(path, "snippet,status", body)["id"]


def _send(path: str, part: str, body: dict) -> dict:
    req = _client().videos().insert(
        part=part, body=body,
        media_body=MediaFileUpload(path, mimetype="video/mp4", resumable=True),
    )
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp
