"""GLM OCR provider tests (HTTP mocked, no network)."""

import json

import pytest

from dpo_agent.ocr.glm_ocr import GLMOCRProvider


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


FILES_OCR_PAYLOAD = {
    "task_id": "t1",
    "message": "成功",
    "status": "succeeded",
    "words_result_num": 2,
    "words_result": [
        {
            "location": {"left": 79, "top": 122, "width": 1483, "height": 182},
            "words": "联系人：陈建国 13812345678",
            "probability": {"average": 0.93, "variance": 0.01, "min": 0.8},
        },
        {
            "location": {"left": 80, "top": 320, "width": 1200, "height": 150},
            "words": "地址：北京市朝阳区望京东路8号",
        },
    ],
}


@pytest.fixture
def provider(monkeypatch, tmp_path):
    monkeypatch.setenv("ZHIPU_API_KEY", "test-key")
    monkeypatch.setenv(
        "GLM_OCR_ENDPOINT", "https://open.bigmodel.cn/api/paas/v4/files/ocr"
    )
    img = tmp_path / "scan.png"
    img.write_bytes(b"\x89PNG fake")
    return GLMOCRProvider(), img


def test_files_ocr_multipart_request(provider, monkeypatch):
    glm, img = provider
    captured = {}

    def fake_post(url, headers=None, files=None, data=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, files=files, data=data, json=json)
        return FakeResponse(FILES_OCR_PAYLOAD)

    monkeypatch.setattr("dpo_agent.ocr.glm_ocr.requests.post", fake_post)
    blocks = glm.recognize(img)

    # must be a multipart upload, not a JSON body
    assert captured["json"] is None
    assert "file" in captured["files"]
    assert captured["data"]["tool_type"]
    assert captured["headers"]["Authorization"] == "Bearer test-key"

    assert len(blocks) == 2
    assert blocks[0].text == "联系人：陈建国 13812345678"
    assert blocks[0].bbox == [79.0, 122.0, 79.0 + 1483.0, 122.0 + 182.0]
    assert blocks[0].confidence == pytest.approx(0.93)
    assert blocks[1].confidence == 1.0  # probability omitted


def test_files_ocr_error_payload(provider, monkeypatch):
    glm, img = provider
    monkeypatch.setattr(
        "dpo_agent.ocr.glm_ocr.requests.post",
        lambda *a, **k: FakeResponse(
            {"msg": "Current request is not a multipart request", "code": 500}, 200
        ),
    )
    with pytest.raises(RuntimeError):
        glm.recognize(img)


def test_files_ocr_failed_status(provider, monkeypatch):
    glm, img = provider
    monkeypatch.setattr(
        "dpo_agent.ocr.glm_ocr.requests.post",
        lambda *a, **k: FakeResponse({"status": "failed", "message": "bad image"}),
    )
    with pytest.raises(RuntimeError, match="bad image"):
        glm.recognize(img)


def test_layout_parsing_json_request(provider, monkeypatch):
    glm, img = provider
    glm.endpoint = "https://open.bigmodel.cn/api/paas/v4/layout_parsing"
    captured = {}

    def fake_post(url, headers=None, files=None, data=None, json=None, timeout=None):
        captured.update(json=json, files=files)
        return FakeResponse({"md_content": "联系人：陈建国\n电话：13812345678"})

    monkeypatch.setattr("dpo_agent.ocr.glm_ocr.requests.post", fake_post)
    blocks = glm.recognize(img)

    assert captured["files"] is None
    assert captured["json"]["model"] == "glm-ocr"
    assert captured["json"]["file"].startswith("data:image/png;base64,")
    assert [b.text for b in blocks] == ["联系人：陈建国", "电话：13812345678"]
