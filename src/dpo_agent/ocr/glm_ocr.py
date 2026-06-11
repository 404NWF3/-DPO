"""GLM OCR API integration (Zhipu). Requires ZHIPU_API_KEY.

Two official endpoints are supported, selected by GLM_OCR_ENDPOINT:

1. OCR 服务 (default): POST https://open.bigmodel.cn/api/paas/v4/files/ocr
   multipart/form-data (file + tool_type + language_type + probability),
   returns words_result[] with per-line text + location bbox — ideal for
   black-box image redaction.
2. layout_parsing: POST https://open.bigmodel.cn/api/paas/v4/layout_parsing
   JSON {"model": "glm-ocr", "file": "<url or base64 data-uri>"}, returns
   document content (markdown/blocks); bbox availability depends on response.

Any failure raises RuntimeError so callers can fall back/warn.
"""

from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path

import requests

from ..schemas import OCRBlock
from .base import OCRProvider

DEFAULT_ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/files/ocr"


class GLMOCRProvider(OCRProvider):
    name = "glm_ocr"

    def __init__(self) -> None:
        self.api_key = os.environ.get("ZHIPU_API_KEY", "")
        self.endpoint = os.environ.get("GLM_OCR_ENDPOINT", DEFAULT_ENDPOINT)
        self.tool_type = os.environ.get("GLM_OCR_TOOL_TYPE", "hand_write")
        self.language_type = os.environ.get("GLM_OCR_LANGUAGE", "CHN_ENG")
        self.model = os.environ.get("GLM_OCR_MODEL", "glm-ocr")

    def available(self) -> bool:
        return bool(self.api_key)

    def recognize(self, image_path: str | Path, page: int = 0) -> list[OCRBlock]:
        if not self.available():
            raise RuntimeError("ZHIPU_API_KEY 未配置，无法使用 GLM OCR")
        if "layout_parsing" in self.endpoint:
            return self._recognize_layout_parsing(image_path, page)
        return self._recognize_files_ocr(image_path, page)

    # ------------------------------------------------------------------
    # files/ocr: multipart upload, line-level words_result with bboxes
    # ------------------------------------------------------------------

    def _recognize_files_ocr(self, image_path: str | Path, page: int) -> list[OCRBlock]:
        image_path = Path(image_path)
        with image_path.open("rb") as f:
            resp = requests.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"file": (image_path.name, f)},
                data={
                    "tool_type": self.tool_type,
                    "language_type": self.language_type,
                    "probability": "true",
                },
                timeout=120,
            )
        payload = self._payload_or_raise(resp)
        status = payload.get("status")
        if status and status != "succeeded":
            raise RuntimeError(
                f"GLM OCR 任务失败: status={status}, message={payload.get('message')}"
            )

        blocks: list[OCRBlock] = []
        for item in payload.get("words_result", []):
            words = (item.get("words") or "").strip()
            loc = item.get("location") or {}
            if not words:
                continue
            bbox = self._location_to_bbox(loc)
            prob = item.get("probability")
            conf = float(prob.get("average", 1.0)) if isinstance(prob, dict) else 1.0
            blocks.append(
                OCRBlock(text=words, bbox=bbox, confidence=conf, page=page)
            )
        if not blocks:
            raise RuntimeError(
                f"GLM OCR (files/ocr) 未识别出文本: {str(payload)[:200]}"
            )
        return blocks

    # ------------------------------------------------------------------
    # layout_parsing: JSON request with base64 data-uri
    # ------------------------------------------------------------------

    def _recognize_layout_parsing(self, image_path: str | Path, page: int) -> list[OCRBlock]:
        image_path = Path(image_path)
        mime = mimetypes.guess_type(image_path.name)[0] or "image/png"
        data_uri = (
            f"data:{mime};base64,"
            + base64.b64encode(image_path.read_bytes()).decode()
        )
        resp = requests.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "file": data_uri},
            timeout=120,
        )
        payload = self._payload_or_raise(resp)

        blocks: list[OCRBlock] = []
        for item in self._iter_lines(payload):
            text = (item.get("text") or item.get("content") or "").strip()
            bbox = item.get("bbox") or item.get("box")
            if not text or not bbox:
                continue
            blocks.append(
                OCRBlock(
                    text=text,
                    bbox=self._norm_bbox(bbox),
                    confidence=float(item.get("confidence", 1.0)),
                    page=page,
                )
            )
        if blocks:
            return blocks
        # bbox-less fallback: markdown content split into lines (text redaction
        # still works; image black-box needs the files/ocr endpoint instead)
        md = self._extract_md(payload)
        if md:
            return [
                OCRBlock(text=line.strip(), bbox=[0, 0, 0, 0], confidence=1.0, page=page)
                for line in md.splitlines()
                if line.strip()
            ]
        raise RuntimeError(
            f"GLM OCR (layout_parsing) 返回结果无法解析: {str(payload)[:200]}"
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _payload_or_raise(resp: requests.Response) -> dict:
        try:
            payload = resp.json()
        except ValueError:
            resp.raise_for_status()
            raise RuntimeError(f"GLM OCR 返回非 JSON: {resp.text[:200]}")
        if resp.status_code >= 400 or "error" in payload:
            err = payload.get("error") or payload
            raise RuntimeError(
                f"GLM OCR 调用失败 (HTTP {resp.status_code}): "
                f"{err.get('message') or err.get('msg') or str(err)[:200]}"
            )
        return payload

    @staticmethod
    def _location_to_bbox(loc: dict) -> list[float]:
        left = float(loc.get("left", 0))
        top = float(loc.get("top", 0))
        return [left, top, left + float(loc.get("width", 0)), top + float(loc.get("height", 0))]

    @staticmethod
    def _iter_lines(payload: dict):
        # tolerate a few likely response shapes
        for key in ("lines", "blocks", "results", "words_result"):
            if isinstance(payload.get(key), list):
                yield from payload[key]
                return
        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("lines", "blocks", "results"):
                if isinstance(data.get(key), list):
                    yield from data[key]
                    return
        if isinstance(data, list):
            yield from data

    @staticmethod
    def _extract_md(payload: dict) -> str:
        for container in (payload, payload.get("data") or {}):
            if not isinstance(container, dict):
                continue
            for key in ("md_content", "content", "markdown", "text"):
                value = container.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            choices = container.get("choices")
            if isinstance(choices, list) and choices:
                msg = (choices[0] or {}).get("message") or {}
                if isinstance(msg.get("content"), str):
                    return msg["content"]
        return ""

    @staticmethod
    def _norm_bbox(bbox) -> list[float]:
        # [x0,y0,x1,y1] or [[x,y]*4] polygon
        if bbox and isinstance(bbox[0], (list, tuple)):
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            return [min(xs), min(ys), max(xs), max(ys)]
        return [float(v) for v in bbox]
