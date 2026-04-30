"""Live fal.ai model catalog with on-disk cache.

fal.ai has no public model-listing API, so this scrapes the explore page once
and caches the result. Cache: ~/.cache/declip/fal_models.json, 24h TTL.
Resolution order on every call: live fetch (if stale) -> cached (any age) -> bundled fallback.

No HTML parser dependency: fal.ai's card markup is stable enough for a regex.
If they redesign the page, _parse_html() is the only thing that needs touching.

Source-of-truth dicts (ALIASES, MODEL_COST_PER_SEC) live here so generate.py
has one place to import from.
"""
from __future__ import annotations

import html as html_mod
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

CACHE_DIR = Path(os.environ.get("DECLIP_CACHE_DIR") or (Path.home() / ".cache" / "declip"))
CACHE_PATH = CACHE_DIR / "fal_models.json"
SOURCE_URL = "https://fal.ai/explore/models"
TTL_SECONDS = 24 * 60 * 60

# Convenient short names for popular models. Users can also pass any raw endpoint.
# `-i2v` siblings are kept for backward compatibility with pre-v0.9 batch specs;
# new code can rely on auto-rewrite from text-to-video to image-to-video.
ALIASES: dict[str, str] = {
    # Kling 3
    "kling-3":         "fal-ai/kling-video/v3/standard/text-to-video",
    "kling-3-pro":     "fal-ai/kling-video/v3/pro/text-to-video",
    "kling-3-i2v":     "fal-ai/kling-video/v3/standard/image-to-video",
    "kling-3-i2v-pro": "fal-ai/kling-video/v3/pro/image-to-video",
    # Kling 2.6
    "kling-2.6":       "fal-ai/kling-video/v2.6/standard/text-to-video",
    "kling-2.6-pro":   "fal-ai/kling-video/v2.6/pro/text-to-video",
    "kling-2.6-i2v":   "fal-ai/kling-video/v2.6/standard/image-to-video",
    # Wan
    "wan-2.6":         "fal-ai/wan/v2.6/text-to-video",
    "wan-2.6-i2v":     "fal-ai/wan/v2.6/image-to-video",
    "wan-2.5":         "fal-ai/wan-25-preview/text-to-video",
    "wan-2.5-i2v":     "fal-ai/wan-25-preview/image-to-video",
    # Budget / open-source
    "ltx":             "fal-ai/ltx-video-v097",
    "luma":            "fal-ai/luma-dream-machine/ray-2",
    "luma-flash":      "fal-ai/luma-dream-machine/ray-2-flash",
    # Premium / latest
    "veo-3":           "fal-ai/veo3",
    "veo-3.1":         "fal-ai/veo3.1",
    "veo-3.1-fast":    "fal-ai/veo3.1/fast",
    "sora-2":          "fal-ai/sora-2/text-to-video",
    "sora-2-pro":      "fal-ai/sora-2/text-to-video/pro",
}

# Per-second cost estimates, keyed by canonical endpoint.
# fal does not expose pricing in any API, so this is curated. Verify against
# fal.ai/pricing for billing-critical use.
MODEL_COST_PER_SEC: dict[str, float] = {
    "fal-ai/kling-video/v3/standard/text-to-video":   0.17,
    "fal-ai/kling-video/v3/pro/text-to-video":        0.22,
    "fal-ai/kling-video/v3/standard/image-to-video":  0.17,
    "fal-ai/kling-video/v3/pro/image-to-video":       0.22,
    "fal-ai/kling-video/v2.6/standard/text-to-video": 0.07,
    "fal-ai/kling-video/v2.6/pro/text-to-video":      0.14,
    "fal-ai/kling-video/v2.6/standard/image-to-video": 0.07,
    "fal-ai/wan/v2.6/text-to-video":                  0.06,
    "fal-ai/wan/v2.6/image-to-video":                 0.06,
    "fal-ai/wan-25-preview/text-to-video":            0.05,
    "fal-ai/wan-25-preview/image-to-video":           0.05,
    "fal-ai/ltx-video-v097":                          0.008,
    "fal-ai/luma-dream-machine/ray-2":                0.10,
    "fal-ai/luma-dream-machine/ray-2-flash":          0.04,
    "fal-ai/veo3":                                    0.40,
    "fal-ai/veo3.1":                                  0.30,
    "fal-ai/veo3.1/fast":                             0.10,
    "fal-ai/sora-2/text-to-video":                    0.30,
    "fal-ai/sora-2/text-to-video/pro":                0.50,
}

# Used only if both live fetch and cache are unavailable.
BUNDLED_FALLBACK_ENDPOINTS: tuple[str, ...] = tuple(ALIASES.values())


@dataclass
class ModelInfo:
    endpoint: str
    name: str
    description: str
    is_video: bool


def _is_video_endpoint(endpoint: str) -> bool:
    """Heuristic: does this endpoint output video?"""
    e = endpoint.lower()
    if any(seg in e for seg in (
        "text-to-video", "image-to-video", "video-to-video",
        "first-last-frame-to-video", "reference-to-video",
    )):
        return True
    for root in (
        "fal-ai/veo3", "fal-ai/veo2",
        "fal-ai/ltx-video", "fal-ai/luma-dream-machine",
        "fal-ai/sora-2",
    ):
        if e == root or e.startswith(root + "/"):
            return True
    return False


# Match a fal.ai model card. Structure (stable as of 2026-04):
#   <a class="page-model-card ..." href="/models/<endpoint>">...<img alt="<description>" ...</a>
# Anchored inside the same <a> tag so marquee cards (multiple <img> tags) don't
# steal descriptions from the next card. fal.ai never nests <a> inside cards,
# so naive </a> termination is safe here.
_CARD_PATTERN = re.compile(
    r'<a\s+class="page-model-card[^"]*"\s+href="/models/([a-z0-9][a-z0-9._/-]+)"'
    r'(.*?)</a>',
    re.DOTALL,
)
_IMG_ALT_PATTERN = re.compile(r'<img\s+alt="([^"]*)"')


def _parse_html(html: str) -> list[ModelInfo]:
    seen: dict[str, ModelInfo] = {}
    for endpoint, body in _CARD_PATTERN.findall(html):
        if endpoint in seen:
            continue
        alt_match = _IMG_ALT_PATTERN.search(body)
        raw_description = alt_match.group(1) if alt_match else ""
        description = html_mod.unescape(raw_description).strip()
        name = endpoint.split("/", 1)[1] if "/" in endpoint else endpoint
        seen[endpoint] = ModelInfo(
            endpoint=endpoint,
            name=name,
            description=description,
            is_video=_is_video_endpoint(endpoint),
        )
    return list(seen.values())


def _http_get(url: str, timeout: float = 10.0) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "declip-fetch-models/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _read_cache() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(payload: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(CACHE_PATH)


def fetch_models(force_refresh: bool = False) -> list[ModelInfo]:
    """Return the catalog. Falls back gracefully on network/parse failure."""
    cache = _read_cache()
    cache_fresh = (
        cache is not None
        and isinstance(cache.get("fetched_at"), (int, float))
        and (time.time() - cache["fetched_at"]) < TTL_SECONDS
    )
    if not force_refresh and cache_fresh:
        return [ModelInfo(**m) for m in cache["models"]]

    try:
        html = _http_get(SOURCE_URL)
        models = _parse_html(html)
        if models:
            _write_cache({
                "fetched_at": time.time(),
                "source_url": SOURCE_URL,
                "models": [asdict(m) for m in models],
            })
            return models
    except (urllib.error.URLError, TimeoutError, OSError):
        pass

    if cache is not None and cache.get("models"):
        return [ModelInfo(**m) for m in cache["models"]]

    return [
        ModelInfo(
            endpoint=ep,
            name=ep.split("/", 1)[1] if "/" in ep else ep,
            description="(bundled fallback - live fetch and cache both unavailable)",
            is_video=_is_video_endpoint(ep),
        )
        for ep in BUNDLED_FALLBACK_ENDPOINTS
    ]


def resolve_endpoint(name_or_endpoint: str) -> str:
    """Resolve a short alias to a canonical endpoint, or return input unchanged."""
    return ALIASES.get(name_or_endpoint, name_or_endpoint)


def cost_per_sec(name_or_endpoint: str) -> float | None:
    """Look up per-second cost. Accepts alias or endpoint. None if unknown."""
    endpoint = resolve_endpoint(name_or_endpoint)
    return MODEL_COST_PER_SEC.get(endpoint)


def to_image_to_video(endpoint: str) -> str:
    """Rewrite a text-to-video endpoint to its image-to-video sibling.

    Returns the input unchanged if no /text-to-video segment is present.
    """
    if "/text-to-video" in endpoint:
        return endpoint.replace("/text-to-video", "/image-to-video")
    return endpoint


def cache_status() -> dict:
    """Diagnostic info about the local cache."""
    cache = _read_cache()
    if cache is None:
        return {"cached": False, "path": str(CACHE_PATH)}
    age = time.time() - cache.get("fetched_at", 0)
    return {
        "cached": True,
        "path": str(CACHE_PATH),
        "fetched_at": cache.get("fetched_at"),
        "age_seconds": int(age),
        "fresh": age < TTL_SECONDS,
        "model_count": len(cache.get("models", [])),
        "source_url": cache.get("source_url"),
    }
