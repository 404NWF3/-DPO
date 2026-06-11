"""Tests for redaction + validation."""

from dpo_agent.detectors import apply_strict_mode, detect_keyword, detect_regex, merge_entities
from dpo_agent.redactors import redact_text, validate_redaction

TEXT = "甲方：北京示例科技有限公司，联系人：李四，电话 13900139000，邮箱 lisi@corp.cn。"


def _entities():
    ents = merge_entities(detect_regex(TEXT), detect_keyword(TEXT))
    return apply_strict_mode(ents, strict=False)


def test_redact_replaces_all_selected():
    ents = _entities()
    out = redact_text(TEXT, ents)
    assert "13900139000" not in out
    assert "lisi@corp.cn" not in out
    assert "北京示例科技有限公司" not in out
    assert "<手机号_1>" in out
    assert "<邮箱_1>" in out


def test_same_text_same_placeholder():
    text = "电话 13900139000；再次出现 13900139000。"
    ents = merge_entities(detect_regex(text))
    apply_strict_mode(ents, strict=False)
    out = redact_text(text, ents)
    assert out.count("<手机号_1>") == 2


def test_unselected_entity_kept():
    ents = _entities()
    for e in ents:
        if e.entity_type == "联系人":
            e.selected = False
    out = redact_text(TEXT, ents)
    assert "李四" in out


def test_validation_passes_on_clean_output():
    ents = _entities()
    out = redact_text(TEXT, ents)
    passed, checks = validate_redaction(out, ents)
    assert passed, checks


def test_validation_fails_on_residual():
    ents = _entities()
    out = redact_text(TEXT, ents) + " 残留手机号 13700137000"
    passed, checks = validate_redaction(out, ents)
    assert not passed
