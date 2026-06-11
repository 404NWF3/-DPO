"""End-to-end pipeline tests (txt + docx, no network)."""

import json
from pathlib import Path

import pytest

from dpo_agent.pipeline import run_pipeline

SAMPLE = """服务合同
甲方：北京示例科技有限公司
乙方：上海某某贸易有限公司
联系人：王五
地址：上海市浦东新区世纪大道100号
电话：13800138000
邮箱：wangwu@example.com
银行账号：6222020200001234567
"""


@pytest.fixture
def sample_txt(tmp_path: Path) -> Path:
    f = tmp_path / "contract.txt"
    f.write_text(SAMPLE, encoding="utf-8")
    return f


def test_txt_end_to_end(sample_txt: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    detection, redaction = run_pipeline(sample_txt, output_dir=out_dir, use_claude=False)

    assert detection.entities, "should detect entities"
    assert redaction.validation_passed, redaction.validation_details

    redacted = (out_dir / "contract.redacted.txt").read_text(encoding="utf-8")
    assert "13800138000" not in redacted
    assert "wangwu@example.com" not in redacted
    assert "北京示例科技有限公司" not in redacted

    report = json.loads((out_dir / "contract.report.json").read_text(encoding="utf-8"))
    assert report["validation_passed"] is True
    # report must not leak raw entity text
    raw = json.dumps(report, ensure_ascii=False)
    assert "13800138000" not in raw


def test_docx_end_to_end(tmp_path: Path) -> None:
    docx = pytest.importorskip("docx")
    src = tmp_path / "contract.docx"
    doc = docx.Document()
    for line in SAMPLE.splitlines():
        doc.add_paragraph(line)
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "开户行"
    table.cell(0, 1).text = "中国银行上海分行 账号：6222020200007654321"
    doc.save(str(src))

    out_dir = tmp_path / "out"
    detection, redaction = run_pipeline(src, output_dir=out_dir, use_claude=False)
    assert redaction.validation_passed, redaction.validation_details

    out_doc = docx.Document(str(out_dir / "contract.redacted.docx"))
    full = "\n".join(p.text for p in out_doc.paragraphs)
    for t in out_doc.tables:
        for row in t.rows:
            for cell in row.cells:
                full += "\n" + cell.text
    assert "13800138000" not in full
    assert "6222020200007654321" not in full
    assert "北京示例科技有限公司" not in full


def test_image_mock_ocr(tmp_path: Path) -> None:
    PIL = pytest.importorskip("PIL")
    from PIL import Image

    img_path = tmp_path / "scan.png"
    Image.new("RGB", (500, 100), "white").save(img_path)
    sidecar = [
        {"text": "联系人：赵六 13600136000", "bbox": [10, 10, 480, 40], "confidence": 0.98}
    ]
    (tmp_path / "scan.png.ocr.json").write_text(
        json.dumps(sidecar, ensure_ascii=False), encoding="utf-8"
    )

    out_dir = tmp_path / "out"
    detection, redaction = run_pipeline(
        img_path, output_dir=out_dir, use_claude=False, ocr_provider="mock"
    )
    assert (out_dir / "scan.redacted.png").exists()
    assert any(e.entity_type == "手机号" for e in detection.entities)
    # the phone entity must carry a bbox from the OCR block
    phone = next(e for e in detection.entities if e.entity_type == "手机号")
    assert phone.bbox == [10, 10, 480, 40]
