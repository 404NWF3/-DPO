"""Tests for the regex + keyword detection layers."""

from dpo_agent.detectors import (
    apply_strict_mode,
    detect_keyword,
    detect_regex,
    merge_entities,
)

SAMPLE = """合同编号：HT-2026-001
甲方：北京示例科技有限公司
乙方：上海某某贸易有限公司（盖章）
联系人：张三
地址：北京市海淀区中关村大街1号
联系电话：13800138000，座机 010-12345678
邮箱：zhangsan@example.com
开户银行：中国银行北京分行
银行账号：6222 0202 0000 1234 567
SWIFT: BKCHCNBJ
"""


def test_regex_phone():
    ents = detect_regex(SAMPLE)
    phones = [e for e in ents if e.entity_type == "手机号"]
    assert len(phones) == 1
    assert phones[0].text == "13800138000"
    assert phones[0].risk_level == "high"


def test_regex_email():
    ents = detect_regex(SAMPLE)
    emails = [e for e in ents if e.entity_type == "邮箱"]
    assert [e.text for e in emails] == ["zhangsan@example.com"]


def test_regex_landline():
    ents = detect_regex(SAMPLE)
    assert any(e.entity_type == "座机" and "010" in e.text for e in ents)


def test_regex_bank_account_with_spaces():
    ents = detect_regex(SAMPLE)
    banks = [e for e in ents if e.entity_type == "银行账号"]
    assert any("6222" in e.text for e in banks)


def test_regex_swift():
    ents = detect_regex(SAMPLE)
    assert any(e.entity_type == "SWIFT" and e.text == "BKCHCNBJ" for e in ents)


def test_keyword_parties():
    ents = detect_keyword(SAMPLE)
    parties = [e for e in ents if e.entity_type == "合同方"]
    texts = [e.text for e in parties]
    assert "北京示例科技有限公司" in texts
    assert any("上海某某贸易有限公司" in t for t in texts)


def test_keyword_contact_and_address():
    ents = detect_keyword(SAMPLE)
    assert any(e.entity_type == "联系人" and e.text == "张三" for e in ents)
    assert any(e.entity_type == "地址" and "海淀区" in e.text for e in ents)


def test_merge_dedup_and_numbering():
    ents = merge_entities(detect_regex(SAMPLE), detect_keyword(SAMPLE))
    texts = [e.text for e in ents]
    assert len(texts) == len(set(texts)), "merge must dedup by text"
    ids = [e.id for e in ents]
    assert len(ids) == len(set(ids))
    for e in ents:
        assert e.replacement.startswith("<") and e.replacement.endswith(">")


def test_strict_mode_selection():
    ents = merge_entities(detect_regex(SAMPLE), detect_keyword(SAMPLE))
    apply_strict_mode(ents, strict=False)
    assert all(e.selected for e in ents if e.risk_level in ("high", "medium"))
    apply_strict_mode(ents, strict=True)
    assert all(e.selected for e in ents)


def test_masked_preview_never_full_text():
    ents = merge_entities(detect_regex(SAMPLE), detect_keyword(SAMPLE))
    for e in ents:
        if len(e.text) > 5:
            assert e.masked_text != e.text
            assert "*" in e.masked_text
