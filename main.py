"""
YouTube Keyword Evaluator
=========================
Analyzes a keyword on YouTube and returns:
  - Top 10 videos + view counts
  - Top 4 channels + subscriber counts
  - Keyword frequency in titles & descriptions
  - Competition overview (avg views, total results, engagement signals)

Requirements:
    pip install google-api-python-client tabulate colorama

Usage:
    python youtube_keyword_eval.py --keyword "coffee and jazz" --api-key YOUR_API_KEY

Get a free API key at: https://console.cloud.google.com/
  → Enable "YouTube Data API v3"
"""

import argparse
import re
import sys
from collections import defaultdict

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    sys.exit("❌  Missing dependency: run  pip install google-api-python-client")

try:
    from tabulate import tabulate
except ImportError:
    sys.exit("❌  Missing dependency: run  pip install tabulate")

try:
    from colorama import Fore, Style, init

    init(autoreset=True)
except ImportError:
    # Graceful fallback – no colors
    class _Noop:
        def __getattr__(self, _):
            return ""

    Fore = Style = _Noop()  # type: ignore[assignment]


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────


def fmt_number(n: int) -> str:
    """Format large numbers with K / M suffix."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def count_keyword_occurrences(text: str, keyword: str) -> int:
    """Case-insensitive count of non-overlapping keyword occurrences."""
    return len(re.findall(re.escape(keyword), text, re.IGNORECASE))


def competition_label(avg_views: int) -> str:
    """Simple heuristic competition label based on average views of top 10."""
    if avg_views >= 1_000_000:
        return f"{Fore.RED}🔴 Very High"
    if avg_views >= 200_000:
        return f"{Fore.YELLOW}🟠 High"
    if avg_views >= 50_000:
        return f"{Fore.CYAN}🟡 Medium"
    return f"{Fore.GREEN}🟢 Low"


# ──────────────────────────────────────────────
#  Core API calls
# ──────────────────────────────────────────────


def search_videos(youtube, keyword: str, max_results: int = 10):
    """Return a list of video IDs and basic search metadata."""
    request = youtube.search().list(
        part="snippet",
        q=keyword,
        type="video",
        order="relevance",
        maxResults=max_results,
        relevanceLanguage="en",
    )
    response = request.execute()
    return response.get("items", [])


def get_video_details(youtube, video_ids: list[str]):
    """Fetch full statistics + snippet for a batch of video IDs."""
    request = youtube.videos().list(
        part="snippet,statistics",
        id=",".join(video_ids),
    )
    return request.execute().get("items", [])


def get_channel_details(youtube, channel_ids: list[str]):
    """Fetch subscriber counts for a list of channel IDs."""
    request = youtube.channels().list(
        part="snippet,statistics",
        id=",".join(channel_ids),
    )
    return request.execute().get("items", [])


# ──────────────────────────────────────────────
#  Analysis
# ──────────────────────────────────────────────


def analyse_keyword(api_key: str, keyword: str):
    youtube = build("youtube", "v3", developerKey=api_key)

    print(f"\n{Fore.CYAN}{'─' * 60}")
    print("  🔍  YouTube Keyword Evaluator")
    print(f"  Keyword : {Style.BRIGHT}{keyword}")
    print(f"{Fore.CYAN}{'─' * 60}\n")

    # ── 1. Search ──────────────────────────────
    print("⏳  Fetching top 10 videos …")
    search_items = search_videos(youtube, keyword, max_results=10)
    if not search_items:
        print("No results found for that keyword.")
        return

    video_ids = [item["id"]["videoId"] for item in search_items]
    channel_ids = [item["snippet"]["channelId"] for item in search_items]

    # ── 2. Video details ───────────────────────
    print("⏳  Fetching video statistics …")
    video_details = get_video_details(youtube, video_ids)

    # Map id → details for easy lookup
    vid_map = {v["id"]: v for v in video_details}

    # ── 3. Channel details (unique) ────────────
    unique_channel_ids = list(dict.fromkeys(channel_ids))  # preserve order, dedupe
    print("⏳  Fetching channel statistics …")
    channel_details = get_channel_details(youtube, unique_channel_ids)

    # ── 4. Build video rows + keyword counts ───
    video_rows = []
    total_views = 0
    kw_in_title = 0
    kw_in_desc = 0

    channel_view_acc: defaultdict[str, int] = defaultdict(
        int
    )  # accumulate views per channel

    for rank, vid_id in enumerate(video_ids, start=1):
        v = vid_map.get(vid_id)
        if not v:
            continue

        title = v["snippet"].get("title", "")
        description = v["snippet"].get("description", "")
        channel_id = v["snippet"].get("channelId", "")
        channel_nm = v["snippet"].get("channelTitle", "")
        views = int(v["statistics"].get("viewCount", 0))
        likes = int(v["statistics"].get("likeCount", 0))
        comments = int(v["statistics"].get("commentCount", 0))

        t_count = count_keyword_occurrences(title, keyword)
        d_count = count_keyword_occurrences(description, keyword)
        kw_in_title += t_count
        kw_in_desc += d_count
        total_views += views

        channel_view_acc[channel_id] += views

        url = f"https://youtu.be/{vid_id}"
        video_rows.append(
            [
                rank,
                (title[:55] + "…") if len(title) > 55 else title,
                channel_nm[:25],
                fmt_number(views),
                fmt_number(likes),
                fmt_number(comments),
                t_count,
                d_count,
                url,
            ]
        )

    # ── 5. Top 4 channels by subscriber count ──
    # Rank all unique channels by their sub count, pick top 4
    channel_rows = []
    for chan in channel_details:
        cid = chan["id"]
        name = chan["snippet"].get("title", "")
        subs = int(chan["statistics"].get("subscriberCount", 0))
        vids = int(chan["statistics"].get("videoCount", 0))
        ttl_v = int(chan["statistics"].get("viewCount", 0))
        url = f"https://www.youtube.com/channel/{cid}"
        channel_rows.append(
            (subs, name, fmt_number(subs), fmt_number(vids), fmt_number(ttl_v), url)
        )

    channel_rows.sort(key=lambda x: x[0], reverse=True)
    top4 = channel_rows[:4]

    # ── 6. Competition metrics ──────────────────
    n_videos = len(video_rows)
    avg_views = total_views // n_videos if n_videos else 0
    comp_label = competition_label(avg_views)

    # ══════════════════════════════════════════
    #  PRINT RESULTS
    # ══════════════════════════════════════════

    # — Competition Overview ———————————————————
    print(f"\n{Style.BRIGHT}{Fore.YELLOW}{'━' * 60}")
    print("  📊  COMPETITION OVERVIEW")
    print(f"{'━' * 60}{Style.RESET_ALL}")
    overview = [
        ["Keyword", keyword],
        ["Competition Level", comp_label],
        ["Avg Views (Top 10)", fmt_number(avg_views)],
        ["Total Views (Top 10)", fmt_number(total_views)],
        ["Keyword in Titles", f"{kw_in_title} / {n_videos} videos"],
        ["Keyword in Descriptions", f"{kw_in_desc} / {n_videos} videos"],
    ]
    print(tabulate(overview, tablefmt="rounded_outline"))

    # — Top 4 Channels ————————————————————————
    print(f"\n{Style.BRIGHT}{Fore.CYAN}{'━' * 60}")
    print("  📺  TOP 4 CHANNELS  (by subscribers)")
    print(f"{'━' * 60}{Style.RESET_ALL}")
    ch_headers = ["#", "Channel Name", "Subscribers", "Videos", "Total Views", "URL"]
    ch_table = [[i + 1, r[1], r[2], r[3], r[4], r[5]] for i, r in enumerate(top4)]
    print(tabulate(ch_table, headers=ch_headers, tablefmt="rounded_outline"))

    # — Top 10 Videos —————————————————————————
    print(f"\n{Style.BRIGHT}{Fore.GREEN}{'━' * 60}")
    print("  🎬  TOP 10 VIDEOS")
    print(f"{'━' * 60}{Style.RESET_ALL}")
    vid_headers = [
        "#",
        "Title",
        "Channel",
        "Views",
        "Likes",
        "Comments",
        "KW in Title",
        "KW in Desc",
        "URL",
    ]
    print(tabulate(video_rows, headers=vid_headers, tablefmt="rounded_outline"))

    # — Keyword Frequency Summary ——————————————
    print(f"\n{Style.BRIGHT}{Fore.MAGENTA}{'━' * 60}")
    print(f"  🔤  KEYWORD FREQUENCY  (top {n_videos} videos)")
    print(f"{'━' * 60}{Style.RESET_ALL}")
    freq_data = [
        ["Occurrences in Titles", kw_in_title],
        ["Occurrences in Descriptions", kw_in_desc],
        ["Total Occurrences", kw_in_title + kw_in_desc],
        ["Videos where KW in Title", sum(1 for r in video_rows if r[6] > 0)],
        ["Videos where KW in Desc", sum(1 for r in video_rows if r[7] > 0)],
    ]
    print(tabulate(freq_data, tablefmt="rounded_outline"))

    print(f"\n{Fore.CYAN}{'─' * 60}")
    print(f"  ✅  Analysis complete for: {Style.BRIGHT}{keyword}")
    print(f"{Fore.CYAN}{'─' * 60}\n")


# ──────────────────────────────────────────────
#  Entry point
# ──────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="YouTube Keyword Evaluator – competition & analytics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--keyword",
        "-k",
        required=True,
        help='Keyword to analyse, e.g. "coffee and jazz"',
    )
    parser.add_argument(
        "--api-key",
        "-a",
        required=True,
        help="Your YouTube Data API v3 key",
    )

    args = parser.parse_args()

    try:
        analyse_keyword(api_key=args.api_key, keyword=args.keyword)
    except HttpError as e:
        print(f"\n{Fore.RED}❌  YouTube API error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.")


if __name__ == "__main__":
    main()
