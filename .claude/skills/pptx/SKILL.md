---
name: pptx
description: 读取与回写 .pptx 演示文稿（文本框、表格、备注），用于 DPO 脱敏管线。需要解析或生成 PowerPoint 时使用。
---

# pptx skill

## 读取

用 `python-pptx` 遍历每页所有 shape 的 text_frame；表格 shape（`shape.has_table`）和演讲者备注（`slide.notes_slide`）也常含联系人/客户名：

```python
from pptx import Presentation
prs = Presentation(path)
for slide in prs.slides:
    for shape in slide.shapes:
        if shape.has_text_frame:
            text = shape.text_frame.text
```

报告：幻灯片数、文本框数。

## 回写（脱敏替换）

逐 run 替换，跨 run 命中时折叠段落到第一个 run。输出 `.redacted.pptx` 与 `.redacted.md`。

项目内实现见 `src/dpo_agent/document_io.py` 的 `_write_pptx`，优先复用。
