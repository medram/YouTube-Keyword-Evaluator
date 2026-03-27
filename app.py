"""
YouTube Keyword Evaluator — Streamlit App  (v2 — KOS Edition)
=============================================================
Run:
    pip install streamlit google-api-python-client pandas openpyxl xlrd
    streamlit run youtube_keyword_app.py
"""

import re
import time
import io
import math
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    st.error("Missing: `pip install google-api-python-client`")
    st.stop()

# ──────────────────────────────────────────────────────────────
#  Page config
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="YT Keyword Evaluator",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────
#  CSS
# ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'Syne', sans-serif !important; }
.main { background: #0d0d0f; }

.hero {
    background: linear-gradient(135deg, #0d0d0f 0%, #1a1025 50%, #0d0d0f 100%);
    border: 1px solid #2a2a3a; border-radius: 16px;
    padding: 2.5rem 2rem; margin-bottom: 1.5rem;
    position: relative; overflow: hidden;
}
.hero::before {
    content: ''; position: absolute; top: -60px; right: -60px;
    width: 220px; height: 220px;
    background: radial-gradient(circle, rgba(255,0,80,0.15) 0%, transparent 70%);
    pointer-events: none;
}
.hero h1 {
    font-size: 2.4rem !important; font-weight: 800 !important;
    background: linear-gradient(90deg, #ff0050, #ff6b35, #ffd700);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin: 0 0 0.4rem !important;
}
.hero p { color: #888; font-size: 1rem; margin: 0; }

/* KOS gauge card */
.kos-card {
    background: #0f0f18;
    border: 1px solid #2a2a3a;
    border-radius: 16px;
    padding: 1.8rem 1.5rem;
    text-align: center;
}
.kos-label {
    font-family: 'Syne', sans-serif;
    font-size: 1rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.1em;
    margin-top: 0.3rem;
}
.kos-sub { font-size: 0.78rem; color: #555; margin-top: 0.2rem; }

/* Score group cards */
.group-card {
    background: #111116;
    border: 1px solid #222230;
    border-radius: 12px;
    padding: 1.1rem 1.2rem;
    height: 100%;
}
.group-title {
    font-family: 'Syne', sans-serif;
    font-size: 0.72rem; text-transform: uppercase;
    letter-spacing: 0.12em; color: #555; margin-bottom: 0.5rem;
}
.group-score {
    font-family: 'Syne', sans-serif;
    font-size: 2rem; font-weight: 700; color: #fff;
}
.group-max { font-size: 0.8rem; color: #444; }
.group-bar-wrap { background: #1a1a2e; border-radius: 4px; height: 6px; margin-top: 0.7rem; }
.group-bar { height: 6px; border-radius: 4px; }

/* Small metric cards */
.metric-card {
    background: #111116;
    border: 1px solid #222230;
    border-radius: 12px; padding: 1rem 1.2rem; text-align: center;
}
.metric-value {
    font-family: 'Syne', sans-serif;
    font-size: 1.65rem; font-weight: 700; color: #fff;
}
.metric-label { font-size: 0.72rem; color: #555; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 2px; }

/* Section headers */
.section-header {
    font-family: 'Syne', sans-serif;
    font-size: 1rem; font-weight: 700; color: #ccc;
    text-transform: uppercase; letter-spacing: 0.1em;
    padding: 0.6rem 0; border-bottom: 1px solid #1e1e2e;
    margin-bottom: 0.8rem; margin-top: 0.4rem;
}

/* Score breakdown table */
.score-breakdown { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.score-breakdown th {
    text-align: left; font-family: 'Syne', sans-serif;
    font-size: 0.7rem; text-transform: uppercase;
    letter-spacing: 0.08em; color: #555;
    padding: 6px 8px; border-bottom: 1px solid #1e1e2e;
}
.score-breakdown td { padding: 7px 8px; border-bottom: 1px solid #16161e; color: #ccc; }
.score-breakdown td.pts { font-family: 'Syne', sans-serif; font-weight: 700; color: #fff; }
.score-breakdown tr:last-child td { border-bottom: none; }

[data-testid="stSidebar"] { background: #090910 !important; border-right: 1px solid #1e1e2e; }
[data-baseweb="tab"] { font-family: 'Syne', sans-serif !important; font-weight: 600; }
.stProgress > div > div { background: linear-gradient(90deg, #ff0050, #ff6b35) !important; }
a { color: #ff6b35 !important; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
#  Default Settings  (default total max = 40 + 32 + 28 = 100 pts)
# ──────────────────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    # ── Group A — Video Metrics (default max: 30 pts) ──────────
    # Bell-curve scoring: sweet spot = full pts, too low OR too high = fewer pts
    "a_avg_views_pts":      8,     # max pts for Avg Views
    "a_avg_views_lo":       100_000, # below → not proven yet (½ pts)
    "a_avg_views_hi1":      1_000_000,# sweet spot upper bound → full pts
    "a_avg_views_hi2":      10_000_000,# above → dominated (0 pts), between hi1-hi2 = ½ pts
    "a_video_age_pts":      8,     # max pts for Avg Video Age
    "a_video_age_lo_mo":    6,     # below → too new, unproven (½ pts)
    "a_video_age_hi1_mo":   4,     # sweet spot upper bound → full pts
    "a_video_age_hi2_mo":   18,    # above → old/stale (0 pts), between hi1-hi2 = ½ pts
    "a_vpm_pts":            9,     # max pts for Views per Month
    "a_vpm_lo":             500,   # below → dead niche (0 pts)
    "a_vpm_hi1":            1_000_000,# sweet spot upper bound → full pts
    "a_vpm_hi2":            2_000_000,# above → viral/dominated (0 pts), between = ½ pts
    "a_like_ratio_pts":     3,     # max pts for Like Ratio (lower weight)
    "a_like_ratio_lo":      0.1,   # below → not engaging (0 pts)
    "a_like_ratio_hi1":     2.0,   # sweet spot upper bound → full pts
    "a_like_ratio_hi2":     10.0,  # above → top channels dominate (0 pts), between = ½ pts
    "a_comments_pts":       2,     # max pts for Avg Comments (lower weight)
    "a_comments_lo":        10,    # below → not engaging (0 pts)
    "a_comments_hi1":       1_000,   # sweet spot upper bound → full pts
    "a_comments_hi2":       5_000, # above → dominated (0 pts), between = ½ pts
    # ── Group B — Channel Metrics (default max: 32 pts) ────────
    "b_subs_pts":           12,    # max pts for Avg Subscribers
    "b_subs_t1":            1_000_000,
    "b_subs_t2":            100_000,
    "b_subs_t3":            10_000,
    "b_vid_count_pts":      10,    # max pts for Avg Video Count
    "b_vid_count_t1":       500,   # > this → 0 pts
    "b_vid_count_t2":       100,   # ≥ this → half pts
    "b_ch_age_pts":         10,    # max pts for Avg Channel Age
    "b_ch_age_t1":          5.0,   # > this years → 0 pts
    "b_ch_age_t2":          2.0,   # ≥ this years → half pts
    # ── Group C — Saturation (default max: 38 pts) ─────────────
    "c_title_pts":          20,    # max pts for KW in Titles (more than desc)
    "c_title_t1":           3,     # ≤ this → high pts
    "c_title_t2":           7,     # ≤ this → medium pts
    "c_title_pos_pts":      5,     # max pts for KW Title Position
    "c_desc_pts":           13,    # max pts for KW in Descriptions
    "c_desc_t1":            3,     # ≤ this → high pts
    "c_desc_t2":            7,     # ≤ this → medium pts
}

if "settings" not in st.session_state:
    st.session_state.settings = DEFAULT_SETTINGS.copy()


# ──────────────────────────────────────────────────────────────
#  Utility helpers
# ──────────────────────────────────────────────────────────────

def fmt_number(n) -> str:
    n = int(n or 0)
    if n >= 1_000_000: return f"{n/1_000_000:.2f}M"
    if n >= 1_000:     return f"{n/1_000:.1f}K"
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


# ──────────────────────────────────────────────────────────────
#  Max point helpers (dynamic based on settings)
# ──────────────────────────────────────────────────────────────
def max_group_a(S: dict) -> int:
    return (S["a_avg_views_pts"] + S["a_video_age_pts"] + S["a_vpm_pts"]
            + S["a_like_ratio_pts"] + S["a_comments_pts"])

def max_group_b(S: dict) -> int:
    return S["b_subs_pts"] + S["b_vid_count_pts"] + S["b_ch_age_pts"]

def max_group_c(S: dict) -> int:
    return S["c_title_pts"] + S["c_title_pos_pts"] + S["c_desc_pts"]

def total_max(S: dict) -> int:
    return max_group_a(S) + max_group_b(S) + max_group_c(S)


# ──────────────────────────────────────────────────────────────
#  KOS Scoring  (default max = 40 + 32 + 28 = 100)
# ──────────────────────────────────────────────────────────────
def score_group_a(avg_views, avg_like_ratio, avg_age_months, avg_comments, avg_vpm, S: dict):
    """
    Bell-curve (inverted-V) scoring for all Group A metrics.
    Sweet spot = full points.  Too low (unproven niche) OR too high (dominated) = fewer points.
    """
    pts = {}

    # Avg Views — sweet spot = proven but not dominated
    P = S["a_avg_views_pts"]
    if   avg_views < S["a_avg_views_lo"]:   pts["Avg Views"] = round(P / 2)  # too few → unproven
    elif avg_views <= S["a_avg_views_hi1"]: pts["Avg Views"] = P              # ✓ sweet spot
    elif avg_views <= S["a_avg_views_hi2"]: pts["Avg Views"] = round(P / 2)  # competitive
    else:                                   pts["Avg Views"] = 0              # dominated

    # Avg Video Age — sweet spot = fresh but proven (not brand-new, not ancient)
    P = S["a_video_age_pts"]
    if   avg_age_months < S["a_video_age_lo_mo"]:   pts["Avg Video Age"] = round(P / 2)  # too new
    elif avg_age_months <= S["a_video_age_hi1_mo"]: pts["Avg Video Age"] = P              # ✓ sweet spot
    elif avg_age_months <= S["a_video_age_hi2_mo"]: pts["Avg Video Age"] = round(P / 2)  # getting old
    else:                                            pts["Avg Video Age"] = 0             # stale

    # Views per Month — sweet spot = active niche, not a viral giant
    P = S["a_vpm_pts"]
    if   avg_vpm < S["a_vpm_lo"]:   pts["Views per Month"] = 0              # dead niche
    elif avg_vpm <= S["a_vpm_hi1"]: pts["Views per Month"] = P              # ✓ sweet spot
    elif avg_vpm <= S["a_vpm_hi2"]: pts["Views per Month"] = round(P / 2)  # viral/competitive
    else:                           pts["Views per Month"] = 0              # dominated by viral content

    # Likes / Views Ratio — sweet spot = healthy engagement, not top-channel territory
    P = S["a_like_ratio_pts"]
    ratio_pct = avg_like_ratio * 100
    if   ratio_pct < S["a_like_ratio_lo"]:   pts["Likes / Views Ratio"] = 0              # not engaging
    elif ratio_pct <= S["a_like_ratio_hi1"]: pts["Likes / Views Ratio"] = P              # ✓ sweet spot
    elif ratio_pct <= S["a_like_ratio_hi2"]: pts["Likes / Views Ratio"] = round(P / 2)  # high (popular channels)
    else:                                    pts["Likes / Views Ratio"] = 0              # dominated

    # Avg Comments — sweet spot = active discussion, not overwhelmingly competitive
    P = S["a_comments_pts"]
    if   avg_comments < S["a_comments_lo"]:   pts["Avg Comments"] = 0              # not engaging
    elif avg_comments <= S["a_comments_hi1"]: pts["Avg Comments"] = P              # ✓ sweet spot
    elif avg_comments <= S["a_comments_hi2"]: pts["Avg Comments"] = round(P / 2)  # heavy competition
    else:                                     pts["Avg Comments"] = 0              # dominated

    return pts   # default max = 30


def score_group_b(avg_subs, avg_vid_count, avg_ch_age_years, S: dict):
    pts = {}

    P = S["b_subs_pts"]
    if   avg_subs >= S["b_subs_t1"]: pts["Avg Subscribers"] = 0
    elif avg_subs >= S["b_subs_t2"]: pts["Avg Subscribers"] = round(P * 1 / 3)
    elif avg_subs >= S["b_subs_t3"]: pts["Avg Subscribers"] = round(P * 2 / 3)
    else:                             pts["Avg Subscribers"] = P

    P = S["b_vid_count_pts"]
    if   avg_vid_count >  S["b_vid_count_t1"]: pts["Avg Video Count"] = 0
    elif avg_vid_count >= S["b_vid_count_t2"]: pts["Avg Video Count"] = round(P / 2)
    else:                                       pts["Avg Video Count"] = P

    P = S["b_ch_age_pts"]
    if   avg_ch_age_years >  S["b_ch_age_t1"]: pts["Avg Channel Age"] = 0
    elif avg_ch_age_years >= S["b_ch_age_t2"]: pts["Avg Channel Age"] = round(P / 2)
    else:                                       pts["Avg Channel Age"] = P

    return pts   # default max = 32


def kw_position_pts(videos: list, keyword: str, max_pts: int) -> int:
    """
    Score based on avg position of keyword in competing video titles.
    Start of title = most competitive = fewer opportunity pts.
    No keyword in any title = best opportunity = full pts.
    """
    positions = []
    for v in videos:
        m = re.search(re.escape(keyword), v["Title"], re.IGNORECASE)
        if m:
            pos_ratio = m.start() / max(len(v["Title"]), 1)  # 0=start, ~1=end
            positions.append(pos_ratio)

    if not positions:
        return max_pts  # No KW in any competing title → best opportunity

    avg_pos = sum(positions) / len(positions)
    return max(0, min(max_pts, round(avg_pos * max_pts)))


def score_group_c(kw_in_title: int, kw_in_desc: int, title_pos_score: int, S: dict):
    pts = {}

    # KW in Titles — FULL pts when 0, more max pts than descriptions
    P  = S["c_title_pts"]
    t1 = S["c_title_t1"]
    t2 = S["c_title_t2"]
    if   kw_in_title == 0:  pts["KW in Titles"] = P             # FULL points
    elif kw_in_title <= t1: pts["KW in Titles"] = round(P * 4 / 7)
    elif kw_in_title <= t2: pts["KW in Titles"] = round(P * 2 / 7)
    else:                   pts["KW in Titles"] = 1

    # KW Title Position — start of title = most competitive = fewer pts
    pts["KW Title Position"] = title_pos_score

    # KW in Descriptions — FULL pts when 0
    P  = S["c_desc_pts"]
    d1 = S["c_desc_t1"]
    d2 = S["c_desc_t2"]
    if   kw_in_desc == 0:  pts["KW in Descriptions"] = P        # FULL points
    elif kw_in_desc <= d1: pts["KW in Descriptions"] = round(P * 3 / 5)
    elif kw_in_desc <= d2: pts["KW in Descriptions"] = round(P * 1 / 5)
    else:                  pts["KW in Descriptions"] = 1

    return pts   # default max = 28


def kos_label(score: int):
    if score >= 75: return "Great Opportunity", "🟢", "#3ddc84"
    if score >= 50: return "Moderate",          "🟡", "#ffd700"
    if score >= 25: return "Tough",             "🟠", "#ff6b35"
    return              "Very Competitive",     "🔴", "#ff0050"


# ──────────────────────────────────────────────────────────────
#  YouTube API helpers
# ──────────────────────────────────────────────────────────────

@st.cache_resource
def get_youtube_client(api_key: str):
    return build("youtube", "v3", developerKey=api_key)


def search_videos(yt, keyword: str, max_results: int = 10):
    resp = yt.search().list(
        part="snippet", q=keyword, type="video",
        order="relevance", maxResults=max_results,
    ).execute()
    return resp.get("items", [])


def get_video_details(yt, video_ids):
    resp = yt.videos().list(
        part="snippet,statistics", id=",".join(video_ids)
    ).execute()
    return {v["id"]: v for v in resp.get("items", [])}


def get_channel_details(yt, channel_ids):
    resp = yt.channels().list(
        part="snippet,statistics", id=",".join(channel_ids)
    ).execute()
    return {c["id"]: c for c in resp.get("items", [])}


# ──────────────────────────────────────────────────────────────
#  Core analysis
# ──────────────────────────────────────────────────────────────

def analyse_keyword(yt, keyword: str, S: dict) -> dict:
    search_items = search_videos(yt, keyword, 10)
    if not search_items:
        return {"error": "No results found.", "keyword": keyword}

    video_ids  = []
    ch_ids_raw = []
    for item in search_items:
        if (item.get("id") and isinstance(item["id"], dict) and
                "videoId" in item["id"] and item.get("snippet") and
                "channelId" in item["snippet"]):
            video_ids.append(item["id"]["videoId"])
            ch_ids_raw.append(item["snippet"]["channelId"])

    if not video_ids:
        return {"error": "No valid video results found.", "keyword": keyword}

    vid_map   = get_video_details(yt, video_ids)
    unique_ch = list(dict.fromkeys(ch_ids_raw))
    chan_map   = get_channel_details(yt, unique_ch)

    # ── Build video list ─────────────────────────────────────
    videos = []
    kw_in_title = kw_in_desc = total_views = total_likes = total_comments = 0
    age_months_list = []

    for rank, vid_id in enumerate(video_ids, 1):
        v = vid_map.get(vid_id)
        if not v:
            continue
        title     = v["snippet"].get("title", "")
        desc      = v["snippet"].get("description", "")
        ch_id     = v["snippet"].get("channelId", "")
        ch_name   = v["snippet"].get("channelTitle", "")
        published = v["snippet"].get("publishedAt", "")
        views     = int(v["statistics"].get("viewCount",    0))
        likes     = int(v["statistics"].get("likeCount",    0))
        comments  = int(v["statistics"].get("commentCount", 0))

        age_mo = months_since(parse_dt(published)) if published else 24
        age_months_list.append(age_mo)

        tc = count_kw(title, keyword)
        dc = count_kw(desc[:200], keyword)
        kw_in_title    += tc
        kw_in_desc     += dc
        total_views    += views
        total_likes    += likes
        total_comments += comments

        like_ratio = likes / views if views > 0 else 0
        vpm        = views / age_mo if age_mo > 0 else 0

        # Determine keyword position label in title
        m = re.search(re.escape(keyword), title, re.IGNORECASE)
        if m:
            pos_ratio = m.start() / max(len(title), 1)
            if pos_ratio < 0.33:
                kw_pos_label = "Start"
            elif pos_ratio < 0.66:
                kw_pos_label = "Middle"
            else:
                kw_pos_label = "End"
        else:
            kw_pos_label = "—"

        videos.append({
            "Rank":              rank,
            "Title":             title,
            "Channel":           ch_name,
            "Published":         published[:10] if published else "—",
            "Age (months)":      round(age_mo, 1),
            "Views":             views,
            "Views (fmt)":       fmt_number(views),
            "Likes":             likes,
            "Likes (fmt)":       fmt_number(likes),
            "Like Ratio":        f"{like_ratio*100:.2f}%",
            "Comments":          comments,
            "Views per Month":   vpm,
            "Views/Month (fmt)": fmt_number(int(vpm)),
            "KW in Title":       tc,
            "KW Pos in Title":   kw_pos_label,
            "KW in Desc":        dc,
            "URL":               f"https://youtu.be/{vid_id}",
            "channel_id":        ch_id,
        })

    n = len(videos)
    avg_views      = total_views    / n if n else 0
    avg_comments   = total_comments / n if n else 0
    avg_like_ratio = total_likes / total_views if total_views > 0 else 0
    avg_age_months = sum(age_months_list) / len(age_months_list) if age_months_list else 24
    avg_vpm        = sum(v["Views per Month"] for v in videos) / n if n else 0

    # ── Build channel list ───────────────────────────────────
    channels = []
    for cid, c in chan_map.items():
        subs   = int(c["statistics"].get("subscriberCount", 0))
        vids   = int(c["statistics"].get("videoCount",      0))
        ttl_v  = int(c["statistics"].get("viewCount",       0))
        pub    = c["snippet"].get("publishedAt", "")
        ch_age = years_since(parse_dt(pub)) if pub else 3.0

        channels.append({
            "Channel":           c["snippet"].get("title", ""),
            "Subscribers":       subs,
            "Subs (fmt)":        fmt_number(subs),
            "Videos":            vids,
            "Videos (fmt)":      fmt_number(vids),
            "Total Views":       ttl_v,
            "Total Views (fmt)": fmt_number(ttl_v),
            "Channel Age (yr)":  round(ch_age, 1),
            "URL":               f"https://www.youtube.com/channel/{cid}",
            "_subs":             subs,
            "_vid_count":        vids,
            "_age_years":        ch_age,
        })

    channels.sort(key=lambda x: x["_subs"], reverse=True)
    top4 = channels[:4]

    avg_subs      = sum(c["_subs"]      for c in top4) / len(top4) if top4 else 0
    avg_vid_count = sum(c["_vid_count"] for c in top4) / len(top4) if top4 else 0
    avg_ch_age_y  = sum(c["_age_years"] for c in top4) / len(top4) if top4 else 3.0

    # ── KOS ──────────────────────────────────────────────────
    title_pos = kw_position_pts(videos, keyword, S["c_title_pos_pts"])
    pts_a     = score_group_a(avg_views, avg_like_ratio, avg_age_months, avg_comments, avg_vpm, S)
    pts_b     = score_group_b(avg_subs, avg_vid_count, avg_ch_age_y, S)
    pts_c     = score_group_c(kw_in_title, kw_in_desc, title_pos, S)
    score_a   = sum(pts_a.values())
    score_b   = sum(pts_b.values())
    score_c   = sum(pts_c.values())
    kos       = min(100, round(score_a + score_b + score_c))

    label, emoji, color = kos_label(kos)

    return {
        "keyword":          keyword,
        "videos":           videos,
        "top4_channels":    top4,
        "total_views":      int(total_views),
        "avg_views":        int(avg_views),
        "avg_comments":     int(avg_comments),
        "avg_like_ratio":   avg_like_ratio,
        "avg_age_months":   avg_age_months,
        "avg_vpm":          int(avg_vpm),
        "kw_in_title":      kw_in_title,
        "kw_in_desc":       kw_in_desc,
        "kos":              kos,
        "kos_label":        label,
        "kos_emoji":        emoji,
        "kos_color":        color,
        "score_a":          score_a,
        "score_b":          score_b,
        "score_c":          score_c,
        "pts_a":            pts_a,
        "pts_b":            pts_b,
        "pts_c":            pts_c,
        "max_a":            max_group_a(S),
        "max_b":            max_group_b(S),
        "max_c":            max_group_c(S),
        "avg_subs":         int(avg_subs),
        "avg_ch_vid_count": int(avg_vid_count),
        "avg_ch_age_y":     round(avg_ch_age_y, 1),
    }


# ──────────────────────────────────────────────────────────────
#  HTML rendering helpers
# ──────────────────────────────────────────────────────────────

def kos_gauge_html(kos: int, label: str, emoji: str, color: str) -> str:
    cx, cy, r = 110, 100, 80
    circumference = math.pi * r
    fill = circumference * (kos / 100)
    gap  = circumference - fill
    return f"""
<div class="kos-card">
  <svg viewBox="0 0 220 120" width="220" style="display:block;margin:0 auto -18px;">
    <path d="M {cx-r} {cy} A {r} {r} 0 0 1 {cx+r} {cy}"
          fill="none" stroke="#1a1a2e" stroke-width="14" stroke-linecap="round"/>
    <path d="M {cx-r} {cy} A {r} {r} 0 0 1 {cx+r} {cy}"
          fill="none" stroke="{color}" stroke-width="14" stroke-linecap="round"
          stroke-dasharray="{fill:.2f} {gap:.2f}"/>
    <text x="{cx}" y="{cy+4}" text-anchor="middle"
          font-family="Syne,sans-serif" font-size="32" font-weight="800"
          fill="{color}">{kos}</text>
    <text x="{cx}" y="{cy+22}" text-anchor="middle"
          font-family="DM Sans,sans-serif" font-size="9" fill="#555">/100</text>
  </svg>
  <div class="kos-label" style="color:{color}">{emoji} {label}</div>
  <div class="kos-sub">Keyword Opportunity Score — higher = easier to rank</div>
</div>
"""


def group_bar_html(score, max_score, color, title, breakdown: dict) -> str:
    pct  = round((score / max_score) * 100)
    rows = "".join(
        f"<tr><td>{m}</td><td class='pts'>{p}</td></tr>"
        for m, p in breakdown.items()
    )
    total = f"<tr style='border-top:1px solid #2a2a3a'><td><b>Total</b></td><td class='pts'><b>{score}/{max_score}</b></td></tr>"
    return f"""
<div class="group-card">
  <div class="group-title">{title}</div>
  <span class="group-score" style="color:{color}">{score}</span>
  <span class="group-max"> / {max_score}</span>
  <div class="group-bar-wrap">
    <div class="group-bar" style="width:{pct}%;background:{color}"></div>
  </div>
  <br>
  <table class="score-breakdown">
    <thead><tr><th>Metric</th><th>Pts</th></tr></thead>
    <tbody>{rows}{total}</tbody>
  </table>
</div>
"""


# ──────────────────────────────────────────────────────────────
#  Render one keyword result
# ──────────────────────────────────────────────────────────────

def render_result(res: dict):
    # Row 1 — KOS gauge + 3 group breakdown cards
    col_gauge, col_a, col_b, col_c = st.columns([2, 1.5, 1.5, 1.5])

    with col_gauge:
        st.markdown(
            kos_gauge_html(res["kos"], res["kos_label"], res["kos_emoji"], res["kos_color"]),
            unsafe_allow_html=True,
        )
    with col_a:
        st.markdown(
            group_bar_html(res["score_a"], res["max_a"], "#4fc3f7",
                           "Group A — Videos", res["pts_a"]),
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown(
            group_bar_html(res["score_b"], res["max_b"], "#ce93d8",
                           "Group B — Channels", res["pts_b"]),
            unsafe_allow_html=True,
        )
    with col_c:
        st.markdown(
            group_bar_html(res["score_c"], res["max_c"], "#ffb74d",
                           "Group C — Saturation", res["pts_c"]),
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Row 2 — supporting metric strip
    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    for col, label, val in [
        (m1, "👁️ Avg Views",      fmt_number(res["avg_views"])),
        (m2, "👍 Avg Like Ratio", f"{res['avg_like_ratio']*100:.2f}%"),
        (m3, "💬 Avg Comments",   fmt_number(res["avg_comments"])),
        (m4, "📅 Avg Video Age",  f"{res['avg_age_months']:.0f} mo"),
        (m5, "🚀 Views/Month",    fmt_number(res["avg_vpm"])),
        (m6, "🔤 KW in Titles",   str(res["kw_in_title"])),
        (m7, "📝 KW in Descs",    str(res["kw_in_desc"])),
    ]:
        with col:
            st.markdown(
                f'<div class="metric-card">'
                f'<div class="metric-value">{val}</div>'
                f'<div class="metric-label">{label}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # Top 4 channels
    st.markdown('<div class="section-header">📺 Top 4 Channels by Subscribers</div>',
                unsafe_allow_html=True)
    ch_df = pd.DataFrame(res["top4_channels"])[[
        "Channel", "Subs (fmt)", "Videos (fmt)",
        "Total Views (fmt)", "Channel Age (yr)", "URL",
    ]].rename(columns={
        "Subs (fmt)": "Subscribers", "Videos (fmt)": "Videos",
        "Total Views (fmt)": "Total Views", "Channel Age (yr)": "Age (yrs)",
    })
    ch_df.index = range(1, len(ch_df) + 1)
    st.dataframe(ch_df, use_container_width=True,
                 column_config={"URL": st.column_config.LinkColumn("Channel URL")})

    st.markdown("<br>", unsafe_allow_html=True)

    # Top 10 videos
    st.markdown('<div class="section-header">🎬 Top 10 Videos</div>', unsafe_allow_html=True)
    vid_df = pd.DataFrame(res["videos"])[[
        "Rank", "Title", "Channel", "Published",
        "Views (fmt)", "Likes (fmt)", "Like Ratio",
        "Views/Month (fmt)", "Comments",
        "KW in Title", "KW Pos in Title", "KW in Desc", "URL",
    ]].rename(columns={
        "Views (fmt)": "Views", "Likes (fmt)": "Likes",
        "Views/Month (fmt)": "Views/Mo",
        "KW Pos in Title": "KW Position",
    }).set_index("Rank")
    st.dataframe(vid_df, use_container_width=True,
                 column_config={"URL": st.column_config.LinkColumn("Video URL")})

    st.markdown("<br>", unsafe_allow_html=True)

    # Keyword frequency bar chart
    st.markdown('<div class="section-header">🔤 Keyword Frequency per Video</div>',
                unsafe_allow_html=True)
    freq_df = pd.DataFrame({
        "Video":          [f"#{v['Rank']} {v['Title'][:38]}…" for v in res["videos"]],
        "In Title":       [v["KW in Title"] for v in res["videos"]],
        "In Description": [v["KW in Desc"]  for v in res["videos"]],
    }).set_index("Video")
    st.bar_chart(freq_df, color=["#4fc3f7", "#ffb74d"])


# ──────────────────────────────────────────────────────────────
#  Excel export
# ──────────────────────────────────────────────────────────────

def results_to_excel(results: list) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        summary_rows = []
        for r in results:
            if "error" in r:
                summary_rows.append({
                    "Keyword": r.get("keyword", ""), "KOS": "ERROR",
                    "Label": "", "Score A": "", "Score B": "", "Score C": "",
                    "Avg Views": "", "KW Titles": "", "KW Descs": "",
                })
            else:
                summary_rows.append({
                    "Keyword":              r["keyword"],
                    "KOS":                  r["kos"],
                    "Label":                r["kos_label"],
                    f"Score A /{r['max_a']}": r["score_a"],
                    f"Score B /{r['max_b']}": r["score_b"],
                    f"Score C /{r['max_c']}": r["score_c"],
                    "Avg Views":            r["avg_views"],
                    "Total Views":          r["total_views"],
                    "Avg Like Ratio":       f"{r['avg_like_ratio']*100:.2f}%",
                    "Avg Comments":         r["avg_comments"],
                    "Avg Video Age (mo)":   round(r["avg_age_months"], 1),
                    "KW in Titles":         r["kw_in_title"],
                    "KW in Descs":          r["kw_in_desc"],
                    "Avg Subs (top4)":      r["avg_subs"],
                    "Avg Ch Age (yr)":      r["avg_ch_age_y"],
                })
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary", index=False)

        for r in results:
            if "error" in r:
                continue
            safe = r["keyword"][:25].replace("/", "_").replace("\\", "_").replace("*", "_")

            # Videos sheet
            pd.DataFrame(r["videos"])[[
                "Rank", "Title", "Channel", "Published", "Views", "Likes",
                "Like Ratio", "Views per Month", "Comments",
                "KW in Title", "KW Pos in Title", "KW in Desc", "URL",
            ]].to_excel(writer, sheet_name=f"{safe}_videos", index=False)

            # Channels sheet
            pd.DataFrame(r["top4_channels"])[[
                "Channel", "Subscribers", "Videos", "Total Views", "Channel Age (yr)", "URL",
            ]].to_excel(writer, sheet_name=f"{safe}_channels", index=False)

            # Score breakdown sheet
            bd_rows = (
                [{"Group": "A — Videos",    "Metric": m, "Points": p}
                 for m, p in r["pts_a"].items()] +
                [{"Group": "B — Channels",  "Metric": m, "Points": p}
                 for m, p in r["pts_b"].items()] +
                [{"Group": "C — Saturation", "Metric": m, "Points": p}
                 for m, p in r["pts_c"].items()] +
                [{"Group": "TOTAL", "Metric": "KOS", "Points": r["kos"]}]
            )
            pd.DataFrame(bd_rows).to_excel(writer, sheet_name=f"{safe}_score", index=False)

    return buf.getvalue()


# ──────────────────────────────────────────────────────────────
#  SIDEBAR
# ──────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️ API Setup")
    api_key = st.text_input(
        "YouTube Data API v3 Key", type="password", placeholder="AIza…",
        help="console.cloud.google.com → Enable YouTube Data API v3",
    )
    st.markdown("---")
    st.markdown("""
**How to get an API key**
1. [Google Cloud Console](https://console.cloud.google.com/)
2. Create / select a project
3. Enable **YouTube Data API v3**
4. Credentials → Create API Key
5. Paste it above ☝️

**Free quota:** ~10,000 units/day  
Each keyword uses ~6–10 units.
""")
    st.markdown("---")
    st.markdown("### 📐 KOS Scale")
    st.markdown("""
| Score | Label |
|---|---|
| 75–100 | 🟢 Great Opportunity |
| 50–74  | 🟡 Moderate |
| 25–49  | 🟠 Tough |
| 0–24   | 🔴 Very Competitive |

**Higher score = easier to rank**

**Groups (default):**
- **A (max 30)** — Bell-curve: avg views, video age, views/month, like ratio, comments (sweet spot = full pts)
- **B (max 32)** — Channel subs, video count, channel age
- **C (max 38)** — KW in titles, KW title position, KW in descs

*Adjust weights & thresholds in the **⚙️ Settings** tab.*
""")
    st.markdown("---")
    st.markdown("**Made with** `streamlit` + YouTube API v3")


# ──────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────

st.markdown("""
<div class="hero">
    <h1>🎬 YouTube Keyword Evaluator</h1>
    <p>Keyword Opportunity Score (KOS/100) — built from video stats, channel authority &amp; content saturation.</p>
</div>
""", unsafe_allow_html=True)

if not api_key:
    st.info("👈 Enter your YouTube Data API v3 key in the sidebar to get started.")
    st.stop()

try:
    yt = get_youtube_client(api_key)
except Exception as e:
    st.error(f"Failed to initialise YouTube client: {e}")
    st.stop()

tab_single, tab_bulk, tab_settings = st.tabs([
    "🔍 Single Keyword", "📂 Bulk / CSV Upload", "⚙️ Settings",
])


# ════════════════════════════════════════════
#  TAB 1 — Single keyword
# ════════════════════════════════════════════
with tab_single:
    col_input, col_btn = st.columns([5, 1])
    with col_input:
        keyword = st.text_input("Enter a keyword", placeholder="e.g. coffee and jazz",
                                label_visibility="collapsed")
    with col_btn:
        analyse_btn = st.button("Analyse →", type="primary", use_container_width=True)

    if analyse_btn and keyword.strip():
        with st.spinner(f"Analysing **{keyword}** …"):
            try:
                S = st.session_state.settings
                res = analyse_keyword(yt, keyword.strip(), S)
                if "error" in res:
                    st.error(res["error"])
                else:
                    render_result(res)
                    xlsx = results_to_excel([res])
                    st.download_button(
                        "⬇️ Download Results (Excel)",
                        data=xlsx,
                        file_name=f"yt_{keyword.strip().replace(' ', '_')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
            except HttpError as e:
                st.error(f"YouTube API error: {e}")


# ════════════════════════════════════════════
#  TAB 2 — Bulk upload
# ════════════════════════════════════════════
with tab_bulk:
    st.markdown("""
Upload a **CSV** or **Excel** file with a column of keywords (first column is used, header optional).  
Each row is processed one by one with a live progress table.
""")

    template_csv = pd.DataFrame({
        "keyword": ["coffee and jazz", "lofi study music", "morning yoga routine"]
    }).to_csv(index=False).encode()
    st.download_button("⬇️ Download template CSV", template_csv,
                       file_name="keywords_template.csv", mime="text/csv")

    uploaded = st.file_uploader("Upload keywords file", type=["csv", "xlsx", "xls"])

    if uploaded:
        try:
            df_kw = (pd.read_csv(uploaded) if uploaded.name.endswith(".csv")
                     else pd.read_excel(uploaded))
            keywords_list = (df_kw.iloc[:, 0].dropna().astype(str)
                             .str.strip().tolist())
            keywords_list = [k for k in keywords_list if k]
            st.success(f"✅ Loaded **{len(keywords_list)} keywords** from `{uploaded.name}`")
            st.dataframe(pd.DataFrame({"Keywords": keywords_list}),
                         use_container_width=True, height=180)
        except Exception as e:
            st.error(f"Could not read file: {e}")
            st.stop()

        run_bulk = st.button("🚀 Run Bulk Analysis", type="primary")

        if run_bulk:
            S = st.session_state.settings
            progress_bar  = st.progress(0, text="Starting…")
            status_table  = st.empty()
            results_store = []
            status_rows   = []

            for i, kw in enumerate(keywords_list):
                progress_bar.progress(
                    i / len(keywords_list),
                    text=f"Analysing {i+1}/{len(keywords_list)}: **{kw}**",
                )
                try:
                    res = analyse_keyword(yt, kw, S)
                    if "error" in res:
                        status_rows.append({
                            "Keyword": kw, "Status": "❌ No results",
                            "KOS": "—", "Label": "—", "A": "—", "B": "—", "C": "—",
                            "Avg Views": "—",
                        })
                    else:
                        results_store.append(res)
                        status_rows.append({
                            "Keyword":               kw,
                            "Status":                "✅ Done",
                            "KOS":                   res["kos"],
                            "Label":                 f"{res['kos_emoji']} {res['kos_label']}",
                            f"A /{res['max_a']}":     res["score_a"],
                            f"B /{res['max_b']}":     res["score_b"],
                            f"C /{res['max_c']}":     res["score_c"],
                            "Avg Views":             fmt_number(res["avg_views"]),
                        })
                except HttpError:
                    status_rows.append({
                        "Keyword": kw, "Status": "❌ API Error",
                        "KOS": "—", "Label": "—", "A": "—", "B": "—", "C": "—",
                        "Avg Views": "—",
                    })

                status_table.dataframe(pd.DataFrame(status_rows), use_container_width=True)
                if i < len(keywords_list) - 1:
                    time.sleep(0.3)

            progress_bar.progress(1.0, text="✅ All done!")

            if results_store:
                st.markdown("---")
                st.markdown("### 📊 Bulk Summary — sorted by KOS ↓")
                summary_df = pd.DataFrame([{
                    "Keyword":   r["keyword"],
                    "KOS":       r["kos"],
                    "Label":     f"{r['kos_emoji']} {r['kos_label']}",
                    "Score A":   r["score_a"],
                    "Score B":   r["score_b"],
                    "Score C":   r["score_c"],
                    "Avg Views": fmt_number(r["avg_views"]),
                    "KW Titles": r["kw_in_title"],
                    "KW Descs":  r["kw_in_desc"],
                } for r in results_store]).sort_values("KOS", ascending=False)
                st.dataframe(summary_df, use_container_width=True)

                st.markdown("### 🔍 Detailed Results per Keyword")
                for res in sorted(results_store, key=lambda x: x["kos"], reverse=True):
                    hdr = (f"📌 {res['keyword']}  —  "
                           f"{res['kos_emoji']} {res['kos_label']}  |  KOS: {res['kos']}/100")
                    with st.expander(hdr):
                        render_result(res)

                xlsx = results_to_excel(results_store)
                st.download_button(
                    "⬇️ Download All Results (Excel)",
                    data=xlsx,
                    file_name="yt_bulk_keyword_analysis.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )


# ════════════════════════════════════════════
#  TAB 3 — Settings
# ════════════════════════════════════════════
with tab_settings:
    S = st.session_state.settings

    st.markdown("### ⚙️ Scoring Settings")
    st.info(
        "Changes take effect on the **next analysis run**. "
        "The default distribution targets exactly **100 total points** (A=30, B=32, C=38).",
        icon="ℹ️",
    )

    st.markdown("---")

    # ── GROUP A ──────────────────────────────────────────────
    with st.expander("📹 Group A — Video Metrics", expanded=True):
        st.info(
            "All Group A metrics use **bell-curve scoring**: a sweet spot in the middle earns full points.  \n"
            "Too low = unproven niche (½ pts). Too high = dominated by established channels (0–½ pts).  \n"
            "The goal: find keywords where the top 10 videos are active and proven, but not giants you can't compete with.",
            icon="🔔",
        )
        st.markdown("##### Point Allocation")
        ga1, ga2, ga3, ga4, ga5 = st.columns(5)
        with ga1:
            S["a_avg_views_pts"] = st.slider(
                "Avg Views (pts)", 0, 30, S["a_avg_views_pts"],
                key="sset_a_avg_views_pts",
                help="Full pts when views are in the proven-but-not-dominated sweet spot.")
        with ga2:
            S["a_video_age_pts"] = st.slider(
                "Video Age (pts)", 0, 20, S["a_video_age_pts"],
                key="sset_a_video_age_pts",
                help="Full pts when videos are fresh-but-proven (not brand new, not ancient).")
        with ga3:
            S["a_vpm_pts"] = st.slider(
                "Views/Month (pts)", 0, 15, S["a_vpm_pts"],
                key="sset_a_vpm_pts",
                help="Full pts when views/month are moderate — niche is alive but not dominated by viral giants.")
        with ga4:
            S["a_like_ratio_pts"] = st.slider(
                "Like Ratio (pts)", 0, 10, S["a_like_ratio_pts"],
                key="sset_a_like_ratio_pts",
                help="Full pts when like ratio is healthy. Too low = unengaging. Too high = top-channel territory.")
        with ga5:
            S["a_comments_pts"] = st.slider(
                "Avg Comments (pts)", 0, 10, S["a_comments_pts"],
                key="sset_a_comments_pts",
                help="Full pts when comments are active but not overwhelmingly competitive.")

        st.markdown("##### Sweet Spot Thresholds *(bell-curve boundaries)*")
        st.caption("Each metric has a **lower bound** (unproven below it) and an **upper bound** (sweet spot end). Above the upper bound = too competitive.")
        t1, t2, t3 = st.columns(3)
        with t1:
            st.markdown("**Avg Views**")
            S["a_avg_views_lo"] = st.number_input(
                "🔻 Too few (½ pts) — below", value=S["a_avg_views_lo"], step=10_000,
                key="sset_a_avg_views_lo", format="%d",
                help="Below this = not enough views to prove the niche.")
            S["a_avg_views_hi1"] = st.number_input(
                "✅ Sweet spot upper — below", value=S["a_avg_views_hi1"], step=100_000,
                key="sset_a_avg_views_hi1", format="%d",
                help="Sweet spot: between lower bound and this = full pts.")
            S["a_avg_views_hi2"] = st.number_input(
                "🔺 Dominated (0 pts) — above", value=S["a_avg_views_hi2"], step=1_000_000,
                key="sset_a_avg_views_hi2", format="%d",
                help="Above this = niche dominated by big channels.")
            st.markdown("**Avg Comments**")
            S["a_comments_lo"] = st.number_input(
                "🔻 Not engaging (0 pts) — below", value=S["a_comments_lo"], step=5,
                key="sset_a_comments_lo", format="%d")
            S["a_comments_hi1"] = st.number_input(
                "✅ Sweet spot upper — below", value=S["a_comments_hi1"], step=100,
                key="sset_a_comments_hi1", format="%d")
            S["a_comments_hi2"] = st.number_input(
                "🔺 Dominated (0 pts) — above", value=S["a_comments_hi2"], step=500,
                key="sset_a_comments_hi2", format="%d")
        with t2:
            st.markdown("**Avg Video Age (months)**")
            S["a_video_age_lo_mo"] = st.slider(
                "🔻 Too new (½ pts) — below", 1, 6, S["a_video_age_lo_mo"],
                key="sset_a_video_age_lo_mo",
                help="Below this many months = too new, topic not proven yet.")
            S["a_video_age_hi1_mo"] = st.slider(
                "✅ Sweet spot upper — below", 6, 30, S["a_video_age_hi1_mo"],
                key="sset_a_video_age_hi1_mo",
                help="Sweet spot end. Videos younger than this = proven & fresh.")
            S["a_video_age_hi2_mo"] = st.slider(
                "🔺 Stale (0 pts) — above", 18, 72, S["a_video_age_hi2_mo"],
                key="sset_a_video_age_hi2_mo",
                help="Above this = topic is old/stale.")
            st.markdown("**Like Ratio (%)**")
            S["a_like_ratio_lo"] = st.slider(
                "🔻 Not engaging (0 pts) — below (%)", 0.0, 2.0, float(S["a_like_ratio_lo"]),
                step=0.1, key="sset_a_like_ratio_lo")
            S["a_like_ratio_hi1"] = st.slider(
                "✅ Sweet spot upper — below (%)", 1.0, 10.0, float(S["a_like_ratio_hi1"]),
                step=0.5, key="sset_a_like_ratio_hi1")
            S["a_like_ratio_hi2"] = st.slider(
                "🔺 Dominated (0 pts) — above (%)", 5.0, 25.0, float(S["a_like_ratio_hi2"]),
                step=0.5, key="sset_a_like_ratio_hi2")
        with t3:
            st.markdown("**Views per Month**")
            S["a_vpm_lo"] = st.number_input(
                "🔻 Dead niche (0 pts) — below", value=S["a_vpm_lo"], step=100,
                key="sset_a_vpm_lo", format="%d",
                help="Below this = barely any traction in the niche.")
            S["a_vpm_hi1"] = st.number_input(
                "✅ Sweet spot upper — below", value=S["a_vpm_hi1"], step=10_000,
                key="sset_a_vpm_hi1", format="%d",
                help="Sweet spot end. Moderate views/month = active but beatable.")
            S["a_vpm_hi2"] = st.number_input(
                "🔺 Viral/dominated (0 pts) — above", value=S["a_vpm_hi2"], step=100_000,
                key="sset_a_vpm_hi2", format="%d",
                help="Above this = viral content dominating the niche.")

    # ── GROUP B ──────────────────────────────────────────────
    with st.expander("📺 Group B — Channel Metrics", expanded=False):
        st.markdown("##### Point Allocation")
        gb1, gb2, gb3 = st.columns(3)
        with gb1:
            S["b_subs_pts"] = st.slider(
                "Avg Subscribers (pts)", 0, 25, S["b_subs_pts"],
                key="sset_b_subs_pts")
        with gb2:
            S["b_vid_count_pts"] = st.slider(
                "Avg Video Count (pts)", 0, 20, S["b_vid_count_pts"],
                key="sset_b_vid_count_pts")
        with gb3:
            S["b_ch_age_pts"] = st.slider(
                "Avg Channel Age (pts)", 0, 20, S["b_ch_age_pts"],
                key="sset_b_ch_age_pts")

        st.markdown("##### Thresholds")
        tb1, tb2, tb3 = st.columns(3)
        with tb1:
            st.markdown("**Avg Subscribers**")
            S["b_subs_t1"] = st.number_input(
                "Very large (0 pts) ≥", value=S["b_subs_t1"], step=100_000,
                key="sset_b_subs_t1", format="%d")
            S["b_subs_t2"] = st.number_input(
                "Large (⅓ pts) ≥", value=S["b_subs_t2"], step=10_000,
                key="sset_b_subs_t2", format="%d")
            S["b_subs_t3"] = st.number_input(
                "Medium (⅔ pts) ≥", value=S["b_subs_t3"], step=1_000,
                key="sset_b_subs_t3", format="%d")
        with tb2:
            st.markdown("**Avg Video Count**")
            S["b_vid_count_t1"] = st.number_input(
                "Very many (0 pts) >", value=S["b_vid_count_t1"], step=50,
                key="sset_b_vid_count_t1", format="%d")
            S["b_vid_count_t2"] = st.number_input(
                "Many (½ pts) ≥", value=S["b_vid_count_t2"], step=10,
                key="sset_b_vid_count_t2", format="%d")
        with tb3:
            st.markdown("**Avg Channel Age (years)**")
            S["b_ch_age_t1"] = st.slider(
                "Old (0 pts) >", 1.0, 15.0, float(S["b_ch_age_t1"]),
                step=0.5, key="sset_b_ch_age_t1")
            S["b_ch_age_t2"] = st.slider(
                "Established (½ pts) ≥", 0.5, 10.0, float(S["b_ch_age_t2"]),
                step=0.5, key="sset_b_ch_age_t2")

    # ── GROUP C ──────────────────────────────────────────────
    with st.expander("📝 Group C — Content Saturation", expanded=False):
        st.info(
            "**KW in Titles** gives full points when 0 competing videos use the keyword in their title.  \n"
            "**KW Title Position** rewards keywords found at the *end* of titles (less competitive than the start).  \n"
            "**KW in Titles** always has more total points than **KW in Descriptions** by design.",
            icon="💡",
        )
        st.markdown("##### Point Allocation")
        gc1, gc2, gc3 = st.columns(3)
        with gc1:
            S["c_title_pts"] = st.slider(
                "KW in Titles (pts)", 0, 25, S["c_title_pts"],
                key="sset_c_title_pts",
                help="More than KW in Descriptions by design. Full pts when 0 KW found in titles.")
        with gc2:
            S["c_title_pos_pts"] = st.slider(
                "KW Title Position (pts)", 0, 10, S["c_title_pos_pts"],
                key="sset_c_title_pos_pts",
                help="Full pts when KW is at end of title (least competitive). 0 pts = KW at start.")
        with gc3:
            S["c_desc_pts"] = st.slider(
                "KW in Descriptions (pts)", 0, 20, S["c_desc_pts"],
                key="sset_c_desc_pts",
                help="Full pts when 0 KW found in descriptions.")

        st.markdown("##### Thresholds")
        tc1, tc2 = st.columns(2)
        with tc1:
            st.markdown("**KW in Titles** *(total count across top-10 videos)*")
            S["c_title_t1"] = st.slider(
                "Few (4/7 pts) — count ≤", 1, 10, S["c_title_t1"],
                key="sset_c_title_t1")
            S["c_title_t2"] = st.slider(
                "Medium (2/7 pts) — count ≤", 2, 15, S["c_title_t2"],
                key="sset_c_title_t2")
        with tc2:
            st.markdown("**KW in Descriptions** *(total count across top-10 videos)*")
            S["c_desc_t1"] = st.slider(
                "Few (3/5 pts) — count ≤", 1, 10, S["c_desc_t1"],
                key="sset_c_desc_t1")
            S["c_desc_t2"] = st.slider(
                "Medium (1/5 pts) — count ≤", 2, 15, S["c_desc_t2"],
                key="sset_c_desc_t2")

    # ── Live totals (shown after sliders so values are current) ─
    st.markdown("---")
    st.markdown("#### 📊 Current Point Totals")
    cur_max = total_max(S)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Max Points", f"{cur_max} / 100",
              delta="✓ On target" if cur_max == 100 else f"{cur_max - 100:+d} vs 100",
              delta_color="normal" if cur_max == 100 else "inverse")
    c2.metric("Group A — Videos",     f"{max_group_a(S)} pts")
    c3.metric("Group B — Channels",   f"{max_group_b(S)} pts")
    c4.metric("Group C — Saturation", f"{max_group_c(S)} pts")
    if cur_max != 100:
        st.warning(f"Total is {cur_max}/100. Adjust point allocations to reach exactly 100.")

    st.markdown("---")
    col_reset, col_note = st.columns([1, 3])
    with col_reset:
        if st.button("🔄 Reset All to Defaults", use_container_width=True):
            st.session_state.settings = DEFAULT_SETTINGS.copy()
            for k in list(st.session_state.keys()):
                if k.startswith("sset_"):
                    del st.session_state[k]
            st.rerun()
    with col_note:
        st.caption(
            "Resets all sliders to the default 100-point distribution "
            "(A = 30 pts, B = 32 pts, C = 38 pts)."
        )