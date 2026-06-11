---
name: pdf
description: 解析 PDF —— 文本型 PDF 直接抽取文字，扫描型 PDF 转页面图片走 OCR + 黑框遮盖。处理 PDF 输入时使用。
---

# pdf skill

## 第一步：判断 PDF 类型

```python
from pypdf import PdfReader
reader = PdfReader(path)
text = "\n".join(page.extract_text() or "" for page in reader.pages)
```

- 提取文本量正常 → **文本型**：对 text 走标准检测/替换，输出 `.redacted.md`（或 `.redacted.txt`）。
- 提取文本 < 20 字符 → **扫描型**：走图片路径。

## 扫描型路径

1. 每页渲染成 PNG（可用 `pypdf` 提取内嵌图片，或提示用户安装 `pymupdf` 提升渲染质量）；
2. 调用 dpo-ocr skill / `ocr_image` 工具拿到行级文本 + bbox；
3. 对 OCR 文本跑三层检测；
4. 命中行的 bbox 画黑色矩形（行级遮盖即可），重组输出 `.redacted.pdf` 或逐页 `.redacted.png`。

注意：扫描件没有 OCR provider 时（无 ZHIPU_API_KEY），明确警告用户，不要静默输出未脱敏内容。
