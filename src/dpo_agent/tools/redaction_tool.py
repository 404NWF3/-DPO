"""Detection + redaction exposed as Claude Agent SDK custom tools."""

from __future__ import annotations

import json

try:
    from claude_agent_sdk import tool
except ImportError:  # SDK optional: pip install dpo-agent[agent]
    def tool(name, description, schema):  # type: ignore
        def deco(fn):
            fn._tool_meta = (name, description, schema)
            return fn
        return deco


@tool(
    "detect_entities",
    "对文档运行三层敏感信息检测（regex + 关键词 + 可选 Claude），返回候选实体 JSON。",
    {"file_path": str, "strict": bool},
)
async def detect_entities(args: dict) -> dict:
    from ..pipeline import detect

    result = detect(
        args["file_path"],
        use_claude=False,  # the calling agent itself does semantic review
        strict=bool(args.get("strict", False)),
    )
    payload = {
        "file_type": result.file_type,
        "stats": result.stats,
        "warnings": result.warnings,
        "entities": [e.model_dump() for e in result.entities],
    }
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]
    }


@tool(
    "redact_document",
    "按候选实体清单对文档执行脱敏（占位符替换/图片遮盖），输出脱敏文件与报告，返回结果 JSON。",
    {"file_path": str, "entities_json": str, "output_dir": str},
)
async def redact_document(args: dict) -> dict:
    from ..pipeline import detect, redact
    from ..schemas import Entity

    detection = detect(args["file_path"], use_claude=False)
    if args.get("entities_json"):
        items = json.loads(args["entities_json"])
        detection.entities = [Entity(**i) for i in items]
    result = redact(detection, args.get("output_dir") or "outputs")
    return {
        "content": [
            {"type": "text", "text": result.model_dump_json()}
        ]
    }
