"""
YouTube Keyword Evaluator — REST API
=====================================
FastAPI server exposing keyword analysis over HTTP.

Quick start:
    cp .env.example .env          # add your YOUTUBE_API_KEY
    uv run uvicorn api:app --reload

Interactive docs:
    http://localhost:8000/docs    (Swagger UI)
    http://localhost:8000/redoc   (ReDoc)

Auth (choose one):
  • Set YOUTUBE_API_KEY in .env or environment  ← server-wide default
  • Pass X-YouTube-API-Key header per request   ← per-request override

Query parameters:
  ?full=true   Return full response (videos list + channels + score breakdown)
  ?full=false  Return short summary only (default)
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; env vars can be set directly

from analyzer import DEFAULT_SETTINGS, analyse_keyword

# ─────────────────────────────────────────────────────────────────────────────
#  App setup
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="YouTube Keyword Evaluator API",
    description=(
        "Analyse YouTube keywords and get a **Keyword Opportunity Score (KOS)**"
        " — a 0–100 score indicating how easy it is to rank for that keyword.\n\n"
        "Supports **single** and **bulk** keyword research with optional full or"
        " summary responses."
    ),
    version="1.0.0",
    contact={
        "name": "YouTube Keyword Evaluator",
        "url": "https://github.com/medram/YouTube-Keyword-Evaluator",
    },
    license_info={"name": "MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional: simple in-process request rate stats (no external deps)
_stats: dict[str, Any] = {"requests": 0, "errors": 0, "start_time": time.time()}


# ─────────────────────────────────────────────────────────────────────────────
#  Pydantic models
# ─────────────────────────────────────────────────────────────────────────────


class VideoShort(BaseModel):
    rank: int
    title: str
    channel: str
    published: str
    views: int
    views_fmt: str
    likes: int
    like_ratio_pct: str
    comments: int
    views_per_month: int
    views_per_month_fmt: str
    kw_in_title: int
    kw_pos_in_title: str
    kw_in_desc: int
    url: str


class ChannelShort(BaseModel):
    channel: str
    subscribers: int
    subscribers_fmt: str
    videos: int
    videos_fmt: str
    total_views: int
    total_views_fmt: str
    channel_age_years: float
    url: str


class ScoreBreakdown(BaseModel):
    score_a: int = Field(..., description="Group A (video metrics) score")
    score_b: int = Field(..., description="Group B (channel metrics) score")
    score_c: int = Field(..., description="Group C (saturation) score")
    max_a: int
    max_b: int
    max_c: int
    pts_a: dict[str, int] = Field(..., description="Per-metric Group A points")
    pts_b: dict[str, int] = Field(..., description="Per-metric Group B points")
    pts_c: dict[str, int] = Field(..., description="Per-metric Group C points")


class KeywordSummary(BaseModel):
    """Lightweight summary — returned when ?full=false (default)."""

    keyword: str
    kos: int = Field(..., ge=0, le=100, description="Keyword Opportunity Score (0-100)")
    kos_label: str = Field(
        ..., description="Great Opportunity | Moderate | Tough | Very Competitive"
    )
    kos_emoji: str
    competition_level: str = Field(..., description="Low | Medium | High | Very High")
    # aggregates
    total_views: int
    avg_views: int
    avg_views_fmt: str
    avg_like_ratio_pct: str
    avg_comments: int
    avg_age_months: float
    avg_vpm: int
    avg_vpm_fmt: str
    kw_in_title: int
    kw_in_desc: int
    # channel summary
    avg_subs: int
    avg_subs_fmt: str
    avg_ch_vid_count: int
    avg_ch_age_y: float
    # score breakdown (always included so clients can render gauges)
    score_breakdown: ScoreBreakdown


class KeywordFull(KeywordSummary):
    """Full response — returned when ?full=true."""

    videos: list[VideoShort]
    top4_channels: list[ChannelShort]


class KeywordError(BaseModel):
    keyword: str
    error: str


class BulkResult(BaseModel):
    results: list[KeywordSummary | KeywordFull | KeywordError]
    total: int
    succeeded: int
    failed: int
    elapsed_seconds: float


# ─────────────────────────────────────────────────────────────────────────────
#  Request bodies
# ─────────────────────────────────────────────────────────────────────────────


class SingleRequest(BaseModel):
    keyword: str = Field(
        ..., min_length=1, max_length=200, examples=["lofi study music"]
    )
    full: bool = Field(False, description="Return full data (videos + channels)")

    @field_validator("keyword")
    @classmethod
    def strip_keyword(cls, v: str) -> str:
        return v.strip()


class BulkRequest(BaseModel):
    keywords: list[str] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="1–20 keywords to analyse",
        examples=[["lofi study music", "coffee and jazz", "morning yoga routine"]],
    )
    full: bool = Field(False, description="Return full data for each keyword")
    concurrency: int = Field(
        3,
        ge=1,
        le=5,
        description="Max parallel API calls (1–5). Lower = fewer quota units burned at once.",
    )

    @field_validator("keywords")
    @classmethod
    def strip_keywords(cls, v: list[str]) -> list[str]:
        cleaned = [kw.strip() for kw in v if kw.strip()]
        if not cleaned:
            raise ValueError("At least one non-empty keyword required.")
        return cleaned


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

_ENV_API_KEY = os.getenv("YOUTUBE_API_KEY", "")


def _resolve_api_key(header_key: str | None) -> str:
    """Return the YouTube API key, preferring the per-request header."""
    key = (header_key or "").strip() or _ENV_API_KEY.strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "No YouTube API key provided. "
                "Set the X-YouTube-API-Key header or the YOUTUBE_API_KEY env variable."
            ),
        )
    return key


def _build_response(
    raw: dict,
    full: bool,
) -> KeywordSummary | KeywordFull | KeywordError:
    """Convert the raw analyser dict into the appropriate response model."""
    if "error" in raw:
        return KeywordError(keyword=raw.get("keyword", ""), error=raw["error"])

    breakdown = ScoreBreakdown(
        score_a=raw["score_a"],
        score_b=raw["score_b"],
        score_c=raw["score_c"],
        max_a=raw["max_a"],
        max_b=raw["max_b"],
        max_c=raw["max_c"],
        pts_a=raw["pts_a"],
        pts_b=raw["pts_b"],
        pts_c=raw["pts_c"],
    )

    common: dict[str, Any] = dict(
        keyword=raw["keyword"],
        kos=raw["kos"],
        kos_label=raw["kos_label"],
        kos_emoji=raw["kos_emoji"],
        competition_level=raw["competition_level"],
        total_views=raw["total_views"],
        avg_views=raw["avg_views"],
        avg_views_fmt=raw["avg_views_fmt"],
        avg_like_ratio_pct=raw["avg_like_ratio_pct"],
        avg_comments=raw["avg_comments"],
        avg_age_months=raw["avg_age_months"],
        avg_vpm=raw["avg_vpm"],
        avg_vpm_fmt=raw["avg_vpm_fmt"],
        kw_in_title=raw["kw_in_title"],
        kw_in_desc=raw["kw_in_desc"],
        avg_subs=raw["avg_subs"],
        avg_subs_fmt=raw["avg_subs_fmt"],
        avg_ch_vid_count=raw["avg_ch_vid_count"],
        avg_ch_age_y=raw["avg_ch_age_y"],
        score_breakdown=breakdown,
    )

    if full:
        return KeywordFull(
            **common,
            videos=[VideoShort(**v) for v in raw["videos"]],
            top4_channels=[ChannelShort(**c) for c in raw["top4_channels"]],
        )
    return KeywordSummary(**common)


async def _analyse_async(
    api_key: str, keyword: str, full: bool, settings: dict | None = None
) -> dict:
    """Run the blocking analyser in a thread pool so FastAPI stays async."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: analyse_keyword(api_key, keyword, settings=settings),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Middleware — request counter
# ─────────────────────────────────────────────────────────────────────────────


@app.middleware("http")
async def _track_stats(request: Request, call_next):
    _stats["requests"] += 1
    response = await call_next(request)
    if response.status_code >= 400:
        _stats["errors"] += 1
    return response


# ─────────────────────────────────────────────────────────────────────────────
#  Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@app.get(
    "/health",
    summary="Health check",
    tags=["System"],
    response_description="Service is up",
)
async def health():
    """Returns service health status and basic request statistics."""
    uptime = round(time.time() - _stats["start_time"], 1)
    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "total_requests": _stats["requests"],
        "total_errors": _stats["errors"],
        "youtube_api_key_configured": bool(_ENV_API_KEY),
    }


@app.get(
    "/api/v1/settings",
    summary="Current scoring settings",
    tags=["System"],
    response_description="Active KOS scoring profile (thresholds & point caps)",
)
async def get_settings():
    """Returns the active scoring settings profile used for all KOS calculations.

    These thresholds and point caps determine how the Keyword Opportunity Score
    is computed across Group A (video metrics), Group B (channel metrics), and
    Group C (saturation).
    """
    from analyzer import max_group_a, max_group_b, max_group_c, total_max

    return {
        "settings": DEFAULT_SETTINGS,
        "max_points": {
            "group_a": max_group_a(DEFAULT_SETTINGS),
            "group_b": max_group_b(DEFAULT_SETTINGS),
            "group_c": max_group_c(DEFAULT_SETTINGS),
            "total": total_max(DEFAULT_SETTINGS),
        },
    }


# ── Single keyword — GET ──────────────────────────────────────────────────────


@app.get(
    "/api/v1/analyze",
    summary="Analyze a single keyword (GET)",
    tags=["Keyword Analysis"],
    response_model=KeywordSummary | KeywordFull,
    responses={
        200: {"description": "Analysis result"},
        401: {"description": "Missing YouTube API key"},
        422: {"description": "Validation error"},
        502: {"description": "YouTube API error"},
    },
)
async def analyze_get(
    keyword: str = Query(
        ..., min_length=1, max_length=200, description="Keyword to analyse"
    ),
    full: bool = Query(
        False, description="Set true to include videos list and top channels"
    ),
    x_youtube_api_key: str | None = Header(
        None, description="YouTube Data API v3 key (overrides env var)"
    ),
):
    """
    Analyse a single YouTube keyword.

    - **keyword** – the term to evaluate (e.g. `lofi study music`)
    - **full** – `false` (default) returns a compact summary;
      `true` also returns the top 10 video details and top 4 channels
    - **X-YouTube-API-Key** – optional per-request API key header
    """
    api_key = _resolve_api_key(x_youtube_api_key)
    keyword = keyword.strip()
    raw = await _analyse_async(api_key, keyword, full)
    if "error" in raw:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=raw["error"]
        )
    return _build_response(raw, full)


# ── Single keyword — POST ─────────────────────────────────────────────────────


@app.post(
    "/api/v1/analyze",
    summary="Analyze a single keyword (POST)",
    tags=["Keyword Analysis"],
    response_model=KeywordSummary | KeywordFull,
    responses={
        200: {"description": "Analysis result"},
        401: {"description": "Missing YouTube API key"},
        502: {"description": "YouTube API error"},
    },
)
async def analyze_post(
    body: SingleRequest,
    x_youtube_api_key: str | None = Header(
        None, description="YouTube Data API v3 key (overrides env var)"
    ),
):
    """
    Analyse a single YouTube keyword (request body variant).

    Prefer this over the GET endpoint when scripting, since the keyword
    is sent in the body rather than as a URL parameter.
    """
    api_key = _resolve_api_key(x_youtube_api_key)
    raw = await _analyse_async(api_key, body.keyword, body.full)
    if "error" in raw:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=raw["error"]
        )
    return _build_response(raw, body.full)


# ── Bulk keywords — POST ──────────────────────────────────────────────────────


@app.post(
    "/api/v1/analyze/bulk",
    summary="Analyze multiple keywords (bulk)",
    tags=["Keyword Analysis"],
    response_model=BulkResult,
    responses={
        200: {"description": "Bulk analysis results"},
        401: {"description": "Missing YouTube API key"},
    },
)
async def analyze_bulk(
    body: BulkRequest,
    x_youtube_api_key: str | None = Header(
        None, description="YouTube Data API v3 key (overrides env var)"
    ),
):
    """
    Analyse **1–20 keywords** in a single request.

    Keywords are processed concurrently (up to `concurrency` at a time, default 3)
    to respect YouTube API quota while staying fast.

    Each entry in `results` is either a **KeywordSummary** / **KeywordFull** on
    success, or a **KeywordError** if that individual keyword failed.

    The response also includes `total`, `succeeded`, `failed`, and
    `elapsed_seconds` for easy reporting.
    """
    api_key = _resolve_api_key(x_youtube_api_key)
    t0 = time.time()

    semaphore = asyncio.Semaphore(body.concurrency)

    async def _limited(kw: str):
        async with semaphore:
            return await _analyse_async(api_key, kw, body.full)

    raws = await asyncio.gather(*[_limited(kw) for kw in body.keywords])

    results = [_build_response(r, body.full) for r in raws]
    succeeded = sum(1 for r in results if not isinstance(r, KeywordError))
    failed = len(results) - succeeded

    return BulkResult(
        results=results,
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        elapsed_seconds=round(time.time() - t0, 2),
    )


# ── Compare keywords ──────────────────────────────────────────────────────────


@app.post(
    "/api/v1/analyze/compare",
    summary="Compare keywords and rank by opportunity",
    tags=["Keyword Analysis"],
    responses={
        200: {"description": "Keywords ranked by KOS descending"},
        401: {"description": "Missing YouTube API key"},
    },
)
async def compare_keywords(
    body: BulkRequest,
    x_youtube_api_key: str | None = Header(
        None, description="YouTube Data API v3 key (overrides env var)"
    ),
):
    """
    Analyse multiple keywords and return them **ranked by KOS (highest first)**.

    Includes a `recommendation` field pointing to the best keyword and a brief
    `reasoning` field explaining the choice.

    Use this endpoint to quickly determine which keyword to target out of a list
    of candidates.
    """
    api_key = _resolve_api_key(x_youtube_api_key)
    t0 = time.time()

    semaphore = asyncio.Semaphore(body.concurrency)

    async def _limited(kw: str):
        async with semaphore:
            return await _analyse_async(api_key, kw, body.full)

    raws = await asyncio.gather(*[_limited(kw) for kw in body.keywords])
    built = [_build_response(r, body.full) for r in raws]

    # Sort successes by KOS desc; errors go last
    successes = sorted(
        [r for r in built if not isinstance(r, KeywordError)],
        key=lambda r: r.kos,
        reverse=True,
    )
    errors = [r for r in built if isinstance(r, KeywordError)]
    ranked = successes + errors

    recommendation = None
    reasoning = None
    if successes:
        best = successes[0]
        recommendation = best.keyword
        reasoning = (
            f'"{best.keyword}" has the highest KOS of {best.kos}/100 '
            f"({best.kos_label}) with {best.competition_level} competition "
            f"and an average of {best.avg_views_fmt} views per video."
        )

    return {
        "ranked": [r.model_dump() for r in ranked],
        "recommendation": recommendation,
        "reasoning": reasoning,
        "total": len(ranked),
        "elapsed_seconds": round(time.time() - t0, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=os.getenv("API_RELOAD", "true").lower() == "true",
        log_level=os.getenv("API_LOG_LEVEL", "info"),
    )
