"""Redaction: text placeholder replacement + image black-box overlay."""

from __future__ import annotations

from pathlib import Path

from .schemas import Entity, OCRBlock


def redact_text(text: str, entities: list[Entity]) -> str:
    """Replace every selected entity occurrence with its placeholder.

    Longer entity texts are replaced first so substrings of an already-replaced
    entity don't corrupt the placeholder.
    """
    selected = [e for e in entities if e.selected and e.text.strip()]
    for ent in sorted(selected, key=lambda e: len(e.text), reverse=True):
        text = text.replace(ent.text, ent.replacement)
    return text


def redact_image(
    image_path: str | Path,
    entities: list[Entity],
    blocks: list[OCRBlock],
    output_path: str | Path,
) -> Path:
    """Draw black rectangles over OCR blocks containing selected entity text.

    Line-level redaction (whole block is covered) — acceptable for the demo.
    """
    from PIL import Image, ImageDraw

    selected = [e for e in entities if e.selected and e.text.strip()]
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    for ent in selected:
        boxes = [ent.bbox] if ent.bbox else [
            b.bbox for b in blocks if ent.text in b.text
        ]
        for box in boxes:
            if box and len(box) == 4:
                draw.rectangle(box, fill="black")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)
    return output_path


def validate_redaction(redacted_text: str, entities: list[Entity]) -> tuple[bool, list[dict]]:
    """Re-scan the redacted text: no selected entity and no fresh regex hit may remain."""
    from .detectors import detect_regex

    checks: list[dict] = []
    passed = True

    for ent in entities:
        if not ent.selected:
            continue
        ok = ent.text not in redacted_text
        checks.append(
            {
                "check": f"实体已替换: {ent.id}",
                "passed": ok,
                "detail": "" if ok else f"原文 {ent.masked_text} 仍出现在输出中",
            }
        )
        passed = passed and ok

    residual = [e for e in detect_regex(redacted_text) if e.risk_level == "high"]
    ok = not residual
    checks.append(
        {
            "check": "无残留高风险模式（手机号/邮箱/银行账号等）",
            "passed": ok,
            "detail": "" if ok else f"仍检测到 {len(residual)} 个高风险片段: "
            + ", ".join(f"{e.entity_type}({e.masked_text})" for e in residual[:5]),
        }
    )
    passed = passed and ok
    return passed, checks
