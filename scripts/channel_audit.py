"""One-off: pull every upload's stats for one channel (uses that channel's token).
Writes audit/<name>.json. Tries the Analytics API too (needs yt-analytics.readonly; skipped if not granted)."""
import json, os, sys, datetime as dt
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

name = sys.argv[1]
creds = Credentials(token=None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
                    client_id=os.environ["YOUTUBE_CLIENT_ID"], client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
                    token_uri="https://oauth2.googleapis.com/token")
yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
ch = yt.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()["items"][0]
uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
ids, tok = [], None
while True:
    r = yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=50, pageToken=tok).execute()
    ids += [i["contentDetails"]["videoId"] for i in r["items"]]
    tok = r.get("nextPageToken")
    if not tok:
        break
vids = []
for i in range(0, len(ids), 50):
    r = yt.videos().list(part="snippet,statistics,status,contentDetails", id=",".join(ids[i:i+50])).execute()
    for v in r["items"]:
        st = v.get("statistics", {})
        vids.append({"id": v["id"], "title": v["snippet"]["title"], "published": v["snippet"]["publishedAt"],
                     "duration": v["contentDetails"]["duration"], "privacy": v["status"]["privacyStatus"],
                     "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                     "comments": int(st.get("commentCount", 0))})
out = {"channel": ch["snippet"]["title"], "id": ch["id"], "stats": ch["statistics"],
       "pulled": dt.datetime.utcnow().isoformat() + "Z", "videos": vids}
try:
    ya = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    r = ya.reports().query(ids="channel==MINE", startDate="2026-11-01", endDate=dt.date.today().isoformat(),
                           metrics="views,averageViewDuration,averageViewPercentage,subscribersGained",
                           dimensions="video", sort="-views", maxResults=200).execute()
    out["analytics"] = r.get("rows", [])
except Exception as e:
    out["analytics_error"] = str(e)[:300]
os.makedirs("audit", exist_ok=True)
json.dump(out, open(f"audit/{name}.json", "w"), indent=1)
print(name, out["channel"], out["stats"], len(vids), "videos", "analytics" in out)
