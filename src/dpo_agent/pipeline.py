"""Orchestrates the core loop: detect → review → redact → validate → export.

Each step is a plain function so the CLI, the Gradio UI and the Agent SDK
tools can all drive it. `detect()` and `redact()` optionally emit progress
lines through a callback so the UI can stream intermediate results.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from . import document_io
from .claude_detect import detect_claude
from .detectors import apply_strict_mode, detect_keyword, detect_regex, merge_entities
from .redactors import redact_text, validate_redaction
from .report import write_reports
from .schemas import DetectionResult, Entity, OCRBlock, RedactionResult

ProgressFn = Callable[[str], None]


def _noop(_: str) -> None:
    pass


def detect(
    file_path: str | Path,
    use_claude: bool = True,
    strict: bool = False,
    ocr_provider: Optional[str] = None,
    progress: ProgressFn = _noop,
) -> DetectionResult:
    file_path = str(file_path)
    ftype = document_io.file_type_of(file_path)
    stats: dict = {}
    warnings: list[str] = []
    ocr_blocks: list[OCRBlock] = []

    # ---- parse ----
    progress(f"📄 解析文件（{ftype}）…")
    text, parse_stats = document_io.read_document(file_path)
    stats.update(parse_stats)
    progress(f"   解析完成: {parse_stats}")

    # ---- OCR for images / scanned docs ----
    if ftype == "image":
        if not ocr_provider:
            ocr_provider = "mock"
            warnings.append("未指定 OCR provider，使用 mock")
        progress(f"🔍 OCR 识别中（provider: {ocr_provider}）…")
        from .ocr import get_provider

        try:
            blocks = get_provider(ocr_provider).recognize(file_path)
            ocr_blocks = blocks
            text = "\n".join(b.text for b in blocks)
            stats["OCR 行数"] = len(blocks)
            progress(f"   OCR 完成: {len(blocks)} 行")
        except Exception as exc:
            warnings.append(f"OCR 失败: {exc}")
            progress(f"   ⚠️ OCR 失败: {exc}")

    # ---- layer 1: regex ----
    progress("🧩 第 1 层：Regex 检测…")
    regex_entities = detect_regex(text)
    by_type: dict[str, int] = {}
    for e in regex_entities:
        by_type[e.entity_type] = by_type.get(e.entity_type, 0) + 1
    stats["regex 命中"] = by_type or 0
    progress(
        "   命中 "
        + (", ".join(f"{k} {v} 个" for k, v in by_type.items()) if by_type else "0 个")
    )

    # ---- layer 2: keyword ----
    progress("🗝️ 第 2 层：关键词/上下文检测…")
    keyword_entities = detect_keyword(text)
    by_type = {}
    for e in keyword_entities:
        by_type[e.entity_type] = by_type.get(e.entity_type, 0) + 1
    stats["keyword 命中"] = by_type or 0
    progress(
        "   命中 "
        + (", ".join(f"{k} {v} 个" for k, v in by_type.items()) if by_type else "0 个")
    )

    # ---- layer 3: claude ----
    claude_entities: list[Entity] = []
    if use_claude:
        progress("🤖 第 3 层：Claude 语义检测…")
        claude_entities, claude_warnings, elapsed = detect_claude(text)
        warnings.extend(claude_warnings)
        stats["claude 命中"] = len(claude_entities)
        stats["claude 耗时(s)"] = round(elapsed, 2)
        if claude_warnings:
            for w in claude_warnings:
                progress(f"   ⚠️ {w}")
        else:
            progress(f"   返回 {len(claude_entities)} 个实体，耗时 {elapsed:.1f}s")
    else:
        progress("⏭️ 跳过 Claude 语义检测层（--no-claude）")

    # ---- merge ----
    entities = merge_entities(regex_entities, keyword_entities, claude_entities)
    apply_strict_mode(entities, strict)
    # attach bboxes from OCR blocks
    for ent in entities:
        if not ent.bbox and ocr_blocks:
            for b in ocr_blocks:
                if ent.text in b.text:
                    ent.bbox = b.bbox
                    ent.page = b.page
                    break
    stats["实体总数(去重后)"] = len(entities)
    progress(f"✅ 检测完成：合并去重后共 {len(entities)} 个候选实体")

    return DetectionResult(
        file_path=file_path,
        file_type=ftype,
        text=text,
        entities=entities,
        ocr_blocks=ocr_blocks,
        warnings=warnings,
        stats=stats,
    )


def redact(
    detection: DetectionResult,
    output_dir: str | Path = "outputs",
    progress: ProgressFn = _noop,
) -> RedactionResult:
    output_dir = Path(output_dir)
    n_sel = sum(1 for e in detection.entities if e.selected)
    progress(f"✂️ 开始脱敏：{n_sel} 个选中实体…")

    out_paths, warnings = document_io.write_redacted(
        detection.file_path,
        detection.text,
        detection.entities,
        output_dir,
        detection.ocr_blocks,
    )
    for p in out_paths:
        progress(f"   写出 {p}")

    progress("🔁 复检（validation）…")
    redacted_text = redact_text(detection.text, detection.entities)
    passed, checks = validate_redaction(redacted_text, detection.entities)
    for c in checks:
        mark = "✅" if c["passed"] else "⚠️"
        progress(f"   {mark} {c['check']}" + (f" — {c['detail']}" if c["detail"] else ""))

    result = RedactionResult(
        input_file=detection.file_path,
        output_files=[str(p) for p in out_paths],
        validation_passed=passed,
        validation_details=checks,
        warnings=warnings,
    )

    progress("🧾 生成报告…")
    json_path, md_path = write_reports(detection, result, output_dir)
    result.report_file = str(json_path)
    result.output_files += [str(json_path), str(md_path)]
    progress(f"   报告: {json_path}")
    progress(
        "🏁 完成。复检 " + ("通过 ✅" if passed else "未通过 ⚠️，请回到 Review 调整实体后重试")
    )
    return result


def run_pipeline(
    file_path: str | Path,
    output_dir: str | Path = "outputs",
    use_claude: bool = True,
    strict: bool = False,
    ocr_provider: Optional[str] = None,
    progress: ProgressFn = _noop,
) -> tuple[DetectionResult, RedactionResult]:
    """One-shot detect+redact (CLI path; UI inserts a human review step between)."""
    detection = detect(
        file_path,
        use_claude=use_claude,
        strict=strict,
        ocr_provider=ocr_provider,
        progress=progress,
    )
    redaction = redact(detection, output_dir, progress=progress)
    return detection, redaction
