"""Mock OCR provider for tests and offline demos.

Looks for a sidecar file `<image>.ocr.json` containing
`[{"text": ..., "bbox": [x0,y0,x1,y1], "confidence": ...}, ...]`.
Without a sidecar it returns a single fake block so the pipeline still runs.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..schemas import OCRBlock
from .base import OCRProvider


class MockOCRProvider(OCRProvider):
    name = "mock"

    def recognize(self, image_path: str | Path, page: int = 0) -> list[OCRBlock]:
        sidecar = Path(str(image_path) + ".ocr.json")
        if sidecar.exists():
            items = json.loads(sidecar.read_text(encoding="utf-8"))
            return [
                OCRBlock(
                    text=i["text"],
                    bbox=i["bbox"],
                    confidence=i.get("confidence", 1.0),
                    page=page,
                )
                for i in items
            ]
        return [
            OCRBlock(
                text="[mock ocr] 联系人：张三 电话 13800138000",
                bbox=[10, 10, 400, 40],
                confidence=0.99,
                page=page,
            )
        ]
