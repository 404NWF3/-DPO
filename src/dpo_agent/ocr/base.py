"""OCR provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..schemas import OCRBlock


class OCRProvider(ABC):
    name: str = "base"

    @abstractmethod
    def recognize(self, image_path: str | Path, page: int = 0) -> list[OCRBlock]:
        """Run OCR on one image, returning line-level blocks with bboxes."""

    def available(self) -> bool:
        return True


def get_provider(name: str) -> OCRProvider:
    from .glm_ocr import GLMOCRProvider
    from .mock_ocr import MockOCRProvider

    providers = {"glm_ocr": GLMOCRProvider, "mock": MockOCRProvider}
    if name not in providers:
        raise ValueError(f"未知 OCR provider: {name}，可选: {', '.join(providers)}")
    return providers[name]()
