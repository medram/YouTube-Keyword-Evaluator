"""
YouTube Keyword Evaluator — Core Analysis Engine
=================================================
Pure-Python module with zero Streamlit/UI dependencies.
Shared by the Streamlit app (app.py), the REST API (api.py),
and the MCP server (mcp_server.py).

The centrepiece is `analyse_keyword()` which runs a full KOS
(Keyword Opportunity Score) evaluation against the YouTube Data API v3.
"""

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any

logger = logging.getLogger("uvicorn.error")

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    raise ImportError("Missing: pip install google-api-python-client")

# ─────────────────────────────────────────────────────────────────────────────
#  In-memory TTL cache
# ─────────────────────────────────────────────────────────────────────────────

# Default: 1 hour.  Override with CACHE_TTL_SECONDS env var (0 = disabled).
_CACHE_TTL: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

# {cache_key: (result_dict, expires_at_epoch)}
_cache: dict[str, tuple[dict[str, Any], float]] = {}
_cache_lock = Lock()


def _cache_key(keyword: str, settings: dict) -> str:
    """Stable cache key from normalised keyword + settings fingerprint."""
    kw_norm = keyword.strip().lower()
    settings_hash = hashlib.md5(
        json.dumps(settings, sort_keys=True).encode()
    ).hexdigest()[:8]
    return f"{kw_norm}|{settings_hash}"


def cache_clear() -> int:
    """Remove all cached entries. Returns the number of entries cleared."""
    with _cache_lock:
        count = len(_cache)
        _cache.clear()
    return count


def cache_stats() -> dict[str, Any]:
    """Return basic cache statistics."""
    now = time.time()
    with _cache_lock:
        total = len(_cache)
        expired = sum(1 for _, exp in _cache.values() if exp <= now)
    return {
        "total_entries": total,
        "live_entries": total - expired,
        "expired_entries": expired,
        "ttl_seconds": _CACHE_TTL,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Scoring settings (all thresholds & point caps in one place)
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_SETTINGS: dict = {
    # ── Group A — Video Metrics (default max: 30 pts) ───────────────────────
    "a_avg_views_pts": 8,
    "a_avg_views_lo": 100_000,
    "a_avg_views_hi1": 1_000_000,
    "a_avg_views_hi2": 10_000_000,
    "a_video_age_pts": 8,
    "a_video_age_lo_mo": 6,
    "a_video_age_hi1_mo": 4,
    "a_video_age_hi2_mo": 18,
    "a_vpm_pts": 9,
    "a_vpm_lo": 500,
    "a_vpm_hi1": 1_000_000,
    "a_vpm_hi2": 2_000_000,
    "a_like_ratio_pts": 3,
    "a_like_ratio_lo": 0.1,
    "a_like_ratio_hi1": 2.0,
    "a_like_ratio_hi2": 10.0,
    "a_comments_pts": 2,
    "a_comments_lo": 10,
    "a_comments_hi1": 1_000,
    "a_comments_hi2": 5_000,
    # ── Group B — Channel Metrics (default max: 32 pts) ─────────────────────
    "b_subs_pts": 12,
    "b_subs_t1": 1_000_000,
    "b_subs_t2": 100_000,
    "b_subs_t3": 10_000,
    "b_vid_count_pts": 10,
    "b_vid_count_t1": 500,
    "b_vid_count_t2": 100,
    "b_ch_age_pts": 10,
    "b_ch_age_t1": 5.0,
    "b_ch_age_t2": 2.0,
    # ── Group C — Saturation (default max: 38 pts) ──────────────────────────
    "c_title_pts": 20,
    "c_title_t1": 3,
    "c_title_t2": 7,
    "c_title_pos_pts": 5,
    "c_desc_pts": 13,
    "c_desc_t1": 3,
    "c_desc_t2": 7,
}


# ─────────────────────────────────────────────────────────────────────────────
#  Formatting helpers
# ─────────────────────────────────────────────────────────────────────────────


def fmt_number(n) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def count_kw(text: str, keyword: str) -> int:
    return len(re.findall(re.escape(keyword), text, re.IGNORECASE))


def parse_dt(iso: str) -> datetime:
    iso = iso.rstrip("Z") + "+00:00"
    return datetime.fromisoformat(iso)


def months_since(dt: datetime) -> float:
    now = datetime.now(timezone.utc)
    return (now - dt).days / 30.44


def years_since(dt: datetime) -> float:
    return months_since(dt) / 12.0


# ─────────────────────────────────────────────────────────────────────────────
#  Group max helpers (used to normalise scores in responses)
# ─────────────────────────────────────────────────────────────────────────────


def max_group_a(S: dict) -> int:
    return (
        S["a_avg_views_pts"]
        + S["a_video_age_pts"]
        + S["a_vpm_pts"]
        + S["a_like_ratio_pts"]
        + S["a_comments_pts"]
    )


def max_group_b(S: dict) -> int:
    return S["b_subs_pts"] + S["b_vid_count_pts"] + S["b_ch_age_pts"]


def max_group_c(S: dict) -> int:
    return S["c_title_pts"] + S["c_title_pos_pts"] + S["c_desc_pts"]


def total_max(S: dict) -> int:
    return max_group_a(S) + max_group_b(S) + max_group_c(S)


# ─────────────────────────────────────────────────────────────────────────────
#  KOS scoring functions
# ─────────────────────────────────────────────────────────────────────────────


def score_group_a(
    avg_views: float,
    avg_like_ratio: float,
    avg_age_months: float,
    avg_comments: float,
    avg_vpm: float,
    S: dict,
) -> dict[str, int]:
    """Bell-curve scoring for video metrics. Sweet spot = full pts."""
    pts: dict[str, int] = {}

    P = S["a_avg_views_pts"]
    if avg_views < S["a_avg_views_lo"]:
        pts["Avg Views"] = round(P / 2)
    elif avg_views <= S["a_avg_views_hi1"]:
        pts["Avg Views"] = P
    elif avg_views <= S["a_avg_views_hi2"]:
        pts["Avg Views"] = round(P / 2)
    else:
        pts["Avg Views"] = 0

    P = S["a_video_age_pts"]
    if avg_age_months < S["a_video_age_lo_mo"]:
        pts["Avg Video Age"] = round(P / 2)
    elif avg_age_months <= S["a_video_age_hi1_mo"]:
        pts["Avg Video Age"] = P
    elif avg_age_months <= S["a_video_age_hi2_mo"]:
        pts["Avg Video Age"] = round(P / 2)
    else:
        pts["Avg Video Age"] = 0

    P = S["a_vpm_pts"]
    if avg_vpm < S["a_vpm_lo"]:
        pts["Views per Month"] = 0
    elif avg_vpm <= S["a_vpm_hi1"]:
        pts["Views per Month"] = P
    elif avg_vpm <= S["a_vpm_hi2"]:
        pts["Views per Month"] = round(P / 2)
    else:
        pts["Views per Month"] = 0

    P = S["a_like_ratio_pts"]
    ratio_pct = avg_like_ratio * 100
    if ratio_pct < S["a_like_ratio_lo"]:
        pts["Likes/Views Ratio"] = 0
    elif ratio_pct <= S["a_like_ratio_hi1"]:
        pts["Likes/Views Ratio"] = P
    elif ratio_pct <= S["a_like_ratio_hi2"]:
        pts["Likes/Views Ratio"] = round(P / 2)
    else:
        pts["Likes/Views Ratio"] = 0

    P = S["a_comments_pts"]
    if avg_comments < S["a_comments_lo"]:
        pts["Avg Comments"] = 0
    elif avg_comments <= S["a_comments_hi1"]:
        pts["Avg Comments"] = P
    elif avg_comments <= S["a_comments_hi2"]:
        pts["Avg Comments"] = round(P / 2)
    else:
        pts["Avg Comments"] = 0

    return pts


def score_group_b(
    avg_subs: float,
    avg_vid_count: float,
    avg_ch_age_years: float,
    S: dict,
) -> dict[str, int]:
    pts: dict[str, int] = {}

    P = S["b_subs_pts"]
    if avg_subs >= S["b_subs_t1"]:
        pts["Avg Subscribers"] = 0
    elif avg_subs >= S["b_subs_t2"]:
        pts["Avg Subscribers"] = round(P * 1 / 3)
    elif avg_subs >= S["b_subs_t3"]:
        pts["Avg Subscribers"] = round(P * 2 / 3)
    else:
        pts["Avg Subscribers"] = P

    P = S["b_vid_count_pts"]
    if avg_vid_count > S["b_vid_count_t1"]:
        pts["Avg Video Count"] = 0
    elif avg_vid_count >= S["b_vid_count_t2"]:
        pts["Avg Video Count"] = round(P / 2)
    else:
        pts["Avg Video Count"] = P

    P = S["b_ch_age_pts"]
    if avg_ch_age_years > S["b_ch_age_t1"]:
        pts["Avg Channel Age"] = 0
    elif avg_ch_age_years >= S["b_ch_age_t2"]:
        pts["Avg Channel Age"] = round(P / 2)
    else:
        pts["Avg Channel Age"] = P

    return pts


def kw_position_pts(videos: list, keyword: str, max_pts: int) -> int:
    """Score based on avg keyword position in competing titles. Start = fewer pts."""
    positions = []
    for v in videos:
        m = re.search(re.escape(keyword), v["title"], re.IGNORECASE)
        if m:
            pos_ratio = m.start() / max(len(v["title"]), 1)
            positions.append(pos_ratio)
    if not positions:
        return max_pts
    avg_pos = sum(positions) / len(positions)
    return max(0, min(max_pts, round(avg_pos * max_pts)))


def score_group_c(
    kw_in_title: int,
    kw_in_desc: int,
    title_pos_score: int,
    S: dict,
) -> dict[str, int]:
    pts: dict[str, int] = {}

    P, t1, t2 = S["c_title_pts"], S["c_title_t1"], S["c_title_t2"]
    if kw_in_title == 0:
        pts["KW in Titles"] = P
    elif kw_in_title <= t1:
        pts["KW in Titles"] = round(P * 4 / 7)
    elif kw_in_title <= t2:
        pts["KW in Titles"] = round(P * 2 / 7)
    else:
        pts["KW in Titles"] = 1

    pts["KW Title Position"] = title_pos_score

    P, d1, d2 = S["c_desc_pts"], S["c_desc_t1"], S["c_desc_t2"]
    if kw_in_desc == 0:
        pts["KW in Descriptions"] = P
    elif kw_in_desc <= d1:
        pts["KW in Descriptions"] = round(P * 3 / 5)
    elif kw_in_desc <= d2:
        pts["KW in Descriptions"] = round(P * 1 / 5)
    else:
        pts["KW in Descriptions"] = 1

    return pts


def kos_label(score: int) -> tuple[str, str, str]:
    """Returns (label, emoji, hex_color)."""
    if score >= 75:
        return "Great Opportunity", "🟢", "#3ddc84"
    if score >= 50:
        return "Moderate", "🟡", "#ffd700"
    if score >= 25:
        return "Tough", "🟠", "#ff6b35"
    return "Very Competitive", "🔴", "#ff0050"


def competition_level(avg_views: int) -> str:
    """Simple heuristic label for competition level."""
    if avg_views >= 1_000_000:
        return "Very High"
    if avg_views >= 200_000:
        return "High"
    if avg_views >= 50_000:
        return "Medium"
    return "Low"


# ─────────────────────────────────────────────────────────────────────────────
#  YouTube API helpers
# ─────────────────────────────────────────────────────────────────────────────


def build_youtube_client(api_key: str):
    """Build and return a YouTube Data API v3 client."""
    return build("youtube", "v3", developerKey=api_key)


def _search_videos(yt, keyword: str, max_results: int = 10) -> list:
    resp = (
        yt.search()
        .list(
            part="snippet",
            q=keyword,
            type="video",
            order="relevance",
            maxResults=max_results,
        )
        .execute()
    )
    return resp.get("items", [])


def _get_video_details(yt, video_ids: list[str]) -> dict:
    resp = (
        yt.videos()
        .list(
            part="snippet,statistics",
            id=",".join(video_ids),
        )
        .execute()
    )
    return {v["id"]: v for v in resp.get("items", [])}


def _get_channel_details(yt, channel_ids: list[str]) -> dict:
    resp = (
        yt.channels()
        .list(
            part="snippet,statistics",
            id=",".join(channel_ids),
        )
        .execute()
    )
    return {c["id"]: c for c in resp.get("items", [])}


# ─────────────────────────────────────────────────────────────────────────────
#  Main analysis function
# ─────────────────────────────────────────────────────────────────────────────


def analyse_keyword(
    api_key: str,
    keyword: str,
    settings: dict | None = None,
    max_results: int = 10,
) -> dict:
    """
    Run a full KOS analysis for *keyword* using the YouTube Data API v3.

    Results are cached in-memory for CACHE_TTL_SECONDS (default 3600 s).
    Set CACHE_TTL_SECONDS=0 to disable caching.

    Returns a dict with:
      - keyword, kos, kos_label, kos_emoji, kos_color
      - score_a, score_b, score_c  (and their per-metric breakdowns)
      - max_a, max_b, max_c
      - avg_views, avg_like_ratio, avg_age_months, avg_comments, avg_vpm
      - kw_in_title, kw_in_desc, total_views
      - avg_subs, avg_ch_vid_count, avg_ch_age_y
      - competition_level  (Low / Medium / High / Very High)
      - videos  (list of top N video dicts)
      - top4_channels  (list of top 4 channel dicts, sorted by subs)
      - pts_a, pts_b, pts_c  (per-metric score breakdowns)

    On failure, returns {"error": "<message>", "keyword": keyword}.
    """
    if settings is None:
        settings = DEFAULT_SETTINGS.copy()

    # ── Cache lookup ──────────────────────────────────────────────────────────
    if _CACHE_TTL > 0:
        key = _cache_key(keyword, settings)
        now = time.time()
        with _cache_lock:
            entry = _cache.get(key)
            if entry is not None:
                result, expires_at = entry
                if now < expires_at:
                    return result
                del _cache[key]

    S = settings

    try:
        yt = build_youtube_client(api_key)
    except Exception as e:
        return {"error": f"Failed to build YouTube client: {e}", "keyword": keyword}

    try:
        search_items = _search_videos(yt, keyword, max_results)
    except HttpError as e:
        return {"error": f"YouTube API error: {e}", "keyword": keyword}

    if not search_items:
        return {"error": "No results found.", "keyword": keyword}

    video_ids: list[str] = []
    ch_ids_raw: list[str] = []
    for item in search_items:
        if (
            item.get("id")
            and isinstance(item["id"], dict)
            and "videoId" in item["id"]
            and item.get("snippet")
            and "channelId" in item["snippet"]
        ):
            video_ids.append(item["id"]["videoId"])
            ch_ids_raw.append(item["snippet"]["channelId"])

    if not video_ids:
        return {"error": "No valid video results found.", "keyword": keyword}

    try:
        vid_map = _get_video_details(yt, video_ids)
        unique_ch = list(dict.fromkeys(ch_ids_raw))
        chan_map = _get_channel_details(yt, unique_ch)
    except HttpError as e:
        return {"error": f"YouTube API error fetching details: {e}", "keyword": keyword}

    # ── Build video list ──────────────────────────────────────────────────────
    videos: list[dict] = []
    kw_in_title = kw_in_desc = total_views = total_likes = total_comments = 0
    age_months_list: list[float] = []

    for rank, vid_id in enumerate(video_ids, 1):
        v = vid_map.get(vid_id)
        if not v:
            continue

        title = v["snippet"].get("title", "")
        desc = v["snippet"].get("description", "")
        ch_id = v["snippet"].get("channelId", "")
        ch_name = v["snippet"].get("channelTitle", "")
        published = v["snippet"].get("publishedAt", "")
        views = int(v["statistics"].get("viewCount", 0))
        likes = int(v["statistics"].get("likeCount", 0))
        comments = int(v["statistics"].get("commentCount", 0))

        age_mo = months_since(parse_dt(published)) if published else 24.0
        age_months_list.append(age_mo)

        tc = count_kw(title, keyword)
        dc = count_kw(desc[:200], keyword)
        kw_in_title += tc
        kw_in_desc += dc
        total_views += views
        total_likes += likes
        total_comments += comments

        like_ratio = likes / views if views > 0 else 0.0
        vpm = views / age_mo if age_mo > 0 else 0.0

        m = re.search(re.escape(keyword), title, re.IGNORECASE)
        if m:
            pos_ratio = m.start() / max(len(title), 1)
            kw_pos_label = (
                "Start"
                if pos_ratio < 0.33
                else ("Middle" if pos_ratio < 0.66 else "End")
            )
        else:
            kw_pos_label = "—"

        videos.append(
            {
                "rank": rank,
                "title": title,
                "channel": ch_name,
                "channel_id": ch_id,
                "published": published[:10] if published else "—",
                "age_months": round(age_mo, 1),
                "views": views,
                "views_fmt": fmt_number(views),
                "likes": likes,
                "likes_fmt": fmt_number(likes),
                "like_ratio_pct": f"{like_ratio * 100:.2f}%",
                "comments": comments,
                "views_per_month": int(vpm),
                "views_per_month_fmt": fmt_number(int(vpm)),
                "kw_in_title": tc,
                "kw_pos_in_title": kw_pos_label,
                "kw_in_desc": dc,
                "url": f"https://youtu.be/{vid_id}",
            }
        )

    n = len(videos)
    avg_views = total_views / n if n else 0.0
    avg_comments = total_comments / n if n else 0.0
    avg_like_ratio = total_likes / total_views if total_views > 0 else 0.0
    avg_age_months = (
        sum(age_months_list) / len(age_months_list) if age_months_list else 24.0
    )
    avg_vpm = sum(v["views_per_month"] for v in videos) / n if n else 0.0

    # ── Build channel list ────────────────────────────────────────────────────
    channels: list[dict] = []
    for cid, c in chan_map.items():
        subs = int(c["statistics"].get("subscriberCount", 0))
        vids = int(c["statistics"].get("videoCount", 0))
        ttl_v = int(c["statistics"].get("viewCount", 0))
        pub = c["snippet"].get("publishedAt", "")
        ch_age = years_since(parse_dt(pub)) if pub else 3.0

        channels.append(
            {
                "channel": c["snippet"].get("title", ""),
                "subscribers": subs,
                "subscribers_fmt": fmt_number(subs),
                "videos": vids,
                "videos_fmt": fmt_number(vids),
                "total_views": ttl_v,
                "total_views_fmt": fmt_number(ttl_v),
                "channel_age_years": round(ch_age, 1),
                "url": f"https://www.youtube.com/channel/{cid}",
                "_subs": subs,
                "_vid_count": vids,
                "_age_years": ch_age,
            }
        )

    channels.sort(key=lambda x: x["_subs"], reverse=True)
    top4 = channels[:4]

    avg_subs = sum(c["_subs"] for c in top4) / len(top4) if top4 else 0.0
    avg_vid_count = sum(c["_vid_count"] for c in top4) / len(top4) if top4 else 0.0
    avg_ch_age_y = sum(c["_age_years"] for c in top4) / len(top4) if top4 else 3.0

    # ── KOS ───────────────────────────────────────────────────────────────────
    title_pos = kw_position_pts(videos, keyword, S["c_title_pos_pts"])
    pts_a = score_group_a(
        avg_views, avg_like_ratio, avg_age_months, avg_comments, avg_vpm, S
    )
    pts_b = score_group_b(avg_subs, avg_vid_count, avg_ch_age_y, S)
    pts_c = score_group_c(kw_in_title, kw_in_desc, title_pos, S)
    score_a = sum(pts_a.values())
    score_b = sum(pts_b.values())
    score_c = sum(pts_c.values())
    kos = min(100, round(score_a + score_b + score_c))

    label, emoji, color = kos_label(kos)

    # Remove internal-only keys before returning
    for c in top4:
        c.pop("_subs", None)
        c.pop("_vid_count", None)
        c.pop("_age_years", None)

    result = {
        "keyword": keyword,
        "kos": kos,
        "kos_label": label,
        "kos_emoji": emoji,
        "kos_color": color,
        "competition_level": competition_level(int(avg_views)),
        # ── aggregates ──────────────────────────────────────────────────────
        "total_views": int(total_views),
        "avg_views": int(avg_views),
        "avg_views_fmt": fmt_number(int(avg_views)),
        "avg_like_ratio": round(avg_like_ratio, 4),
        "avg_like_ratio_pct": f"{avg_like_ratio * 100:.2f}%",
        "avg_comments": int(avg_comments),
        "avg_age_months": round(avg_age_months, 1),
        "avg_vpm": int(avg_vpm),
        "avg_vpm_fmt": fmt_number(int(avg_vpm)),
        "kw_in_title": kw_in_title,
        "kw_in_desc": kw_in_desc,
        # ── channel aggregates ───────────────────────────────────────────────
        "avg_subs": int(avg_subs),
        "avg_subs_fmt": fmt_number(int(avg_subs)),
        "avg_ch_vid_count": int(avg_vid_count),
        "avg_ch_age_y": round(avg_ch_age_y, 1),
        # ── score breakdown ──────────────────────────────────────────────────
        "score_a": score_a,
        "score_b": score_b,
        "score_c": score_c,
        "max_a": max_group_a(S),
        "max_b": max_group_b(S),
        "max_c": max_group_c(S),
        "pts_a": pts_a,
        "pts_b": pts_b,
        "pts_c": pts_c,
        # ── detail lists ─────────────────────────────────────────────────────
        "videos": videos,
        "top4_channels": top4,
    }

    # ── Cache store ───────────────────────────────────────────────────────────
    if _CACHE_TTL > 0:
        with _cache_lock:
            _cache[key] = (result, time.time() + _CACHE_TTL)

    return result
