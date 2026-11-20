"""Daily Shorts reviewer: pulls every posted Short's stats, finds what's working, feeds it back to the bot.

Usage (one channel per run, using that channel's YouTube sign-in from the environment):
  python -m autoclip.review --config config.yaml
  python -m autoclip.review --config config.es.yaml

What it does:
  1. Reads the channel's posted Shorts (state/posted*.json) and asks YouTube for views, likes, comments.
  2. Saves a snapshot per video per day in state/stats.json, so videos of different ages can be
     compared fairly (each video is judged on its views at about 48 hours old).
  3. For every A/B test (caption style, hook style, verdict style, series title style, series look)
     works out which option gets more views, and writes new odds to state/learned.json. The bot
     reads those odds, so winners get used more. Every option keeps at least a small share.
  4. Asks Claude for a few concrete lessons from the best and worst Shorts (fed to the writer).
  5. Writes a plain-English report to reports/daily/<date>-<channel>.md.
"""
import argparse
import datetime as dt
import json
import math
import os
import statistics

import yaml

from . import learned

ROOT = learned.ROOT
STATS = os.path.join(ROOT, "state", "stats.json")
TARGET_AGE_H = 48.0     # compare every video at this age
MIN_AGE_H = 20.0        # younger videos are too early to judge
MIN_VIEWS_TO_LEARN = 300  # below this many 48h views in total, differences are luck: keep the test even
PRIOR = 3.0             # pretend every option already has 3 average videos (stops one lucky video winning)
EXPLORE = 0.2           # share of picks kept spread evenly across all options
PT = dt.timezone(dt.timedelta(hours=-8))  # Pacific (PST); good enough for slot labels

YPP_SUBS, YPP_VIEWS = 1000, 10_000_000


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ---------- YouTube ----------

def youtube_client():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def fetch_videos(yt, ids: list[str]) -> dict:
    out = {}
    for i in range(0, len(ids), 50):
        resp = yt.videos().list(part="snippet,statistics,status", id=",".join(ids[i:i + 50])).execute()
        for item in resp.get("items", []):
            st = item.get("statistics", {})
            out[item["id"]] = {
                "published": item["snippet"]["publishedAt"],
                "privacy": item.get("status", {}).get("privacyStatus"),
                "views": int(st.get("viewCount", 0)),
                "likes": int(st.get("likeCount", 0)),
                "comments": int(st.get("commentCount", 0)),
            }
    return out


def fetch_channel(yt) -> dict:
    items = yt.channels().list(part="snippet,statistics", mine=True).execute().get("items", [])
    if not items:
        return {}
    st = items[0]["statistics"]
    return {"title": items[0]["snippet"]["title"], "subs": int(st.get("subscriberCount", 0)),
            "views": int(st.get("viewCount", 0)), "videos": int(st.get("videoCount", 0))}


# ---------- scoring ----------

def views_at_target(published: str, snaps: list) -> tuple[float | None, str]:
    """Estimated views at ~48h old from the daily snapshots. Returns (views, how)."""
    pub = parse_ts(published)
    pts = sorted(((parse_ts(t) - pub).total_seconds() / 3600, v) for t, v, *_ in snaps)
    pts = [(a, v) for a, v in pts if a > 0]
    if not pts or pts[-1][0] < MIN_AGE_H:
        return None, "too new"
    before = [p for p in pts if p[0] <= TARGET_AGE_H]
    after = [p for p in pts if p[0] >= TARGET_AGE_H]
    if before and after:
        (a0, v0), (a1, v1) = before[-1], after[0]
        if a1 == a0:
            return float(v0), "measured"
        return v0 + (v1 - v0) * (TARGET_AGE_H - a0) / (a1 - a0), "measured"
    if after:  # first seen when already older than 48h (e.g. the first day the reviewer ran)
        a, v = after[0]
        return v * (TARGET_AGE_H / a) ** 0.5, "estimated"
    a, v = before[-1]  # 20-48h old: project forward
    return v * (TARGET_AGE_H / a) ** 0.5, "estimated"


def group_of(row: dict) -> str:
    if row.get("format") == "series":
        return "series"
    return {"uncensored": "18+ uncensored", "censored": "18+ censored"}.get(row.get("variant"), "clips")


def factor_value(row: dict, factor: str):
    if factor == "slot":
        if not row.get("posted_at"):
            return None
        return parse_ts(row["posted_at"]).astimezone(PT).strftime("%-I %p PT")
    if factor == "format":
        return group_of(row)
    v = row.get(factor)
    return str(v) if v not in (None, "") else None


def weights_for(scored: list[dict], factor: str, options: list[str]) -> tuple[dict, dict]:
    """Returns (weights, table). Score per option = smoothed geometric mean of relative views."""
    logs = {o: [] for o in options}
    for r in scored:
        v = factor_value(r, factor)
        if v in logs:
            logs[v].append(math.log(max(r["rel"], 0.05)))
    table, strength = {}, {}
    for o in options:
        n = len(logs[o])
        s = math.exp(sum(logs[o]) / (n + PRIOR))  # unseen options sit at 1.0 = average
        strength[o] = s ** 2  # sharpen so a clear winner actually gets picked more
        table[o] = {"videos": n, "score": round(s, 2)}
    total = sum(strength.values())
    weights = {o: round((1 - EXPLORE) * strength[o] / total + EXPLORE / len(options), 3) for o in options}
    return weights, table


def lessons_from_claude(cfg: dict, scored: list[dict], tables: dict) -> tuple[list[str], str]:
    """A few concrete writing rules from the best vs worst Shorts, plus a 2-3 sentence summary."""
    if len(scored) < 6 or not os.environ.get("ANTHROPIC_API_KEY"):
        return [], ""
    import anthropic
    from pydantic import BaseModel, Field

    class Review(BaseModel):
        lessons: list[str] = Field(description="3 to 5 concrete rules for future hooks, titles and verdicts, "
                                               "each under 25 words")
        summary: str = Field(description="2 to 3 plain sentences for the channel owner (no jargon): what is "
                                         "working, what isn't, what the bot will do more of")

    ranked = sorted(scored, key=lambda r: r["rel"], reverse=True)
    def fmt(r):
        return (f"- {r['views48']:.0f} views@48h ({r['rel']:.2f}x typical) [{group_of(r)}] "
                f"title: {r.get('title')} | hook({r.get('hook_style', '-')}): {r.get('hook')} | "
                f"verdict({r.get('verdict_style', '-')}): {r.get('verdict', '-')} | caption {r.get('caption_style', '-')}")
    best = "\n".join(fmt(r) for r in ranked[:6])
    worst = "\n".join(fmt(r) for r in ranked[-6:])
    prompt = (
        "You review a GTA 6 YouTube Shorts channel narrated by an AI host, Rico Neon. Below are its best and "
        "worst Shorts by views at 48 hours (relative to similar Shorts on the channel), and the A/B test "
        "tables. Find patterns in the wording, subjects, streamers and styles that separate winners from "
        "losers, and turn them into rules the script writer can follow. Be specific (e.g. 'name the streamer "
        "and the exact stake in the hook'), not generic. Small sample: only state patterns the data supports.\n\n"
        f"BEST:\n{best}\n\nWORST:\n{worst}\n\nA/B TABLES (score 1.0 = average):\n{json.dumps(tables)}"
        + (f"\n\nChannel language note: {cfg['writer_language']}" if cfg.get("writer_language") else "")
    )
    try:
        resp = anthropic.Anthropic().messages.parse(
            model=cfg["writer_model"], max_tokens=4000, output_config={"effort": "low"},
            messages=[{"role": "user", "content": prompt}], output_format=Review)
        out = resp.parsed_output
        return [l.strip() for l in out.lessons][:5], out.summary.strip()
    except Exception as e:  # the numbers still work without the lessons
        print(f"lessons skipped: {e}")
        return [], ""


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--offline", help="JSON file of {video_id: stats} to use instead of YouTube (testing)")
    args = ap.parse_args()
    with open(os.path.join(ROOT, args.config)) as f:
        cfg = yaml.safe_load(f)
    key = learned.channel_key(cfg)
    posted = load_json(os.path.join(ROOT, cfg.get("state_file", "state/posted.json")), [])
    rows = [r for r in posted if r.get("youtube_id") and not r.get("dry_run")]
    seen, uniq = set(), []
    for r in rows:  # a video id can appear twice if it was recorded by hand
        if r["youtube_id"] not in seen:
            seen.add(r["youtube_id"])
            uniq.append(r)
    rows = uniq
    print(f"[{key}] {len(rows)} posted Shorts")

    if args.offline:
        live, channel = load_json(args.offline, {}), {}
    else:
        yt = youtube_client()
        live = fetch_videos(yt, [r["youtube_id"] for r in rows])
        try:
            channel = fetch_channel(yt)
        except Exception as e:
            print(f"channel stats skipped: {e}")
            channel = {}

    stamp = now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
    stats = load_json(STATS, {})
    ch_stats = stats.setdefault(key, {})
    missing = []
    for r in rows:
        vid = r["youtube_id"]
        info = live.get(vid)
        if not info:
            missing.append(r)
            continue
        entry = ch_stats.setdefault(vid, {"published": info["published"], "snaps": []})
        entry["published"] = info["published"]
        entry["privacy"] = info.get("privacy")
        entry["snaps"] = (entry["snaps"] + [[stamp, info["views"], info["likes"], info["comments"]]])[-30:]
    if channel:
        stats.setdefault("_channels", {}).setdefault(key, []).append({"at": stamp, **channel})
        stats["_channels"][key] = stats["_channels"][key][-120:]
    save_json(STATS, stats)

    # Score every video old enough to judge
    scored = []
    for r in rows:
        e = ch_stats.get(r["youtube_id"])
        if not e:
            continue
        v48, how = views_at_target(e["published"], e["snaps"])
        last = e["snaps"][-1]
        if v48 is None:
            continue
        scored.append({**r, "views48": v48, "how": how, "views_now": last[1], "likes": last[2],
                       "comments": last[3], "published": e["published"]})
    by_group = {}
    for r in scored:
        by_group.setdefault(group_of(r), []).append(r["views48"])
    all_med = statistics.median([r["views48"] for r in scored if group_of(r) != "18+ uncensored"] or [1]) or 1
    for r in scored:
        g = by_group[group_of(r)]
        base = statistics.median(g) if len(g) >= 3 else all_med
        r["rel"] = r["views48"] / max(base, 1)

    weights, tables = {}, {}
    enough = sum(r["views48"] for r in scored) >= MIN_VIEWS_TO_LEARN
    for factor, options in learned.OPTIONS.items():
        weights[factor], tables[factor] = weights_for(scored, factor, options)
        if not enough:
            weights[factor] = {o: round(1 / len(options), 3) for o in options}
    for factor in ("format", "slot", "streamer"):  # reported only; not changed automatically
        vals = sorted({factor_value(r, factor) for r in scored} - {None})
        if vals:
            tables[factor] = weights_for(scored, factor, vals)[1]

    lessons, summary = lessons_from_claude(cfg, scored, tables) if enough else ([], "")
    store = load_json(learned.PATH, {})
    prev = store.get("channels", {}).get(key, {})
    store.setdefault("channels", {})[key] = {
        "updated": stamp,
        "videos_scored": len(scored),
        "weights": weights,
        "tested": {f: {o: t["videos"] for o, t in tables[f].items()} for f in learned.OPTIONS},
        "lessons": lessons or prev.get("lessons", []),
    }
    save_json(learned.PATH, store)

    report = render_report(key, cfg, rows, scored, missing, tables, weights, prev.get("weights", {}),
                           lessons, summary, channel, stats.get("_channels", {}).get(key, []), enough)
    day = now_utc().astimezone(PT).strftime("%Y-%m-%d")
    path = os.path.join(ROOT, "reports", "daily", f"{day}-{key}.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(report + "\n\n")
    print(report)
    return 0


def render_report(key, cfg, rows, scored, missing, tables, weights, old_weights, lessons, summary,
                  channel, history, enough=True) -> str:
    name = channel.get("title") or ("Leonida Clips en Español" if key == "es" else "Leonida Clips")
    today = now_utc().astimezone(PT).strftime("%a %b %-d, %Y")
    L = [f"# Daily Shorts review: {name}", f"_{today}. {len(rows)} Shorts posted, "
         f"{len(scored)} old enough to judge (about 48 hours of views)._", ""]
    if channel:
        L += ["## Monetization progress",
              f"- Subscribers: **{channel['subs']:,}** of {YPP_SUBS:,}",
              f"- Channel views (all time): **{channel['views']:,}** of {YPP_VIEWS:,} needed in 90 days",
              ""]
        day_ago = [h for h in history[:-1] if parse_ts(h["at"]) <= now_utc() - dt.timedelta(hours=20)]
        if day_ago:
            p = day_ago[-1]
            L.insert(-1, f"- Since yesterday: {channel['subs'] - p['subs']:+,} subscribers, "
                         f"{channel['views'] - p['views']:+,} views")
    if summary:
        L += ["## In short", summary, ""]
    if scored and not enough:
        total = sum(r["views48"] for r in scored)
        L += ["## In short", f"Only about {total:,.0f} views across the judged Shorts so far. That's too few to tell "
              f"which styles really win, so the bot keeps testing everything evenly. It starts shifting toward "
              f"winners once the judged Shorts pass {MIN_VIEWS_TO_LEARN:,} views.", ""]
    if not scored:
        L += ["Not enough data yet: Shorts need about a day of views before they can be compared. "
              "The bot keeps testing every style evenly until then.", ""]
    else:
        ranked = sorted(scored, key=lambda r: r["rel"], reverse=True)
        def line(r):
            est = "" if r["how"] == "measured" else " (est.)"
            return (f"| {r['views48']:,.0f}{est} | {r['views_now']:,} | {r['likes']} | {r['rel']:.1f}x | "
                    f"[{(r.get('title') or '')[:55]}](https://youtube.com/shorts/{r['youtube_id']}) |")
        head = ["| Views at 48h | Views now | Likes | vs typical | Short |", "|---:|---:|---:|---:|---|"]
        L += ["## Best Shorts", *head, *[line(r) for r in ranked[:5]], ""]
        if len(ranked) > 5:
            L += ["## Weakest Shorts", *head, *[line(r) for r in ranked[-3:]], ""]

        L += ["## A/B tests", "Score 1.0 = a typical Short. **Next odds** = how often the bot will pick each "
              "option from now on (winners get more, every option keeps some so the test continues).", ""]
        labels = {"caption_style": "Caption style (A pink 3 words, B yellow 2 words, C cyan 1 big word)",
                  "hook_style": "Hook style (H1 question, H2 superlative, H3 setup+but, H4 Rico's bet, "
                                "H5 GTA 5 contrast, H6 warning, H7 countdown)",
                  "verdict_style": "Verdict style (V1 Neon score, V2 GTA 5 comparison, V3 tip, V4 prediction, "
                                   "V5 callback, V6 contrarian)",
                  "title_style": "Series banner (count = numbered list, utility = one promise)",
                  "look": "Series look (clean vs sticker white boxes)",
                  "format": "Type of Short (report only)", "slot": "Posting time (report only)",
                  "streamer": "Streamer (report only)"}
        for factor, table in tables.items():
            if not any(t["videos"] for t in table.values()):
                continue
            L.append(f"**{labels.get(factor, factor)}**")
            L.append("")
            has_w = factor in weights
            L.append("| Option | Shorts | Score |" + (" Next odds |" if has_w else ""))
            L.append("|---|---:|---:|" + ("---:|" if has_w else ""))
            for o, t in sorted(table.items(), key=lambda kv: -kv[1]["score"]):
                if factor == "streamer" and t["videos"] < 2:
                    continue
                cell = ""
                if has_w:
                    new = weights[factor][o]
                    old = old_weights.get(factor, {}).get(o)
                    arrow = "" if old is None or abs(new - old) < 0.01 else (" ▲" if new > old else " ▼")
                    cell = f" {new:.0%}{arrow} |"
                L.append(f"| {o} | {t['videos']} | {t['score']:.2f} |{cell}")
            L.append("")
    if lessons:
        L += ["## Lessons fed to the writer", *[f"- {l}" for l in lessons], ""]
    if missing:
        L += [f"_{len(missing)} posted Short(s) not found on YouTube (deleted or private): "
              + ", ".join(r["youtube_id"] for r in missing[:10]) + "_", ""]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
