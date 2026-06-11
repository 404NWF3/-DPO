"""Layer 3: Claude-based semantic detector.

Uses the Anthropic SDK directly (never OpenAI). Requires ANTHROPIC_API_KEY;
without it (or on any API failure) the layer degrades gracefully to an empty
result plus a warning, so the regex/keyword layers still carry the pipeline.
"""

from __future__ import annotations

import json
import os
import re
import time

from .schemas import Entity

SYSTEM_PROMPT = """\
你是一个文档脱敏助手。从用户提供的文档文本中找出敏感实体，仅返回 JSON 数组，不要任何其他文字。
需要识别的类型：客户名称、合同方（甲方/乙方等指代的公司或个人全称）、联系人姓名、地址（能定位到具体单位/个人的）、银行账号/开户行组合、手机号、邮箱。
每个元素格式：
{"text": "原文中出现的精确字符串", "entity_type": "客户名称|合同方|联系人|地址|开户行|银行账号|手机号|邮箱|其他敏感信息", "risk_level": "high|medium|low", "reason": "一句话说明"}
只返回文本中逐字出现的字符串；不确定的给 low。"""

_MAX_CHARS = 30000


def claude_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def detect_claude(text: str) -> tuple[list[Entity], list[str], float]:
    """Returns (entities, warnings, elapsed_seconds)."""
    warnings: list[str] = []
    if not claude_available():
        return [], ["ANTHROPIC_API_KEY 未配置，跳过 Claude 语义检测层"], 0.0

    start = time.time()
    try:
        import anthropic

        client = anthropic.Anthropic()  # picks up ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL
        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        resp = client.messages.create(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text[:_MAX_CHARS]}],
        )
        raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        items = _parse_json_array(raw)
    except Exception as exc:  # any API/parse failure must not break the pipeline
        return [], [f"Claude 检测层失败，已降级: {exc}"], time.time() - start

    entities: list[Entity] = []
    for item in items:
        ent_text = str(item.get("text", "")).strip()
        if not ent_text or ent_text not in text:
            continue
        risk = item.get("risk_level", "medium")
        if risk not in ("high", "medium", "low"):
            risk = "medium"
        entities.append(
            Entity(
                id="",
                text=ent_text,
                entity_type=str(item.get("entity_type", "其他敏感信息")),
                replacement="",
                risk_level=risk,
                source="claude",
                reason=str(item.get("reason", "")),
            )
        )
    return entities, warnings, time.time() - start


def _parse_json_array(raw: str) -> list[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.S)
        if not m:
            raise
        data = json.loads(m.group(0))
    return data if isinstance(data, list) else []
