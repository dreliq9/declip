"""MCP tools for AI video generation via fal.ai."""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def declip_generate(
        prompt: str,
        model: str = "kling-3",
        duration: int = 5,
        output_path: str | None = None,
        aspect_ratio: str = "16:9",
        image_path: str | None = None,
        end_image_path: str | None = None,
        negative_prompt: str | None = None,
        generate_audio: bool = False,
        seed: int | None = None,
        resolution: str | None = None,
    ) -> str:
        """Generate a video clip using AI via fal.ai.

        Requires FAL_KEY environment variable. Use declip_models to see available models.

        Models: kling-3 (#1 quality), kling-3-pro (best), wan-2.5 (cheapest good),
        ltx (budget), luma-flash, luma, veo-3 (premium).
        Add "-i2v" suffix for image-to-video variants.

        Args:
            prompt: Text description of the video to generate
            model: Model name (kling-3, wan-2.5, ltx, etc.)
            duration: Duration in seconds (3-15 depending on model)
            output_path: Where to save the video
            aspect_ratio: "16:9", "9:16", or "1:1"
            image_path: Start image path/URL for image-to-video
            end_image_path: End image path/URL (Kling only)
            negative_prompt: What to avoid in generation
            generate_audio: Generate audio with video (Kling 3.0 only)
            seed: Seed for reproducibility
            resolution: Resolution for Wan models (480p, 720p, 1080p)
        """
        from declip.generate import generate_video

        if not output_path:
            safe = "".join(c if c.isalnum() else "_" for c in prompt[:30])
            output_path = f"gen_{safe}.mp4"

        try:
            result = generate_video(
                prompt=prompt, model=model, duration=duration,
                aspect_ratio=aspect_ratio, output_path=output_path,
                image_path=image_path, end_image_path=end_image_path,
                negative_prompt=negative_prompt, generate_audio=generate_audio,
                seed=seed, resolution=resolution,
            )
            lines = [
                f"Generated: {result.local_path}",
                f"Model: {result.model}",
                f"Estimated cost: ${result.estimated_cost:.3f}",
            ]
            if result.seed is not None:
                lines.append(f"Seed: {result.seed}")
            lines.append(f"URL: {result.video_url}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def declip_generate_batch(
        specs: str,
        output_dir: str = "generated",
    ) -> str:
        """Generate multiple AI video clips in sequence.

        Args:
            specs: JSON string — array of objects, each with: prompt, model, duration, etc.
                   Example: [{"prompt": "A sunset", "model": "kling-3", "duration": 5}]
            output_dir: Directory to save generated clips
        """
        import json
        from declip.generate import generate_batch

        try:
            spec_list = json.loads(specs)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"

        try:
            results = generate_batch(spec_list, output_dir)
            lines = [f"Generated {len(results)} clip(s):"]
            total_cost = 0.0
            for r in results:
                lines.append(f"  {r.local_path} ({r.model}, ~${r.estimated_cost:.3f})")
                total_cost += r.estimated_cost
            lines.append(f"Total estimated cost: ${total_cost:.2f}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def declip_models(
        estimate_model: str = "",
        estimate_duration: int = 5,
        estimate_count: int = 1,
        filter_substring: str = "",
        force_refresh: bool = False,
        include_non_video: bool = False,
    ) -> str:
        """List AI video generation models from the live fal.ai catalog with pricing.

        The catalog is fetched from fal.ai/explore/models and cached for 24h. By
        default lists video-output models only. Cost-per-second is None for models
        without a curated price entry — verify on fal.ai/pricing before billing-critical use.

        Args:
            estimate_model: If set, estimate cost for this model and skip the listing.
            estimate_duration: Duration in seconds per clip (for estimates).
            estimate_count: Number of clips (for estimates).
            filter_substring: If set, only show models whose endpoint or alias contains this string.
            force_refresh: Refetch the catalog now, bypassing the 24h cache.
            include_non_video: Include image / audio / utility models too.
        """
        if estimate_model:
            from declip.generate import estimate_cost
            result = estimate_cost(model=estimate_model, duration=estimate_duration, count=estimate_count)
            return (f"Model: {result['model']}\n"
                    f"Endpoint: {result['endpoint']}\n"
                    f"Duration: {result['duration_sec']}s x {result['clips']} clip(s)\n"
                    f"Per clip: ${result['cost_per_clip']:.3f}\n"
                    f"Total: ${result['total_cost']:.2f}")

        from declip.generate import list_models
        result = list_models(force_refresh=force_refresh, video_only=not include_non_video)
        if filter_substring:
            needle = filter_substring.lower()
            result = {
                name: info for name, info in result.items()
                if needle in name.lower() or needle in info["endpoint"].lower()
            }

        lines = [f"{len(result)} model(s):"]
        for name, info in result.items():
            type_short = {
                "text-to-video": "t2v",
                "image-to-video": "i2v",
                "video-to-video": "v2v",
                "reference-to-video": "r2v",
                "first-last-frame-to-video": "flf",
            }.get(info["type"], "vid")
            cost = info["cost_per_sec"]
            cost_str = f"${cost:.3f}/sec" if cost is not None else "$?/sec"
            line = f"  {name}: {type_short}, {cost_str}"
            if info.get("description"):
                line += f"  — {info['description'][:60]}"
            lines.append(line)
        return "\n".join(lines)

    @mcp.tool()
    def declip_refresh_models(force: bool = True) -> str:
        """Refresh the local fal.ai model cache.

        Triggers an immediate fetch from fal.ai/explore/models and writes
        ~/.cache/declip/fal_models.json. Reports cache status before and after.

        Args:
            force: If True (default), refetch even if cache is fresh.
        """
        from declip.fetch_models import cache_status, fetch_models

        before = cache_status()
        models = fetch_models(force_refresh=force)
        after = cache_status()

        videos = [m for m in models if m.is_video]
        return (
            f"Cache: {after.get('path')}\n"
            f"Before: {'cached, age=' + str(before['age_seconds']) + 's' if before.get('cached') else 'no cache'}\n"
            f"After: {'cached, age=' + str(after['age_seconds']) + 's, fresh=' + str(after['fresh']) if after.get('cached') else 'fetch failed - using bundled fallback'}\n"
            f"Models: {len(models)} total, {len(videos)} video"
        )
