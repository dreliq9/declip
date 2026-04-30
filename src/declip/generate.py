"""AI video generation via fal.ai.

Model catalog comes from declip.fetch_models, which scrapes fal.ai/explore/models
and caches to ~/.cache/declip/fal_models.json (24h TTL). Aliases and
per-second pricing live there too.

Requires FAL_KEY environment variable to be set.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlretrieve

import fal_client

from declip.fetch_models import (
    ALIASES,
    cost_per_sec,
    fetch_models,
    resolve_endpoint,
    to_image_to_video,
)


def _check_key():
    if not os.environ.get("FAL_KEY"):
        raise RuntimeError(
            "FAL_KEY environment variable not set. "
            "Get your key at https://fal.ai/dashboard/keys"
        )


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

@dataclass
class GenerationResult:
    video_url: str
    local_path: str | None
    model: str
    duration: float
    estimated_cost: float
    seed: int | None = None


def _progress_callback(update):
    """Print progress during generation."""
    if isinstance(update, fal_client.InProgress):
        for log in update.logs:
            print(f"    {log['message']}", file=sys.stderr)


def generate_video(
    prompt: str,
    model: str = "kling-3",
    duration: int = 5,
    aspect_ratio: str = "16:9",
    output_path: str | Path | None = None,
    image_path: str | Path | None = None,
    end_image_path: str | Path | None = None,
    negative_prompt: str | None = None,
    generate_audio: bool = False,
    seed: int | None = None,
    resolution: str | None = None,
    progress_callback=None,
) -> GenerationResult:
    """Generate a video clip using fal.ai.

    Args:
        prompt: Text description of the video to generate
        model: Model name from MODELS registry (e.g., "kling-3", "wan-2.5")
        duration: Duration in seconds (model-dependent, typically 3-15)
        aspect_ratio: "16:9", "9:16", or "1:1"
        output_path: Where to save the video (None = don't download)
        image_path: Start image for image-to-video models
        end_image_path: End image (Kling only)
        negative_prompt: What to avoid
        generate_audio: Generate audio with video (Kling 3.0 only)
        seed: Reproducibility seed
        resolution: Resolution for Wan models ("480p", "720p", "1080p")
        progress_callback: Function called with fal_client queue updates
    """
    _check_key()

    # Resolve alias (or pass through if already a raw endpoint)
    endpoint = resolve_endpoint(model)

    # Auto-switch to i2v sibling if image provided and endpoint advertises text-to-video
    if image_path:
        endpoint = to_image_to_video(endpoint)

    # Build arguments
    args: dict = {
        "prompt": prompt,
        "duration": str(duration),
        "aspect_ratio": aspect_ratio,
    }

    if negative_prompt:
        args["negative_prompt"] = negative_prompt
    if seed is not None:
        args["seed"] = seed

    # Model-specific params
    if "kling" in endpoint:
        if generate_audio:
            args["generate_audio"] = True
        if image_path:
            args["start_image_url"] = _upload_image(image_path)
            if end_image_path:
                args["end_image_url"] = _upload_image(end_image_path)
    elif "wan" in endpoint:
        if resolution:
            args["resolution"] = resolution
        args["enable_prompt_expansion"] = True
        if image_path:
            args["image_url"] = _upload_image(image_path)

    # Submit and wait
    cb = progress_callback or _progress_callback
    result = fal_client.subscribe(
        endpoint,
        arguments=args,
        with_logs=True,
        on_queue_update=cb,
    )

    video_url = result["video"]["url"]
    result_seed = result.get("seed")

    # Estimate cost
    rate = cost_per_sec(model) or cost_per_sec(endpoint) or 0.10
    estimated_cost = rate * duration
    if generate_audio and "kling" in endpoint:
        estimated_cost *= 1.5  # Audio adds ~50%

    # Download if path provided
    local = None
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        urlretrieve(video_url, str(output_path))
        local = str(output_path)

    return GenerationResult(
        video_url=video_url,
        local_path=local,
        model=model,
        duration=duration,
        estimated_cost=round(estimated_cost, 3),
        seed=result_seed,
    )


def _upload_image(path: str | Path) -> str:
    """Upload a local image to fal.ai CDN."""
    path = Path(path)
    if str(path).startswith(("http://", "https://")):
        return str(path)  # Already a URL
    return fal_client.upload_file(str(path))


# ---------------------------------------------------------------------------
# Batch generation
# ---------------------------------------------------------------------------

def generate_batch(
    specs: list[dict],
    output_dir: str | Path = "generated",
) -> list[GenerationResult]:
    """Generate multiple videos from a list of specs.

    Each spec is a dict with keys matching generate_video() args:
    {"prompt": "...", "model": "kling-3", "duration": 5, ...}
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for i, spec in enumerate(specs):
        out_path = output_dir / f"gen_{i:03d}.mp4"
        spec.setdefault("output_path", str(out_path))

        print(f"  [{i+1}/{len(specs)}] Generating: {spec.get('prompt', '')[:60]}...",
              file=sys.stderr)

        try:
            result = generate_video(**spec)
            results.append(result)
        except Exception as e:
            print(f"    Error: {e}", file=sys.stderr)

    return results


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------

def estimate_cost(
    model: str = "kling-3",
    duration: int = 5,
    count: int = 1,
    audio: bool = False,
) -> dict:
    """Estimate generation cost without running anything."""
    endpoint = resolve_endpoint(model)
    rate = cost_per_sec(model) or cost_per_sec(endpoint) or 0.10
    per_clip = rate * duration
    if audio and "kling" in endpoint:
        per_clip *= 1.5
    return {
        "model": model,
        "endpoint": endpoint,
        "duration_sec": duration,
        "clips": count,
        "cost_per_clip": round(per_clip, 3),
        "total_cost": round(per_clip * count, 2),
        "audio_included": audio,
    }


def _classify_type(endpoint: str) -> str:
    e = endpoint.lower()
    if "/image-to-video" in e:
        return "image-to-video"
    if "/video-to-video" in e:
        return "video-to-video"
    if "/first-last-frame-to-video" in e:
        return "first-last-frame-to-video"
    if "/reference-to-video" in e:
        return "reference-to-video"
    if "/text-to-video" in e:
        return "text-to-video"
    return "video"  # bare-root endpoints like fal-ai/veo3, fal-ai/sora-2/text-to-video etc.


def list_models(force_refresh: bool = False, video_only: bool = True) -> dict[str, dict]:
    """List available models from the live fal.ai catalog plus convenience aliases.

    Returns a dict keyed by display name. For aliases the name is the short form
    ("kling-3"); for non-aliased catalog entries the name is the canonical endpoint.
    """
    catalog = fetch_models(force_refresh=force_refresh)
    by_endpoint = {m.endpoint: m for m in catalog}

    result: dict[str, dict] = {}

    # Aliases first so popular short names sort to the top of the dict
    for alias, endpoint in ALIASES.items():
        info = by_endpoint.get(endpoint)
        rate = cost_per_sec(endpoint)
        result[alias] = {
            "endpoint": endpoint,
            "type": _classify_type(endpoint),
            "cost_per_sec": rate,
            "cost_5sec": round(rate * 5, 2) if rate is not None else None,
            "description": info.description if info else None,
            "in_catalog": info is not None,
        }

    # Then catalog entries that don't already have an alias
    aliased_endpoints = set(ALIASES.values())
    for m in catalog:
        if m.endpoint in aliased_endpoints:
            continue
        if video_only and not m.is_video:
            continue
        rate = cost_per_sec(m.endpoint)
        result[m.endpoint] = {
            "endpoint": m.endpoint,
            "type": _classify_type(m.endpoint),
            "cost_per_sec": rate,
            "cost_5sec": round(rate * 5, 2) if rate is not None else None,
            "description": m.description,
            "in_catalog": True,
        }

    return result
