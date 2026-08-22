"""Structured results for Declip production pipelines."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class PipelineResult(BaseModel):
    success: bool
    message: str
    output_path: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    def __str__(self) -> str:
        if self.success:
            return self.message
        return self.message if self.message.startswith("Error:") else f"Error: {self.message}"
