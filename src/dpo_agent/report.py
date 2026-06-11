"""Generate report.json + report.md describing one redaction run."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .schemas import DetectionResult, Entity, RedactionResult


def write_reports(
    detection: DetectionResult,
    redaction: RedactionResult,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(detection.file_path).stem

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_file": detection.file_path,
        "file_type": detection.file_type,
        "stats": detection.stats,
        "entities": [
            {
                "id": e.id,
                "masked_text": e.masked_text,
                "entity_type": e.entity_type,
                "replacement": e.replacement,
                "risk_level": e.risk_level,
                "source": e.source,
                "reason": e.reason,
                "selected": e.selected,
                "page": e.page,
            }
            for e in detection.entities
        ],
        "output_files": redaction.output_files,
        "validation_passed": redaction.validation_passed,
        "validation_details": redaction.validation_details,
        "warnings": detection.warnings + redaction.warnings,
    }

    json_path = output_dir / f"{stem}.report.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_path = output_dir / f"{stem}.report.md"
    md_path.write_text(_render_md(payload, detection.entities), encoding="utf-8")
    return json_path, md_path


def _render_md(payload: dict, entities: list[Entity]) -> str:
    lines = [
        f"# 脱敏报告 — {Path(payload['input_file']).name}",
        "",
        f"- 生成时间: {payload['generated_at']}",
        f"- 文件类型: {payload['file_type']}",
        f"- 复检结果: {'✅ 通过' if payload['validation_passed'] else '⚠️ 未通过'}",
        "",
        "## 检测统计",
        "",
    ]
    for k, v in payload.get("stats", {}).items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 实体清单（脱敏预览）", "", "| ID | 类型 | 原文(掩码) | 替换为 | 风险 | 来源 | 选中 |", "|---|---|---|---|---|---|---|"]
    for e in entities:
        lines.append(
            f"| {e.id} | {e.entity_type} | {e.masked_text} | `{e.replacement}` | {e.risk_level} | {e.source} | {'✔' if e.selected else ''} |"
        )
    lines += ["", "## 复检明细", ""]
    for c in payload.get("validation_details", []):
        mark = "✅" if c["passed"] else "⚠️"
        detail = f" — {c['detail']}" if c.get("detail") else ""
        lines.append(f"- {mark} {c['check']}{detail}")
    if payload.get("warnings"):
        lines += ["", "## 警告", ""]
        lines += [f"- {w}" for w in payload["warnings"]]
    lines += ["", "## 输出文件", ""]
    lines += [f"- `{f}`" for f in payload.get("output_files", [])]
    return "\n".join(lines) + "\n"
