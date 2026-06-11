"""Layer 1 (regex) and layer 2 (keyword/context) detectors.

Both layers are pure-Python and work offline; layer 3 (Claude) lives in
claude_detect.py and is optional.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .schemas import Entity, RiskLevel

# ---------------------------------------------------------------------------
# Layer 1: regex detectors
# ---------------------------------------------------------------------------


@dataclass
class RegexRule:
    entity_type: str
    pattern: re.Pattern
    risk_level: RiskLevel
    group: int = 0


REGEX_RULES: list[RegexRule] = [
    RegexRule("手机号", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "high"),
    RegexRule(
        "邮箱",
        re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        "high",
    ),
    RegexRule(
        "座机",
        re.compile(r"(?<![\d-])0\d{2,3}[- ]\d{7,8}(?:[- ]\d{1,5})?(?![\d-])"),
        "medium",
    ),
    # 16-19 digit card/account numbers, allowing space/dash groups of 4
    RegexRule(
        "银行账号",
        re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)"),
        "high",
    ),
    RegexRule(
        "IBAN",
        re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
        "high",
    ),
    RegexRule(
        "SWIFT",
        re.compile(r"\b[A-Z]{4}(?:CN|US|GB|HK|SG|JP|DE|FR|AU|CA)[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b"),
        "high",
    ),
]


def detect_regex(text: str) -> list[Entity]:
    entities: list[Entity] = []
    taken: list[tuple[int, int]] = []  # spans already claimed, earlier rules win
    for rule in REGEX_RULES:
        for m in rule.pattern.finditer(text):
            span = m.span(rule.group)
            if any(s < span[1] and span[0] < e for s, e in taken):
                continue
            taken.append(span)
            entities.append(
                Entity(
                    id="",
                    text=m.group(rule.group),
                    entity_type=rule.entity_type,
                    replacement="",
                    risk_level=rule.risk_level,
                    source="regex",
                    reason=f"regex:{rule.entity_type}",
                )
            )
    return entities


# ---------------------------------------------------------------------------
# Layer 2: keyword/context detectors
# ---------------------------------------------------------------------------

# value = run of chars after the keyword separator, stopping at punctuation/newline
_CN_VALUE = r"([^\s，。;；、：:）)】\n]{2,40}(?:[（(][^）)]{1,20}[）)])?)"
_SEP = r"\s*[:：]\s*"


@dataclass
class KeywordRule:
    entity_type: str
    pattern: re.Pattern
    risk_level: RiskLevel
    group: int = 1


KEYWORD_RULES: list[KeywordRule] = [
    KeywordRule(
        "合同方",
        re.compile(r"(?:甲方|乙方|丙方|丁方)(?:（[^）]{0,20}）)?" + _SEP + _CN_VALUE),
        "high",
    ),
    KeywordRule(
        "合同方",
        re.compile(r"(?:Party\s+[AB]|Client|Supplier|Vendor)" + _SEP + r"([^\n,;]{2,60})", re.I),
        "high",
    ),
    KeywordRule(
        "客户名称",
        re.compile(r"(?:客户名称|客户单位|委托方|受托方|客户)" + _SEP + _CN_VALUE),
        "high",
    ),
    KeywordRule(
        "供应商",
        re.compile(r"(?:供应商|供货方|服务方|承包方)" + _SEP + _CN_VALUE),
        "high",
    ),
    KeywordRule(
        "联系人",
        re.compile(r"(?:联系人|经办人|负责人|代表人|法定代表人)" + _SEP + _CN_VALUE),
        "medium",
    ),
    KeywordRule(
        "联系人",
        re.compile(r"(?:Contact(?:\s+Person)?|Attn)" + _SEP + r"([^\n,;]{2,40})", re.I),
        "medium",
    ),
    KeywordRule(
        "地址",
        re.compile(
            r"(?:注册地址|办公地址|联系地址|住所地|住所|地址|Address)"
            + _SEP
            + r"([^\n，。;；]{4,60})",
            re.I,
        ),
        "medium",
    ),
    KeywordRule(
        "开户行",
        re.compile(r"(?:开户银行|开户行|Bank\s*Name)" + _SEP + r"([^\n，。;；,]{4,40})", re.I),
        "medium",
    ),
    KeywordRule(
        "银行账号",
        re.compile(r"(?:银行账号|银行账户|账号|账户|Account\s*(?:No|Number)\.?)" + _SEP + r"([0-9][0-9 -]{7,28}[0-9])", re.I),
        "high",
    ),
]


def detect_keyword(text: str) -> list[Entity]:
    entities: list[Entity] = []
    for rule in KEYWORD_RULES:
        for m in rule.pattern.finditer(text):
            value = m.group(rule.group).strip()
            if not value:
                continue
            entities.append(
                Entity(
                    id="",
                    text=value,
                    entity_type=rule.entity_type,
                    replacement="",
                    risk_level=rule.risk_level,
                    source="keyword",
                    reason=f"keyword:{m.group(0)[:20]}",
                )
            )
    return entities


# ---------------------------------------------------------------------------
# Merge / dedup / numbering
# ---------------------------------------------------------------------------


def merge_entities(*entity_lists: list[Entity]) -> list[Entity]:
    """Dedup by exact text (first source wins), then assign ids/replacements.

    Same text always maps to the same replacement so redaction is consistent.
    """
    merged: list[Entity] = []
    seen: dict[str, Entity] = {}
    counters: dict[str, int] = {}
    for entities in entity_lists:
        for ent in entities:
            key = ent.text.strip()
            if not key:
                continue
            if key in seen:
                # keep the higher risk level if a later layer escalates it
                order = {"high": 0, "medium": 1, "low": 2}
                if order[ent.risk_level] < order[seen[key].risk_level]:
                    seen[key].risk_level = ent.risk_level
                continue
            counters[ent.entity_type] = counters.get(ent.entity_type, 0) + 1
            n = counters[ent.entity_type]
            ent.id = f"{ent.entity_type}_{n}"
            ent.replacement = f"<{ent.entity_type}_{n}>"
            seen[key] = ent
            merged.append(ent)
    return merged


def apply_strict_mode(entities: list[Entity], strict: bool) -> list[Entity]:
    """high/medium are always pre-selected; low only in strict mode."""
    for ent in entities:
        ent.selected = ent.risk_level in ("high", "medium") or strict
    return entities
