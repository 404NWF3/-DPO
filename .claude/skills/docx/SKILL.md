---
name: docx
description: 读取与回写 .docx 文档（段落、表格、保留格式），用于 DPO 脱敏管线。需要解析或生成 Word 文档时使用。
---

# docx skill

## 读取

用 `python-docx` 提取全部文本，段落与表格都要覆盖：

```python
import docx
doc = docx.Document(path)
paras = [p.text for p in doc.paragraphs if p.text.strip()]
for table in doc.tables:
    for row in table.rows:
        for cell in row.cells:
            paras.append(cell.text)
```

报告解析统计：段落数、表格数。页眉/页脚（`section.header/footer`）在合同类文档中常含公司名，也要检查。

## 回写（脱敏替换）

优先逐 run 替换以保留格式；当敏感串跨 run 边界时，把整段折叠到第一个 run（demo 可接受的取舍）：

```python
for run in paragraph.runs:
    run.text = replace(run.text)
if paragraph.text != expected:   # 跨 run 命中
    paragraph.runs[0].text = expected
    for r in paragraph.runs[1:]:
        r.text = ""
```

输出 `.redacted.docx` 与 `.redacted.md` 两份。项目内的实现见 `src/dpo_agent/document_io.py`，能复用就复用，不要重写解析器。
