"""Channel checkup: why aren't the Shorts getting views?

Run in GitHub Actions (needs the channel's YouTube sign-in in the environment):
  python scripts/diagnose.py --state state/posted.json --name en

For the channel and every posted Short it records what YouTube reports:
  - channel: made-for-kids, linked, upload limits, country
  - each video: privacy, upload/rejection status, made-for-kids, age restriction, region blocks,
    length, shape (vertical or not), views/likes
  - what a logged-out viewer sees on the watch page (playable? family safe? which countries)
  - the YouTube Analytics traffic sources, if the sign-in allows it (it may not)
Writes reports/diagnose-<name>.md and prints it.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def creds():
    return Credentials(token=None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
                       client_id=os.environ["YOUTUBE_CLIENT_ID"],
                       client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
                       token_uri="https://oauth2.googleapis.com/token")


def iso_dur(s):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return None
    h, mi, se = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + se


def public_view(vid):
    """What a logged-out viewer gets from the watch page."""
    try:
        html = requests.get(f"https://www.youtube.com/watch?v={vid}&hl=en&gl=US",
                            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US"},
                            cookies={"CONSENT": "YES+1"}, timeout=20).text
        m = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.+?\});(?:var|</script>)", html)
        if not m:
            return {"error": "player data not found"}
        pr = json.loads(m.group(1))
        ps = pr.get("playabilityStatus", {})
        mf = pr.get("microformat", {}).get("playerMicroformatRenderer", {})
        vd = pr.get("videoDetails", {})
        return {"playable": ps.get("status"), "reason": ps.get("reason"),
                "family_safe": mf.get("isFamilySafe"), "countries": len(mf.get("availableCountries", []) or []),
                "unlisted": mf.get("isUnlisted"), "category": mf.get("category"),
                "public_views": vd.get("viewCount"), "is_shorts_eligible": mf.get("isShortsEligible")}
    except Exception as e:
        return {"error": str(e)[:120]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--name", required=True)
    args = ap.parse_args()
    c = creds()
    yt = build("youtube", "v3", credentials=c, cache_discovery=False)
    L = [f"# Channel checkup ({args.name}) {dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC", ""]

    ch = yt.channels().list(part="snippet,status,statistics,brandingSettings,contentDetails",
                            mine=True).execute().get("items", [])
    if ch:
        ch = ch[0]
        L += ["## Channel", "```", json.dumps({
            "title": ch["snippet"]["title"], "created": ch["snippet"].get("publishedAt"),
            "country": ch["snippet"].get("country"), "status": ch.get("status"),
            "stats": ch.get("statistics"),
            "branding_channel": {k: v for k, v in ch.get("brandingSettings", {}).get("channel", {}).items()
                                 if k in ("keywords", "country", "defaultLanguage", "madeForKids")},
        }, indent=1), "```", ""]
        uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    else:
        uploads = None

    # every video on the channel, not just the ones the bot logged
    ids = []
    if uploads:
        tok = None
        while True:
            r = yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=50,
                                        pageToken=tok).execute()
            ids += [i["contentDetails"]["videoId"] for i in r.get("items", [])]
            tok = r.get("nextPageToken")
            if not tok:
                break
    posted = json.load(open(os.path.join(ROOT, args.state)))
    ids += [r["youtube_id"] for r in posted if r.get("youtube_id")]
    ids = list(dict.fromkeys(ids))

    rows = []
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="snippet,status,contentDetails,statistics,fileDetails,processingDetails,suggestions",
                             id=",".join(ids[i:i + 50])).execute()
        for v in r.get("items", []):
            st, cd = v.get("status", {}), v.get("contentDetails", {})
            fd = v.get("fileDetails", {})
            vs = (fd.get("videoStreams") or [{}])[0]
            rows.append({
                "id": v["id"], "title": v["snippet"]["title"][:60], "published": v["snippet"]["publishedAt"],
                "privacy": st.get("privacyStatus"), "upload": st.get("uploadStatus"),
                "rejection": st.get("rejectionReason"), "failure": st.get("failureReason"),
                "made_for_kids": st.get("madeForKids"), "self_kids": st.get("selfDeclaredMadeForKids"),
                "embeddable": st.get("embeddable"), "license": st.get("license"),
                "synthetic": st.get("containsSyntheticMedia"),
                "secs": iso_dur(cd.get("duration")), "rating": cd.get("contentRating"),
                "region": cd.get("regionRestriction"), "licensed": cd.get("licensedContent"),
                "w": vs.get("widthPixels"), "h": vs.get("heightPixels"),
                "views": int(v.get("statistics", {}).get("viewCount", 0)),
                "likes": int(v.get("statistics", {}).get("likeCount", 0)),
                "processing": v.get("processingDetails", {}).get("processingStatus"),
                "lang": v["snippet"].get("defaultAudioLanguage"), "category": v["snippet"].get("categoryId"),
                "tags": len(v["snippet"].get("tags", [])),
            })
    missing = [i for i in ids if i not in {r["id"] for r in rows}]
    for r in rows:
        r["public"] = public_view(r["id"])

    L += ["## Videos", "| id | views | privacy | kids | 18+ | region | secs | WxH | logged-out viewer | title |",
          "|---|---:|---|---|---|---|---:|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["published"]):
        p = r["public"]
        pv = p.get("error") or f"{p.get('playable')} {p.get('reason') or ''} safe={p.get('family_safe')} cc={p.get('countries')}"
        L.append(f"| {r['id']} | {r['views']} | {r['privacy']}/{r['upload']}{'/' + r['rejection'] if r['rejection'] else ''} "
                 f"| {r['made_for_kids']} | {json.dumps(r['rating']) if r['rating'] else '-'} | "
                 f"{json.dumps(r['region']) if r['region'] else '-'} | {r['secs']} | {r['w']}x{r['h']} | {pv} | {r['title']} |")
    if missing:
        L += ["", f"Not returned by YouTube (deleted/removed?): {', '.join(missing)}"]
    L += ["", "## Raw", "```", json.dumps(rows, indent=1)[:60000], "```", ""]

    # Traffic sources (needs yt-analytics.readonly; reports the error if the sign-in lacks it)
    try:
        ya = build("youtubeAnalytics", "v2", credentials=c, cache_discovery=False)
        today = dt.date.today()
        res = ya.reports().query(ids="channel==MINE", startDate=str(today - dt.timedelta(days=30)),
                                 endDate=str(today), metrics="views", dimensions="insightTrafficSourceType").execute()
        L += ["## Traffic sources (30 days)", "```", json.dumps(res.get("rows"), indent=1), "```"]
    except Exception as e:
        L += ["## Traffic sources", f"Not available with this sign-in: {str(e)[:200]}"]

    out = "\n".join(L)
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    with open(os.path.join(ROOT, "reports", f"diagnose-{args.name}.md"), "w") as f:
        f.write(out)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(out.split("## Raw")[0] + "\n")
    print(out)


if __name__ == "__main__":
    sys.exit(main())
