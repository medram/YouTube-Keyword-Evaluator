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
#  KOS Scoring  (max = 40 + 35 + 27 = 102, capped at 100)
# ──────────────────────────────────────────────────────────────

def score_group_a(avg_views, avg_like_ratio, avg_age_months, avg_comments):
    pts = {}

    if   avg_views >= 1_000_000: pts["Avg Views"]          = 0
    elif avg_views >= 100_000:   pts["Avg Views"]          = 5
    elif avg_views >= 10_000:    pts["Avg Views"]          = 10
    else:                        pts["Avg Views"]          = 15

    ratio_pct = avg_like_ratio * 100
    if   ratio_pct > 5:  pts["Likes / Views Ratio"] = 0
    elif ratio_pct >= 2: pts["Likes / Views Ratio"] = 5
    else:                pts["Likes / Views Ratio"] = 10

    if   avg_age_months < 6:   pts["Avg Video Age"]  = 10
    elif avg_age_months <= 24: pts["Avg Video Age"]  = 5
    else:                      pts["Avg Video Age"]  = 0

    if   avg_comments > 5_000: pts["Avg Comments"]   = 0
    elif avg_comments >= 500:  pts["Avg Comments"]   = 3
    else:                      pts["Avg Comments"]   = 5

    return pts  # max 40


def score_group_b(avg_subs, avg_vid_count, avg_ch_age_years):
    pts = {}

    if   avg_subs >= 1_000_000: pts["Avg Subscribers"]  = 0
    elif avg_subs >= 100_000:   pts["Avg Subscribers"]  = 5
    elif avg_subs >= 10_000:    pts["Avg Subscribers"]  = 10
    else:                       pts["Avg Subscribers"]  = 15

    if   avg_vid_count > 500:  pts["Avg Video Count"]   = 0
    elif avg_vid_count >= 100: pts["Avg Video Count"]   = 5
    else:                      pts["Avg Video Count"]   = 10

    if   avg_ch_age_years > 5: pts["Avg Channel Age"]   = 0
    elif avg_ch_age_years >= 2: pts["Avg Channel Age"]  = 5
    else:                       pts["Avg Channel Age"]  = 10

    return pts  # max 35


def score_group_c(kw_in_title, kw_in_desc):
    pts = {}

    if   kw_in_title <= 3: pts["KW in Titles"]       = 10
    elif kw_in_title <= 7: pts["KW in Titles"]       = 5
    else:                  pts["KW in Titles"]       = 2

    if   kw_in_desc <= 3:  pts["KW in Descriptions"] = 10
    elif kw_in_desc <= 7:  pts["KW in Descriptions"] = 5
    else:                  pts["KW in Descriptions"] = 2

    saturation = min((kw_in_title + kw_in_desc) / 20.0, 1.0)
    pts["Saturation Index"] = round((1 - saturation) * 7, 1)

    return pts  # max ~27


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

def analyse_keyword(yt, keyword: str) -> dict:
    search_items = search_videos(yt, keyword, 10)
    if not search_items:
        return {"error": "No results found.", "keyword": keyword}

    # Filter items and safely extract IDs
    video_ids = []
    ch_ids_raw = []
    
    for item in search_items:
        # Check if item has expected video structure
        if (item.get("id") and 
            isinstance(item["id"], dict) and 
            "videoId" in item["id"] and 
            item.get("snippet") and 
            "channelId" in item["snippet"]):
            video_ids.append(item["id"]["videoId"])
            ch_ids_raw.append(item["snippet"]["channelId"])
    
    if not video_ids:
        return {"error": "No valid video results found.", "keyword": keyword}

    vid_map   = get_video_details(yt, video_ids)
    unique_ch = list(dict.fromkeys(ch_ids_raw))
    chan_map   = get_channel_details(yt, unique_ch)

    # ── Build video list ─────────────────────
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
        dc = count_kw(desc[:200], keyword)    # only scan first 200 chars of description
        kw_in_title   += tc
        kw_in_desc    += dc
        total_views   += views
        total_likes   += likes
        total_comments += comments

        like_ratio = likes / views if views > 0 else 0

        videos.append({
            "Rank":          rank,
            "Title":         title,
            "Channel":       ch_name,
            "Published":     published[:10] if published else "—",
            "Age (months)":  round(age_mo, 1),
            "Views":         views,
            "Views (fmt)":   fmt_number(views),
            "Likes":         likes,
            "Likes (fmt)":   fmt_number(likes),
            "Like Ratio":    f"{like_ratio*100:.2f}%",
            "Comments":      comments,
            "KW in Title":   tc,
            "KW in Desc":    dc,
            "URL":           f"https://youtu.be/{vid_id}",
            "channel_id":    ch_id,
        })

    n = len(videos)
    avg_views      = total_views    / n if n else 0
    avg_comments   = total_comments / n if n else 0
    avg_like_ratio = total_likes / total_views if total_views > 0 else 0
    avg_age_months = sum(age_months_list) / len(age_months_list) if age_months_list else 24

    # ── Build channel list ───────────────────
    channels = []
    for cid, c in chan_map.items():
        subs    = int(c["statistics"].get("subscriberCount", 0))
        vids    = int(c["statistics"].get("videoCount",      0))
        ttl_v   = int(c["statistics"].get("viewCount",       0))
        pub     = c["snippet"].get("publishedAt", "")
        ch_age  = years_since(parse_dt(pub)) if pub else 3.0

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

    avg_subs      = sum(c["_subs"]       for c in top4) / len(top4) if top4 else 0
    avg_vid_count = sum(c["_vid_count"]  for c in top4) / len(top4) if top4 else 0
    avg_ch_age_y  = sum(c["_age_years"]  for c in top4) / len(top4) if top4 else 3.0

    # ── KOS ──────────────────────────────────
    pts_a   = score_group_a(avg_views, avg_like_ratio, avg_age_months, avg_comments)
    pts_b   = score_group_b(avg_subs, avg_vid_count, avg_ch_age_y)
    pts_c   = score_group_c(kw_in_title, kw_in_desc)
    score_a = sum(pts_a.values())
    score_b = sum(pts_b.values())
    score_c = sum(pts_c.values())
    kos     = min(100, round(score_a + score_b + score_c))

    label, emoji, color = kos_label(kos)

    return {
        "keyword":           keyword,
        "videos":            videos,
        "top4_channels":     top4,
        "total_views":       int(total_views),
        "avg_views":         int(avg_views),
        "avg_comments":      int(avg_comments),
        "avg_like_ratio":    avg_like_ratio,
        "avg_age_months":    avg_age_months,
        "kw_in_title":       kw_in_title,
        "kw_in_desc":        kw_in_desc,
        "kos":               kos,
        "kos_label":         label,
        "kos_emoji":         emoji,
        "kos_color":         color,
        "score_a":           score_a,
        "score_b":           score_b,
        "score_c":           round(score_c, 1),
        "pts_a":             pts_a,
        "pts_b":             pts_b,
        "pts_c":             pts_c,
        "avg_subs":          int(avg_subs),
        "avg_ch_vid_count":  int(avg_vid_count),
        "avg_ch_age_y":      round(avg_ch_age_y, 1),
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
            group_bar_html(res["score_a"], 40, "#4fc3f7", "Group A — Videos",   res["pts_a"]),
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown(
            group_bar_html(res["score_b"], 35, "#ce93d8", "Group B — Channels", res["pts_b"]),
            unsafe_allow_html=True,
        )
    with col_c:
        st.markdown(
            group_bar_html(round(res["score_c"], 1), 27, "#ffb74d",
                           "Group C — Saturation", res["pts_c"]),
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Row 2 — supporting metric strip
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    for col, label, val in [
        (m1, "👁️ Avg Views",      fmt_number(res["avg_views"])),
        (m2, "👍 Avg Like Ratio", f"{res['avg_like_ratio']*100:.2f}%"),
        (m3, "💬 Avg Comments",   fmt_number(res["avg_comments"])),
        (m4, "📅 Avg Video Age",  f"{res['avg_age_months']:.0f} mo"),
        (m5, "🔤 KW in Titles",   str(res["kw_in_title"])),
        (m6, "📝 KW in Descs",    str(res["kw_in_desc"])),
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
        "Comments", "KW in Title", "KW in Desc", "URL",
    ]].rename(columns={"Views (fmt)": "Views", "Likes (fmt)": "Likes"}).set_index("Rank")
    st.dataframe(vid_df, use_container_width=True,
                 column_config={"URL": st.column_config.LinkColumn("Video URL")})

    st.markdown("<br>", unsafe_allow_html=True)

    # Keyword frequency bar chart
    st.markdown('<div class="section-header">🔤 Keyword Frequency per Video</div>',
                unsafe_allow_html=True)
    freq_df = pd.DataFrame({
        "Video": [f"#{v['Rank']} {v['Title'][:38]}…" for v in res["videos"]],
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
        # Summary sheet
        summary_rows = []
        for r in results:
            if "error" in r:
                summary_rows.append({"Keyword": r.get("keyword",""), "KOS": "ERROR",
                    "Label":"","Score A /40":"","Score B /35":"","Score C /27":"",
                    "Avg Views":"","KW Titles":"","KW Descs":""})
            else:
                summary_rows.append({
                    "Keyword":       r["keyword"],
                    "KOS":           r["kos"],
                    "Label":         r["kos_label"],
                    "Score A /40":   r["score_a"],
                    "Score B /35":   r["score_b"],
                    "Score C /27":   r["score_c"],
                    "Avg Views":     r["avg_views"],
                    "Total Views":   r["total_views"],
                    "Avg Like Ratio":f"{r['avg_like_ratio']*100:.2f}%",
                    "Avg Comments":  r["avg_comments"],
                    "Avg Video Age (mo)": round(r["avg_age_months"], 1),
                    "KW in Titles":  r["kw_in_title"],
                    "KW in Descs":   r["kw_in_desc"],
                    "Avg Subs (top4)": r["avg_subs"],
                    "Avg Ch Age (yr)": r["avg_ch_age_y"],
                })
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary", index=False)

        for r in results:
            if "error" in r:
                continue
            safe = r["keyword"][:25].replace("/","_").replace("\\","_").replace("*","_")

            # Videos sheet
            pd.DataFrame(r["videos"])[[
                "Rank","Title","Channel","Published","Views","Likes",
                "Like Ratio","Comments","KW in Title","KW in Desc","URL"
            ]].to_excel(writer, sheet_name=f"{safe}_videos", index=False)

            # Channels sheet
            pd.DataFrame(r["top4_channels"])[[
                "Channel","Subscribers","Videos","Total Views","Channel Age (yr)","URL"
            ]].to_excel(writer, sheet_name=f"{safe}_channels", index=False)

            # Score breakdown sheet
            MAX_A = {"Avg Views": 15, "Likes / Views Ratio": 10,
                     "Avg Video Age": 10, "Avg Comments": 5}
            MAX_B = {"Avg Subscribers": 15, "Avg Video Count": 10, "Avg Channel Age": 10}
            MAX_C = {"KW in Titles": 10, "KW in Descriptions": 10, "Saturation Index": 7}
            bd_rows = (
                [{"Group":"A — Videos",    "Metric":m,"Points":p,"Max":MAX_A.get(m,"—")} for m,p in r["pts_a"].items()] +
                [{"Group":"B — Channels",  "Metric":m,"Points":p,"Max":MAX_B.get(m,"—")} for m,p in r["pts_b"].items()] +
                [{"Group":"C — Saturation","Metric":m,"Points":p,"Max":MAX_C.get(m,"—")} for m,p in r["pts_c"].items()] +
                [{"Group":"TOTAL","Metric":"KOS","Points":r["kos"],"Max":100}]
            )
            pd.DataFrame(bd_rows).to_excel(writer, sheet_name=f"{safe}_score", index=False)

    return buf.getvalue()


# ──────────────────────────────────────────────────────────────
#  SIDEBAR
# ──────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️ Settings")
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

**Groups:**
- **A (max 40)** — Avg views, like ratio, video age, comments
- **B (max 35)** — Channel subs, video count, channel age
- **C (max 27)** — KW in titles/descs, saturation index
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

tab_single, tab_bulk = st.tabs(["🔍 Single Keyword", "📂 Bulk / CSV Upload"])


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
                res = analyse_keyword(yt, keyword.strip())
                if "error" in res:
                    st.error(res["error"])
                else:
                    render_result(res)
                    xlsx = results_to_excel([res])
                    st.download_button(
                        "⬇️ Download Results (Excel)",
                        data=xlsx,
                        file_name=f"yt_{keyword.strip().replace(' ','_')}.xlsx",
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
                    res = analyse_keyword(yt, kw)
                    if "error" in res:
                        status_rows.append({
                            "Keyword": kw, "Status": "❌ No results",
                            "KOS":"—","Label":"—","A":"—","B":"—","C":"—","Avg Views":"—",
                        })
                    else:
                        results_store.append(res)
                        status_rows.append({
                            "Keyword":  kw,
                            "Status":   "✅ Done",
                            "KOS":      res["kos"],
                            "Label":    f"{res['kos_emoji']} {res['kos_label']}",
                            "A /40":    res["score_a"],
                            "B /35":    res["score_b"],
                            "C /27":    res["score_c"],
                            "Avg Views":fmt_number(res["avg_views"]),
                        })
                except HttpError:
                    status_rows.append({
                        "Keyword": kw, "Status": "❌ API Error",
                        "KOS":"—","Label":"—","A":"—","B":"—","C":"—","Avg Views":"—",
                    })

                status_table.dataframe(pd.DataFrame(status_rows), use_container_width=True)
                if i < len(keywords_list) - 1:
                    time.sleep(0.3)

            progress_bar.progress(1.0, text="✅ All done!")

            if results_store:
                st.markdown("---")
                st.markdown("### 📊 Bulk Summary — sorted by KOS ↓")
                summary_df = pd.DataFrame([{
                    "Keyword":    r["keyword"],
                    "KOS":        r["kos"],
                    "Label":      f"{r['kos_emoji']} {r['kos_label']}",
                    "A /40":      r["score_a"],
                    "B /35":      r["score_b"],
                    "C /27":      r["score_c"],
                    "Avg Views":  fmt_number(r["avg_views"]),
                    "KW Titles":  r["kw_in_title"],
                    "KW Descs":   r["kw_in_desc"],
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