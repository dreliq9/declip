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
    ) -> str:
        """List AI video generation models with pricing. Optionally estimate cost for a specific model.

        Call with no args to see all models and pricing. Set estimate_model to
        get a cost estimate for a specific generation job.

        Args:
            estimate_model: If set, estimate cost for this model instead of listing all
            estimate_duration: Duration in seconds per clip (for estimates)
            estimate_count: Number of clips (for estimates)
        """
        if estimate_model:
            from declip.generate import estimate_cost
            result = estimate_cost(model=estimate_model, duration=estimate_duration, count=estimate_count)
            return (f"Model: {result['model']}\n"
                    f"Duration: {result['duration_sec']}s x {result['clips']} clip(s)\n"
                    f"Per clip: ${result['cost_per_clip']:.3f}\n"
                    f"Total: ${result['total_cost']:.2f}")

        from declip.generate import list_models
        result = list_models()
        lines = []
        for name, info in result.items():
            type_tag = "i2v" if info["type"] == "image-to-video" else "t2v"
            lines.append(f"{name}: {type_tag}, ${info['cost_per_sec']:.3f}/sec (${info['cost_5sec']:.2f}/5s)")
        return "\n".join(lines)
