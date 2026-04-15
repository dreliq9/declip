"""AI video generation via fal.ai — Kling 3.0, Wan 2.5, and other models.

Requires FAL_KEY environment variable to be set.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlretrieve

import fal_client


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

MODELS = {
    # Kling 3.0
    "kling-3": "fal-ai/kling-video/v3/standard/text-to-video",
    "kling-3-pro": "fal-ai/kling-video/v3/pro/text-to-video",
    "kling-3-i2v": "fal-ai/kling-video/v3/standard/image-to-video",
    "kling-3-i2v-pro": "fal-ai/kling-video/v3/pro/image-to-video",
    # Kling 2.6
    "kling-2.6": "fal-ai/kling-video/v2.6/standard/text-to-video",
    "kling-2.6-pro": "fal-ai/kling-video/v2.6/pro/text-to-video",
    "kling-2.6-i2v": "fal-ai/kling-video/v2.6/standard/image-to-video",
    # Wan 2.5
    "wan-2.5": "fal-ai/wan-25-preview/text-to-video",
    "wan-2.5-i2v": "fal-ai/wan-25-preview/image-to-video",
    # Wan 2.6
    "wan-2.6": "fal-ai/wan/v2.6/text-to-video",
    "wan-2.6-i2v": "fal-ai/wan/v2.6/image-to-video",
    # Budget options
    "ltx": "fal-ai/ltx-video",
    "luma-flash": "fal-ai/luma-dream-machine/ray-2-flash",
    "luma": "fal-ai/luma-dream-machine/ray-2",
    # Premium
    "veo-3": "fal-ai/veo3",
}

# Approximate cost per second (for estimation, not billing)
MODEL_COST_PER_SEC = {
    "kling-3": 0.17, "kling-3-pro": 0.22,
    "kling-2.6": 0.07, "kling-2.6-pro": 0.14,
    "wan-2.5": 0.05, "wan-2.6": 0.06,
    "ltx": 0.008, "luma-flash": 0.04, "luma": 0.10,
    "veo-3": 0.40,
}


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

    # Resolve model endpoint
    if model in MODELS:
        endpoint = MODELS[model]
    else:
        endpoint = model  # Allow raw endpoint IDs

    # Auto-switch to i2v endpoint if image provided
    if image_path and not model.endswith("-i2v"):
        i2v_model = model + "-i2v"
        if i2v_model in MODELS:
            endpoint = MODELS[i2v_model]

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
    cost_per_sec = MODEL_COST_PER_SEC.get(model, 0.10)
    estimated_cost = cost_per_sec * duration
    if generate_audio and "kling" in model:
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
    """Estimate generation cost without running anything.

    Returns dict with per-clip and total cost.
    """
    cost_per_sec = MODEL_COST_PER_SEC.get(model, 0.10)
    per_clip = cost_per_sec * duration
    if audio and "kling" in model:
        per_clip *= 1.5
    return {
        "model": model,
        "duration_sec": duration,
        "clips": count,
        "cost_per_clip": round(per_clip, 3),
        "total_cost": round(per_clip * count, 2),
        "audio_included": audio,
    }


def list_models() -> dict[str, dict]:
    """List available models with pricing info."""
    result = {}
    for name, endpoint in MODELS.items():
        is_i2v = name.endswith("-i2v")
        cost = MODEL_COST_PER_SEC.get(name.replace("-i2v", ""), 0.10)
        result[name] = {
            "endpoint": endpoint,
            "type": "image-to-video" if is_i2v else "text-to-video",
            "cost_per_sec": cost,
            "cost_5sec": round(cost * 5, 2),
        }
    return result
