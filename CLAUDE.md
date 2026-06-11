# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

You should develop this project adhered to the protocal of claude agent sdk(https://code.claude.com/docs/en/agent-sdk/). 

## Project Overview

**DPO Agent - Document Redaction Tool**: A document redaction agent that detects and masks sensitive information (customer names, contacts, phone/email, addresses, bank accounts, contract parties) from office documents before they are sent to general-purpose LLMs.

The full specification is in `agent.md` at the repo root. This file distills the essential development commands and architecture.

## Development Principles

- **Framework**: Claude Agent SDK is the primary development framework.
- **Skills are core**: Do not hand-write complex docx/pptx/pdf parsers. Use the skills in `.claude/skills/`.
- **No OpenAI-compatible**: Model calls use Anthropic SDK / Claude Agent SDK. Env vars: `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL`. Never use `OPENAI_API_KEY` or OpenAI SDK.
- **Vibe coding + loop**: Plan → Implement → Run → Inspect → Fix → Repeat. Ship working code fast, then iterate.
- **Detect → Review → Redact → Validate → Export**: This is the core product loop.
- **Don't over-engineer**: Three-day demo target. Avoid microservices, databases, auth systems, complex deployment.

## Commands

```bash
# Install (after pyproject.toml exists)
pip install -e .

# Start Gradio UI
dpo-redact ui
# or
python -m dpo_agent.app

# CLI detect
dpo-redact detect input.pdf --output outputs/

# CLI redact with OCR + Claude
dpo-redact redact input.docx --ocr-provider glm_ocr --use-claude --output outputs/

# CLI strict mode
dpo-redact redact input.docx --strict --output outputs/

# Run Claude Agent SDK entry point
python -m dpo_agent.agent_runner

# Run tests
pytest tests/ -v
pytest tests/test_detectors.py -v
```

## Docker

最终交付需支持 Docker 封装，提供 `docker-compose.yml` 一键启动：

```bash
# 构建并启动 Gradio UI（默认端口 7860）
docker compose up -d

# 查看日志
docker compose logs -f

# 停止
docker compose down
```

容器要求：
- `ANTHROPIC_API_KEY`、`ZHIPU_API_KEY` 等敏感信息通过 `.env` 传入，不写入镜像
- `outputs/`、`examples/`、`.claude/skills/` 以 volume 挂载，方便调试
- 不做复杂多服务编排，单容器即可

## Architecture

### Planned Project Structure (from agent.md)

```
src/dpo_agent/
  cli.py              # CLI entry point (click/argparse)
  app.py              # Gradio UI
  agent_runner.py     # Claude Agent SDK entry point
  pipeline.py         # Orchestrates detect→review→redact→validate→export
  schemas.py          # Pydantic models: Entity, OCRBlock, DetectionResult, RedactionResult
  detectors.py        # Regex + keyword detectors
  claude_detect.py    # Claude-based semantic detector (Anthropic API/Agent SDK)
  redactors.py        # Text placeholder replacement + image black-box redaction
  report.py           # Generates report.json + report.md
  document_io.py      # File type dispatch, reads/writes per format
  ocr/
    base.py           # OCRProvider abstract class
    glm_ocr.py        # GLM OCR API integration (env: ZHIPU_API_KEY)
    mock_ocr.py       # Mock OCR for testing
  tools/
    ocr_tool.py       # OCR as Claude Agent SDK custom tool
    redaction_tool.py # Redaction as Claude Agent SDK custom tool
```

### File Type Handling

| Format | Primary Tool | Output |
|--------|-------------|--------|
| `.docx` | `docx` skill (in `.claude/skills/docx/`) | `.redacted.docx` + `.redacted.md` |
| `.pptx` | `pptx` skill (in `.claude/skills/pptx/`) | `.redacted.pptx` + `.redacted.md` |
| `.pdf` (text) | `pdf` skill → text extraction | `.redacted.txt` / `.redacted.md` |
| `.pdf` (image) | `pdf` skill → page images → OCR → black-box overlay | `.redacted.pdf` |
| `.png/.jpg/…` | OCR → black-box overlay | `.redacted.png` |

### Detection Layers (3-tier)

1. **Regex detector**: Phone numbers (CN mobile), email, landline, bank account numbers, IBAN, SWIFT
2. **Keyword/context detector**: Party A/B, client, supplier, contact person, address, bank account keywords (CN + EN)
3. **Claude detector**: Semantic detection of customer names, contract parties, address+entity combos, entity+bank combos. Returns JSON with entity_type, risk_level, reason. Falls back gracefully on failure.

### Redaction Strategy

- **Text**: Placeholder replacement (`客户名称_1`, `<手机号_1>`, etc.)
- **Images**: Black rectangle overlay using OCR bbox coordinates (line-level is acceptable for demo)
- **Risk levels**: `high` / `medium` always pre-selected; `low` pre-selected only in strict mode

### Key Data Models (`schemas.py`)

- `Entity`: id, text, masked_text, entity_type, replacement, risk_level, source, bbox, page, selected
- `OCRBlock`: text, bbox, confidence, page
- `DetectionResult`: file_path, file_type, text, entities, warnings
- `RedactionResult`: input_file, output_files, report_file, validation_passed, warnings

### Gradio UI：Agent 中间过程展示

Gradio 页面必须展示 Agent 任务过程中的**中间生成结果**，让用户看到每一步在做什么，而不是黑盒等待：

1. **文件解析阶段** — 显示所用 skill 名称（如 `docx skill`）、提取的文本段落数/表格数
2. **检测阶段** — 逐层展示：
   - Regex detector 命中数量（手机号 X 个、邮箱 X 个…）
   - Keyword detector 命中数量（甲方/乙方/地址关键词 X 个…）
   - Claude detector 返回的实体数量 + 耗时
3. **候选实体表格** — 检测完成后立即展示（masked preview），用户可逐条勾选/修改/新增
4. **脱敏阶段** — 显示替换/遮盖进度（如 "正在处理第 3/10 页…"）
5. **复检阶段** — 展示 validation 结果：通过项（✅ 手机号已全部替换）、残留项（⚠️ 第 2 页仍有 1 个未替换邮箱）
6. **导出阶段** — 列出所有输出文件路径

UI 组件建议：
- `gr.Textbox`（日志流，实时追加）
- `gr.Dataframe`（候选实体表格）
- `gr.Markdown`（阶段摘要）
- `gr.File`（结果下载）

### Loop Agent Flow

```
Upload file → Detect → Show candidate entities → User confirms (toggle/edit) → Redact → Validate
  ↑                                                                                              |
  └──────────────────────── If validation fails, loop back to Review ────────────────────────────┘
```

Validation checks at minimum: phone numbers, emails, bank accounts, address keywords, unreplaced entities after Party A/B markers. If validation fails, `validation_passed = false` and user is prompted to adjust.

### Env Vars

```bash
ANTHROPIC_API_KEY=          # Required for Claude detector
ANTHROPIC_BASE_URL=         # Optional: custom gateway
ANTHROPIC_MODEL=            # Optional: model selection
ZHIPU_API_KEY=              # Required for GLM OCR
GLM_OCR_ENDPOINT=           # Optional: custom OCR endpoint
```

Never hardcode keys. Never commit `.env`. `.env.example` should list all vars without values.

### Skills Directory

Skills live in `.claude/skills/` — six skills: `docx`, `pptx`, `pdf`, `dpo-redaction`, `dpo-ocr`, `dpo-review`. The three document skills handle format-specific read/write. The three DPO skills encode redaction rules, OCR strategy, and review workflow for the agent.

### Day 1 Checkpoint

After initial setup: `dpo-redact ui` starts Gradio, upload a sample file, see detected entities, generate redacted output, get report.json.
