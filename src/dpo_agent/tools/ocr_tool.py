"""OCR exposed as a Claude Agent SDK custom tool."""

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
    "ocr_image",
    "对图片或扫描页运行 OCR，返回行级文本块及其 bbox 坐标（JSON）。",
    {"image_path": str, "provider": str},
)
async def ocr_image(args: dict) -> dict:
    from ..ocr import get_provider

    provider = get_provider(args.get("provider") or "mock")
    blocks = provider.recognize(args["image_path"])
    payload = [b.model_dump() for b in blocks]
    return {
        "content": [
            {"type": "text", "text": json.dumps(payload, ensure_ascii=False)}
        ]
    }
