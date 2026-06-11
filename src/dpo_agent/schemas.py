"""Pydantic data models shared across the pipeline."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

RiskLevel = Literal["high", "medium", "low"]
EntitySource = Literal["regex", "keyword", "claude", "user"]


class Entity(BaseModel):
    """A detected sensitive entity, candidate for redaction."""

    id: str
    text: str
    masked_text: str = ""
    entity_type: str
    replacement: str
    risk_level: RiskLevel = "medium"
    source: EntitySource = "regex"
    reason: str = ""
    bbox: Optional[list[float]] = None  # [x0, y0, x1, y1] for image/OCR entities
    page: Optional[int] = None
    selected: bool = True

    def model_post_init(self, __context) -> None:
        if not self.masked_text:
            self.masked_text = mask_text(self.text)


class OCRBlock(BaseModel):
    """One line/block of OCR output with its bounding box."""

    text: str
    bbox: list[float]  # [x0, y0, x1, y1]
    confidence: float = 1.0
    page: int = 0


class DetectionResult(BaseModel):
    file_path: str
    file_type: str
    text: str = ""
    entities: list[Entity] = Field(default_factory=list)
    ocr_blocks: list[OCRBlock] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)  # per-layer hit counts, timings


class RedactionResult(BaseModel):
    input_file: str
    output_files: list[str] = Field(default_factory=list)
    report_file: str = ""
    validation_passed: bool = False
    validation_details: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def mask_text(text: str) -> str:
    """Mask the middle of a string for safe preview display."""
    t = text.strip()
    if len(t) <= 2:
        return t[:1] + "*"
    if len(t) <= 5:
        return t[0] + "*" * (len(t) - 2) + t[-1]
    keep = max(2, len(t) // 4)
    return t[:keep] + "*" * min(6, len(t) - 2 * keep) + t[-keep:]
