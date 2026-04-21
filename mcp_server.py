"""
YouTube Keyword Evaluator — MCP Server
========================================
FastMCP server exposing YouTube keyword research as AI-assistant tools.

Compatible with any MCP client: Claude Desktop, Cursor, Continue, etc.

Quick start (stdio mode — default for Claude Desktop):
    uv run python mcp_server.py

HTTP/SSE mode (for web clients):
    uv run python mcp_server.py --transport sse --port 8001

Configure once:
    export YOUTUBE_API_KEY=AIza...   # or put it in .env

Tools exposed:
  • analyze_keyword         — full KOS analysis of one keyword
  • bulk_analyze_keywords   — analyse 1–10 keywords in one call
  • compare_keywords        — rank keywords and pick the best one
  • explain_kos_score       — explain what a KOS score means
  • get_video_insights      — deep-dive on the top competing videos

Prompts exposed:
  • keyword_research        — guided research session prompt template
"""

from __future__ import annotations

import os
import sys
from textwrap import dedent

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

try:
    from fastmcp import FastMCP
except ImportError:
    sys.exit("Missing: pip install fastmcp\nOr:      uv add fastmcp")

from analyzer import (
    DEFAULT_SETTINGS,
    analyse_keyword,
    fmt_number,
    kos_label,
    max_group_a,
    max_group_b,
    max_group_c,
    total_max,
)

# ─────────────────────────────────────────────────────────────────────────────
#  Server setup
# ─────────────────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="YouTube Keyword Evaluator 🎬",
    instructions=dedent("""
        You are a YouTube SEO expert assistant powered by real-time YouTube Data API data.

        You help content creators identify the best keywords to target on YouTube by
        computing a **Keyword Opportunity Score (KOS)** — a 0–100 number where higher
        means easier to rank.

        The KOS is built from three groups:
          • Group A (Videos)     — avg views, like ratio, video age, views/month, comments
          • Group B (Channels)   — avg subscribers, video count, channel age of top competitors
          • Group C (Saturation) — how often the keyword appears in competing titles & descriptions

        Use the tools below to fetch live data. Always cite the KOS and competition level
        when discussing keyword opportunities.
    """).strip(),
)

_ENV_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")


def _get_api_key(youtube_api_key: str) -> str:
    """Resolve the API key: explicit arg > env var."""
    key = (youtube_api_key or "").strip() or _ENV_API_KEY.strip()
    if not key:
        raise ValueError(
            "No YouTube API key available. "
            "Pass youtube_api_key= or set the YOUTUBE_API_KEY environment variable."
        )
    return key


def _run_analysis(api_key: str, keyword: str, settings: dict | None = None) -> dict:
    """Thin wrapper that runs analyse_keyword synchronously."""
    return analyse_keyword(api_key, keyword, settings=settings)


# ─────────────────────────────────────────────────────────────────────────────
#  Tool: analyze_keyword
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def analyze_keyword(
    keyword: str,
    youtube_api_key: str = "",
    full_data: bool = False,
) -> str:
    """
    Analyse a single YouTube keyword and return its Keyword Opportunity Score (KOS).

    The KOS (0–100) indicates how easy it is to rank for this keyword:
      75–100 → Great Opportunity (🟢)
      50–74  → Moderate          (🟡)
      25–49  → Tough             (🟠)
      0–24   → Very Competitive  (🔴)

    Args:
        keyword:         The YouTube search term to analyse (e.g. "lofi study music").
        youtube_api_key: YouTube Data API v3 key. Falls back to YOUTUBE_API_KEY env var.
        full_data:       If True, also return the top 10 competing videos and top 4 channels.

    Returns:
        A Markdown-formatted report.
    """
    key = _get_api_key(youtube_api_key)
    raw = _run_analysis(key, keyword)

    if "error" in raw:
        return f"❌ **Error analysing `{keyword}`**: {raw['error']}"

    lines = [
        f"# 🎬 YouTube Keyword Analysis: `{raw['keyword']}`",
        "",
        f"## KOS: {raw['kos']}/100 — {raw['kos_emoji']} {raw['kos_label']}",
        f"**Competition level:** {raw['competition_level']}",
        "",
        "### 📊 Video Metrics (Group A)",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Avg Views | {raw['avg_views_fmt']} |",
        f"| Avg Views/Month | {raw['avg_vpm_fmt']} |",
        f"| Avg Like Ratio | {raw['avg_like_ratio_pct']} |",
        f"| Avg Comments | {fmt_number(raw['avg_comments'])} |",
        f"| Avg Video Age | {raw['avg_age_months']:.0f} months |",
        f"| KW in Competing Titles | {raw['kw_in_title']} / 10 |",
        f"| KW in Competing Descriptions | {raw['kw_in_desc']} / 10 |",
        "",
        "### 📺 Channel Metrics (Group B, top 4 by subs)",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Avg Subscribers | {raw['avg_subs_fmt']} |",
        f"| Avg Video Count | {fmt_number(raw['avg_ch_vid_count'])} |",
        f"| Avg Channel Age | {raw['avg_ch_age_y']:.1f} years |",
        "",
        "### 🏆 Score Breakdown",
        "| Group | Score | Max | % |",
        "|-------|-------|-----|---|",
        f"| A — Videos | {raw['score_a']} | {raw['max_a']} | {raw['score_a'] / raw['max_a'] * 100:.0f}% |",
        f"| B — Channels | {raw['score_b']} | {raw['max_b']} | {raw['score_b'] / raw['max_b'] * 100:.0f}% |",
        f"| C — Saturation | {raw['score_c']} | {raw['max_c']} | {raw['score_c'] / raw['max_c'] * 100:.0f}% |",
        f"| **TOTAL** | **{raw['kos']}** | **100** | |",
    ]

    if full_data:
        lines += [
            "",
            "### 🎬 Top Competing Videos",
            "| # | Title | Channel | Views | Views/Mo | KW in Title |",
            "|---|-------|---------|-------|----------|-------------|",
        ]
        for v in raw["videos"]:
            title_short = v["title"][:45] + ("…" if len(v["title"]) > 45 else "")
            lines.append(
                f"| {v['rank']} | [{title_short}]({v['url']}) | "
                f"{v['channel'][:22]} | {v['views_fmt']} | "
                f"{v['views_per_month_fmt']} | {v['kw_in_title']} |"
            )

        lines += [
            "",
            "### 📺 Top 4 Channels",
            "| Channel | Subscribers | Videos | Channel Age |",
            "|---------|-------------|--------|-------------|",
        ]
        for c in raw["top4_channels"]:
            lines.append(
                f"| [{c['channel']}]({c['url']}) | {c['subscribers_fmt']} | "
                f"{c['videos_fmt']} | {c['channel_age_years']} yrs |"
            )

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  Tool: bulk_analyze_keywords
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def bulk_analyze_keywords(
    keywords: list[str],
    youtube_api_key: str = "",
    full_data: bool = False,
) -> str:
    """
    Analyse multiple YouTube keywords in one call (up to 10).

    Each keyword is analysed independently. Results are returned as a
    Markdown table sorted alphabetically, followed by individual reports.

    Args:
        keywords:        List of keywords to analyse (max 10).
        youtube_api_key: YouTube Data API v3 key. Falls back to YOUTUBE_API_KEY env var.
        full_data:       If True, include top videos and channels for each keyword.

    Returns:
        A Markdown summary table followed by per-keyword reports.
    """
    if not keywords:
        return "❌ No keywords provided."
    if len(keywords) > 10:
        return (
            "❌ Maximum 10 keywords per bulk call. Please split into smaller batches."
        )

    key = _get_api_key(youtube_api_key)
    keywords = [k.strip() for k in keywords if k.strip()]

    results = [_run_analysis(key, kw) for kw in keywords]

    # ── Summary table ─────────────────────────────────────────────────────────
    lines = [
        "# 📦 Bulk Keyword Analysis",
        "",
        "## Summary",
        "| Keyword | KOS | Label | Competition | Avg Views | KW/Titles |",
        "|---------|-----|-------|-------------|-----------|-----------|",
    ]
    for raw in results:
        if "error" in raw:
            lines.append(f"| `{raw.get('keyword', '?')}` | — | ❌ Error | — | — | — |")
        else:
            lines.append(
                f"| `{raw['keyword']}` | **{raw['kos']}** | "
                f"{raw['kos_emoji']} {raw['kos_label']} | "
                f"{raw['competition_level']} | "
                f"{raw['avg_views_fmt']} | "
                f"{raw['kw_in_title']}/10 |"
            )

    # ── Per-keyword detail ────────────────────────────────────────────────────
    lines.append("\n---\n")
    lines.append("## Individual Reports\n")
    for raw in results:
        if "error" in raw:
            lines.append(f"### ❌ `{raw.get('keyword', '?')}` — {raw['error']}\n")
            continue
        lines.append(
            f"### `{raw['keyword']}` — KOS {raw['kos']}/100 {raw['kos_emoji']}\n"
            f"- Competition: **{raw['competition_level']}** | "
            f"Avg Views: **{raw['avg_views_fmt']}** | "
            f"Views/Month: **{raw['avg_vpm_fmt']}**\n"
            f"- Score: A={raw['score_a']}/{raw['max_a']}  "
            f"B={raw['score_b']}/{raw['max_b']}  "
            f"C={raw['score_c']}/{raw['max_c']}\n"
        )
        if full_data:
            lines.append("**Top videos:**\n")
            for v in raw["videos"][:5]:
                t = v["title"][:50] + ("…" if len(v["title"]) > 50 else "")
                lines.append(f"- [{t}]({v['url']}) — {v['views_fmt']} views")
            lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  Tool: compare_keywords
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def compare_keywords(
    keywords: list[str],
    youtube_api_key: str = "",
) -> str:
    """
    Compare multiple YouTube keywords and recommend the best one to target.

    Keywords are ranked by KOS (highest = easiest to rank). The tool explains
    WHY the top keyword is recommended based on the score breakdown.

    Use this when a creator has several keyword ideas and wants a data-driven
    recommendation on which one to go with.

    Args:
        keywords:        2–10 keywords to compare.
        youtube_api_key: YouTube Data API v3 key. Falls back to YOUTUBE_API_KEY env var.

    Returns:
        Ranked comparison table + recommendation with reasoning.
    """
    if len(keywords) < 2:
        return "❌ Provide at least 2 keywords to compare."
    if len(keywords) > 10:
        return "❌ Maximum 10 keywords per comparison."

    key = _get_api_key(youtube_api_key)
    keywords = [k.strip() for k in keywords if k.strip()]

    results = [_run_analysis(key, kw) for kw in keywords]
    successes = [r for r in results if "error" not in r]
    errors = [r for r in results if "error" in r]

    if not successes:
        return "❌ All keywords failed to analyse. Check your API key and try again."

    successes.sort(key=lambda r: r["kos"], reverse=True)
    best = successes[0]
    worst = successes[-1]

    # ── Ranked table ──────────────────────────────────────────────────────────
    lines = [
        "# 🏆 Keyword Comparison",
        "",
        "## Ranked by KOS (highest = easiest to rank)",
        "",
        "| Rank | Keyword | KOS | Label | Competition | Avg Views | Score A | Score B | Score C |",
        "|------|---------|-----|-------|-------------|-----------|---------|---------|---------|",
    ]
    for i, r in enumerate(successes, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"#{i}")
        lines.append(
            f"| {medal} | `{r['keyword']}` | **{r['kos']}** | "
            f"{r['kos_emoji']} {r['kos_label']} | "
            f"{r['competition_level']} | "
            f"{r['avg_views_fmt']} | "
            f"{r['score_a']}/{r['max_a']} | "
            f"{r['score_b']}/{r['max_b']} | "
            f"{r['score_c']}/{r['max_c']} |"
        )

    for r in errors:
        lines.append(
            f"| ❌ | `{r.get('keyword', '?')}` | — | Error | — | — | — | — | — |"
        )

    # ── Recommendation ────────────────────────────────────────────────────────
    kos_diff = best["kos"] - (successes[1]["kos"] if len(successes) > 1 else 0)
    lines += [
        "",
        "---",
        "",
        f"## ✅ Recommendation: `{best['keyword']}`",
        "",
        f"**KOS {best['kos']}/100** — {best['kos_emoji']} {best['kos_label']}",
        "",
        "### Why this keyword?",
    ]

    reasons = []

    # Competition level
    if best["competition_level"] in ("Low", "Medium"):
        reasons.append(
            f"- **{best['competition_level']} competition** — fewer dominant channels to compete with."
        )

    # Avg views (demand signal)
    if best["avg_views"] >= 50_000:
        reasons.append(
            f"- **Strong demand signal** — top videos average {best['avg_views_fmt']} views."
        )
    elif best["avg_views"] < 50_000:
        reasons.append(
            f"- **Niche demand** — avg {best['avg_views_fmt']} views; easier to break in early."
        )

    # KW saturation
    if best["kw_in_title"] <= 3:
        reasons.append(
            f"- **Low keyword saturation** — only {best['kw_in_title']}/10 competing titles "
            f"contain this keyword, so a well-optimised title stands out."
        )

    # Channel authority
    if best["score_b"] >= best["max_b"] * 0.5:
        reasons.append(
            f"- **Achievable channel bar** — top channels average {best['avg_subs_fmt']} "
            f"subscribers; within reach for a growing channel."
        )

    # Score lead
    if len(successes) > 1 and kos_diff >= 5:
        reasons.append(
            f"- **Clear leader** — {kos_diff} KOS points ahead of the next best option "
            f"(`{successes[1]['keyword']}` at {successes[1]['kos']})."
        )

    if not reasons:
        reasons.append(
            f"- Highest overall KOS ({best['kos']}) among compared keywords."
        )

    lines += reasons

    if len(successes) > 1:
        lines += [
            "",
            f"### ⚠️ Least recommended: `{worst['keyword']}`",
            f"KOS {worst['kos']}/100 ({worst['kos_emoji']} {worst['kos_label']}) — "
            f"{worst['competition_level']} competition.",
        ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  Tool: explain_kos_score
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def explain_kos_score(score: int) -> str:
    """
    Explain what a given KOS (Keyword Opportunity Score) means and suggest next steps.

    Use this after getting a KOS from analyze_keyword or compare_keywords to help
    a creator understand the score in plain language.

    Args:
        score: The KOS value (0–100).

    Returns:
        Plain-language interpretation and actionable advice.
    """
    score = max(0, min(100, score))
    label, emoji, _ = kos_label(score)

    advice_map = {
        "Great Opportunity": dedent("""
            **Action plan:**
            1. Create high-quality content targeting this keyword immediately — the window of
               opportunity may not stay open forever.
            2. Include the keyword naturally in your title (ideally in the first 40 characters),
               description (first 2–3 sentences), and 2–3 tags.
            3. Focus on thumbnail CTR and audience retention to fast-track ranking.
            4. Monitor the keyword monthly — if competition grows, double down before it peaks.
        """),
        "Moderate": dedent("""
            **Action plan:**
            1. Target this keyword but invest in production quality — mediocre videos won't rank.
            2. Study the top 3 videos in detail: what makes them successful? Match or exceed their
               quality, structure, and thumbnail design.
            3. Build a small cluster of 3–5 related videos to signal authority on the topic.
            4. Consider combining this keyword with a longer-tail variant to capture easier sub-niches.
        """),
        "Tough": dedent("""
            **Action plan:**
            1. Only go after this keyword if you already have a solid audience (10K+ subs) or
               a proven track record in this niche.
            2. Target longer-tail variants first to build authority before competing on the
               head keyword.
            3. Look for a unique angle (format, perspective, audience) that the top videos miss.
            4. Use this as a long-term goal, not a quick win.
        """),
        "Very Competitive": dedent("""
            **Action plan:**
            1. **Avoid as a new/small channel** — the top positions are locked by dominant channels.
            2. Use this keyword as a secondary/supporting keyword (in description, tags) rather
               than the primary title keyword.
            3. Research adjacent long-tail keywords with scores above 50 instead.
            4. If you must target it, plan a series of 10+ videos building topical authority first.
        """),
    }

    tier_context = {
        "Great Opportunity": (
            "The competitive landscape is relatively accessible. Top videos don't dominate "
            "with massive view counts, the channels aren't mega-channels, and the keyword "
            "isn't heavily over-used in competing titles or descriptions."
        ),
        "Moderate": (
            "There's real demand but also real competition. You can rank, but it will take "
            "deliberate effort, quality content, and possibly some promotion."
        ),
        "Tough": (
            "Established channels with strong subscriber bases and high view counts dominate "
            "this space. Breaking in requires exceptional content or a differentiated angle."
        ),
        "Very Competitive": (
            "This is a saturated keyword dominated by large channels. The algorithm strongly "
            "favours existing high-performers, making it very hard for new entries to rank."
        ),
    }

    lines = [
        f"# KOS {score}/100 — {emoji} {label}",
        "",
        "## What this means",
        tier_context[label],
        "",
        "## Score tiers for reference",
        "| Range | Label | What it means |",
        "|-------|-------|----------------|",
        "| 75–100 | 🟢 Great Opportunity | Low-to-medium competition, real demand — go for it |",
        "| 50–74  | 🟡 Moderate | Achievable with quality content and SEO |",
        "| 25–49  | 🟠 Tough | Established competition — need differentiation |",
        "| 0–24   | 🔴 Very Competitive | Dominated by major channels — high difficulty |",
        "",
        advice_map[label].strip(),
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  Tool: get_video_insights
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def get_video_insights(
    keyword: str,
    youtube_api_key: str = "",
) -> str:
    """
    Deep-dive on the top competing videos for a keyword.

    Returns a detailed breakdown of each top video: title patterns, keyword
    usage, engagement metrics, channel size, and publication recency.

    Use this to help a creator understand what the best-performing videos look
    like so they can model their own content strategy.

    Args:
        keyword:         The YouTube keyword to research.
        youtube_api_key: YouTube Data API v3 key. Falls back to YOUTUBE_API_KEY env var.

    Returns:
        Markdown report with video-level insights and pattern observations.
    """
    key = _get_api_key(youtube_api_key)
    raw = _run_analysis(key, keyword)

    if "error" in raw:
        return f"❌ **Error**: {raw['error']}"

    videos = raw["videos"]

    lines = [
        f"# 🎬 Video Insights: `{keyword}`",
        f"*KOS: {raw['kos']}/100 — {raw['kos_emoji']} {raw['kos_label']}*",
        "",
        "## Top Competing Videos",
        "",
        "| # | Title | Views | Views/Mo | Age | KW in Title | KW Pos | KW in Desc |",
        "|---|-------|-------|----------|-----|-------------|--------|------------|",
    ]

    for v in videos:
        t = v["title"][:48] + ("…" if len(v["title"]) > 48 else "")
        lines.append(
            f"| {v['rank']} | [{t}]({v['url']}) | {v['views_fmt']} | "
            f"{v['views_per_month_fmt']} | {v['age_months']}mo | "
            f"{v['kw_in_title']} | {v['kw_pos_in_title']} | {v['kw_in_desc']} |"
        )

    # Pattern observations
    kw_in_titles_count = sum(1 for v in videos if v["kw_in_title"] > 0)
    avg_age = raw["avg_age_months"]
    max_views_video = max(videos, key=lambda v: v["views"])
    positions = [v["kw_pos_in_title"] for v in videos if v["kw_pos_in_title"] != "—"]
    pos_counts = {p: positions.count(p) for p in set(positions)}

    lines += [
        "",
        "## 🔍 Pattern Observations",
        "",
        f"- **Keyword in titles**: {kw_in_titles_count}/10 videos use the keyword in their title "
        f"({'high saturation' if kw_in_titles_count >= 7 else 'moderate saturation' if kw_in_titles_count >= 4 else 'low saturation — opportunity!'}).",
    ]

    if pos_counts:
        dominant_pos = max(pos_counts, key=lambda k: pos_counts[k])
        lines.append(
            f"- **Keyword position**: Most competitors place the keyword at the "
            f"**{dominant_pos}** of their title ({pos_counts[dominant_pos]}/{len(positions)} videos)."
        )

    lines.append(
        f"- **Content freshness**: Average video age is **{avg_age:.0f} months** "
        f"({'recent content dominates' if avg_age < 12 else 'older content dominates — update angle opportunity' if avg_age > 24 else 'mixed age range'})."
    )
    lines.append(
        f"- **Top performer**: [{max_views_video['title'][:60]}]({max_views_video['url']}) "
        f"with **{max_views_video['views_fmt']} views** ({max_views_video['views_per_month_fmt']} views/month)."
    )

    kw_desc_count = sum(1 for v in videos if v["kw_in_desc"] > 0)
    lines.append(
        f"- **Keyword in descriptions**: {kw_desc_count}/10 competing videos mention "
        f"the keyword in their description "
        f"({'saturated' if kw_desc_count >= 8 else 'moderate' if kw_desc_count >= 5 else 'low — use it!'})."
    )

    lines += [
        "",
        "## 💡 Content Strategy Tips",
        "",
    ]

    if kw_in_titles_count < 4:
        lines.append(
            "- ✅ **Include the keyword in your title** — most competitors don't, so "
            "a keyword-optimised title gives you an immediate SEO edge."
        )
    elif dominant_pos == "Start" if pos_counts else False:
        lines.append(
            "- 💡 Try placing the keyword in the **middle or end** of your title — "
            "most competitors front-load it, so a different pattern may stand out."
        )

    if avg_age > 18:
        lines.append(
            "- ✅ **Recency advantage** — most top videos are older. A fresh, updated "
            "take on this topic could rank well and capture demand for new content."
        )

    if raw["avg_like_ratio"] < 0.02:
        lines.append(
            "- 💡 **Engagement is low** — focus on watch time and encouraging comments/likes "
            "in your video. Better engagement signals = faster ranking."
        )

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
#  Prompt: keyword_research
# ─────────────────────────────────────────────────────────────────────────────


@mcp.prompt()
def keyword_research(
    topic: str,
    channel_size: str = "small (under 10K subscribers)",
    content_goal: str = "grow audience",
) -> str:
    """
    Generate a guided YouTube keyword research session prompt.

    Use this to start a structured keyword research session where the AI will
    help identify the best keywords for a given topic and channel.

    Args:
        topic:          The broad topic or niche (e.g. "home coffee brewing").
        channel_size:   Current channel size for context (e.g. "small", "medium 10K-100K").
        content_goal:   What the creator wants to achieve (e.g. "grow audience", "monetise").
    """
    return dedent(f"""
        You are a YouTube SEO strategist. Your task is to help identify the best keywords
        for a YouTube channel with the following context:

        - **Topic/Niche**: {topic}
        - **Channel size**: {channel_size}
        - **Content goal**: {content_goal}

        ## Session plan

        1. **Brainstorm** 5–8 keyword variations for the topic (mix of head terms and long-tail).
        2. **Analyse** each keyword using the `analyze_keyword` tool to get KOS scores.
        3. **Compare** all keywords using the `compare_keywords` tool to rank them.
        4. **Deep-dive** on the top 2 keywords using the `get_video_insights` tool.
        5. **Recommend** a final keyword strategy with:
           - Primary keyword (highest KOS)
           - 2–3 supporting long-tail keywords
           - Title formula based on competing title patterns
           - Description optimisation tips

        Start by suggesting 5–8 keyword variations, then begin analysing them.
        Always explain your reasoning at each step.
    """).strip()


# ─────────────────────────────────────────────────────────────────────────────
#  Resource: KOS scale reference
# ─────────────────────────────────────────────────────────────────────────────


@mcp.resource("yt-kos://scale")
def kos_scale() -> str:
    """The KOS scoring scale, group descriptions, and active scoring thresholds."""
    S = DEFAULT_SETTINGS
    return dedent(f"""
        # Keyword Opportunity Score (KOS) Scale

        ## Score Tiers
        | Range  | Tier              | Meaning                                              |
        |--------|-------------------|------------------------------------------------------|
        | 75–100 | 🟢 Great Opportunity | Low-to-medium competition, real demand — act now  |
        | 50–74  | 🟡 Moderate          | Achievable with quality content and SEO effort    |
        | 25–49  | 🟠 Tough             | Established competition — differentiation needed  |
        | 0–24   | 🔴 Very Competitive  | Dominated by major channels — very hard to break in |

        ## Score Groups (max {total_max(S)} pts)

        ### Group A — Video Metrics (max {max_group_a(S)} pts)
        Bell-curve scoring: sweet spot = full pts; too low (unproven) OR too high (dominated) = fewer pts.
        - Avg Views ({S["a_avg_views_pts"]} pts)       — sweet spot: {fmt_number(S["a_avg_views_lo"])}–{fmt_number(S["a_avg_views_hi1"])} views
        - Avg Video Age ({S["a_video_age_pts"]} pts)   — sweet spot: {S["a_video_age_hi1_mo"]}–{S["a_video_age_lo_mo"]} months (fresh but proven)
        - Views per Month ({S["a_vpm_pts"]} pts) — sweet spot: {fmt_number(S["a_vpm_lo"])}–{fmt_number(S["a_vpm_hi1"])} views/mo
        - Like Ratio ({S["a_like_ratio_pts"]} pts)      — sweet spot: {S["a_like_ratio_lo"]}%–{S["a_like_ratio_hi1"]}%
        - Avg Comments ({S["a_comments_pts"]} pts)    — sweet spot: {S["a_comments_lo"]}–{fmt_number(S["a_comments_hi1"])}

        ### Group B — Channel Metrics (max {max_group_b(S)} pts)
        Lower channel authority = more opportunity.
        - Avg Subscribers ({S["b_subs_pts"]} pts) — < {fmt_number(S["b_subs_t3"])} subs = full pts; ≥ {fmt_number(S["b_subs_t1"])} = 0 pts
        - Avg Video Count ({S["b_vid_count_pts"]} pts) — < {S["b_vid_count_t2"]} videos = full pts; > {S["b_vid_count_t1"]} = 0 pts
        - Avg Channel Age ({S["b_ch_age_pts"]} pts) — < {S["b_ch_age_t2"]} years = full pts; > {S["b_ch_age_t1"]} years = 0 pts

        ### Group C — Saturation (max {max_group_c(S)} pts)
        Less keyword usage in competing content = more opportunity.
        - KW in Titles ({S["c_title_pts"]} pts)     — 0 occurrences = full pts
        - KW Title Position ({S["c_title_pos_pts"]} pts) — keyword at end of title = more pts (less competitive position)
        - KW in Descriptions ({S["c_desc_pts"]} pts) — 0 occurrences = full pts
    """).strip()


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="YouTube Keyword Evaluator MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport protocol (default: stdio for Claude Desktop)",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MCP_HOST", "0.0.0.0"),
        help="Host for SSE/HTTP transports",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "8001")),
        help="Port for SSE/HTTP transports",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)
