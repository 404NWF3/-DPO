"""Gradio UI — shows every intermediate step of the agent loop:
parse → 3-layer detect → candidate review (editable) → redact → validate → export.
"""

from __future__ import annotations

import os
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

from .detectors import merge_entities
from .pipeline import detect as pipeline_detect
from .pipeline import redact as pipeline_redact
from .schemas import DetectionResult, Entity

load_dotenv()

OUTPUT_DIR = Path(os.environ.get("DPO_OUTPUT_DIR", "outputs"))

DF_HEADERS = ["选中", "ID", "类型", "原文(掩码)", "替换为", "风险", "来源", "理由"]
ENTITY_TYPES = [
    "客户名称", "合同方", "联系人", "地址", "开户行",
    "银行账号", "手机号", "邮箱", "座机", "其他敏感信息",
]


def _entities_to_rows(entities: list[Entity]) -> list[list]:
    return [
        [e.selected, e.id, e.entity_type, e.masked_text, e.replacement,
         e.risk_level, e.source, e.reason]
        for e in entities
    ]


def _apply_rows(detection: DetectionResult, rows) -> DetectionResult:
    """Fold dataframe edits (选中 / 替换为) back into the stored entities."""
    by_id = {e.id: e for e in detection.entities}
    values = rows.values.tolist() if hasattr(rows, "values") else list(rows or [])
    for row in values:
        if len(row) < 5:
            continue
        ent = by_id.get(str(row[1]))
        if ent is None:
            continue
        ent.selected = bool(row[0]) and str(row[0]).lower() not in ("false", "0", "")
        if str(row[4]).strip():
            ent.replacement = str(row[4]).strip()
    return detection


def do_detect(file, use_claude, strict, ocr_provider):
    if file is None:
        yield "请先上传文件", gr.update(), None, gr.update()
        return
    log_lines: list[str] = []
    detection_holder: dict = {}

    def progress(msg: str) -> None:
        log_lines.append(msg)

    # run synchronously but flush progress incrementally via generator
    import threading

    done = threading.Event()
    error_holder: dict = {}

    def work():
        try:
            detection_holder["d"] = pipeline_detect(
                file, use_claude=use_claude, strict=strict,
                ocr_provider=ocr_provider or None, progress=progress,
            )
        except Exception as exc:
            error_holder["e"] = exc
        finally:
            done.set()

    threading.Thread(target=work, daemon=True).start()
    shown = 0
    while not done.wait(timeout=0.3):
        if len(log_lines) > shown:
            shown = len(log_lines)
            yield "\n".join(log_lines), gr.update(), None, gr.update()
    if "e" in error_holder:
        log_lines.append(f"❌ 检测失败: {error_holder['e']}")
        yield "\n".join(log_lines), gr.update(), None, gr.update()
        return

    detection: DetectionResult = detection_holder["d"]
    summary = _stage_summary(detection)
    yield (
        "\n".join(log_lines),
        gr.update(value=_entities_to_rows(detection.entities)),
        detection,
        summary,
    )


def _stage_summary(detection: DetectionResult) -> str:
    s = detection.stats
    lines = [
        "### 检测摘要",
        f"- 文件类型: **{detection.file_type}**",
    ]
    for k, v in s.items():
        lines.append(f"- {k}: {v}")
    if detection.warnings:
        lines.append("")
        lines += [f"- ⚠️ {w}" for w in detection.warnings]
    lines.append("")
    lines.append("👇 请在下表中勾选/修改实体，然后点击 **开始脱敏**。")
    return "\n".join(lines)


def do_add_entity(detection, new_text, new_type, rows):
    if detection is None:
        return gr.update(), detection, "请先执行检测"
    if not (new_text or "").strip():
        return gr.update(), detection, "请输入要新增的原文"
    detection = _apply_rows(detection, rows)
    extra = Entity(
        id="", text=new_text.strip(), entity_type=new_type,
        replacement="", risk_level="high", source="user", reason="用户手动添加",
    )
    detection.entities = merge_entities(detection.entities, [extra])
    return (
        gr.update(value=_entities_to_rows(detection.entities)),
        detection,
        f"已新增实体（{new_type}）",
    )


def do_redact(detection, rows):
    if detection is None:
        yield "请先执行检测", gr.update(), gr.update(), None
        return
    detection = _apply_rows(detection, rows)
    log_lines: list[str] = []

    import threading

    result_holder: dict = {}
    done = threading.Event()

    def work():
        try:
            result_holder["r"] = pipeline_redact(
                detection, OUTPUT_DIR, progress=log_lines.append
            )
        except Exception as exc:
            result_holder["e"] = exc
        finally:
            done.set()

    threading.Thread(target=work, daemon=True).start()
    shown = 0
    while not done.wait(timeout=0.3):
        if len(log_lines) > shown:
            shown = len(log_lines)
            yield "\n".join(log_lines), gr.update(), gr.update(), detection
    if "e" in result_holder:
        log_lines.append(f"❌ 脱敏失败: {result_holder['e']}")
        yield "\n".join(log_lines), gr.update(), gr.update(), detection
        return

    result = result_holder["r"]
    status = "✅ 复检通过" if result.validation_passed else "⚠️ 复检未通过 — 请在上表调整后重新脱敏"
    md = [f"### 脱敏结果 — {status}", ""]
    for c in result.validation_details:
        mark = "✅" if c["passed"] else "⚠️"
        md.append(f"- {mark} {c['check']}" + (f" — {c['detail']}" if c["detail"] else ""))
    if result.warnings:
        md += [""] + [f"- ⚠️ {w}" for w in result.warnings]
    yield (
        "\n".join(log_lines),
        "\n".join(md),
        gr.update(value=result.output_files, visible=True),
        detection,
    )


def build_app() -> gr.Blocks:
    with gr.Blocks(title="DPO Agent — 文档脱敏") as demo:
        gr.Markdown(
            "# 🛡️ DPO Agent — 文档脱敏\n"
            "Detect → Review → Redact → Validate → Export。"
            "支持 .docx / .pptx / .pdf / .txt / .md / 图片。"
        )
        detection_state = gr.State(None)

        with gr.Row():
            with gr.Column(scale=1):
                file_in = gr.File(
                    label="上传文件", type="filepath",
                    file_types=[".docx", ".pptx", ".pdf", ".txt", ".md",
                                ".png", ".jpg", ".jpeg"],
                )
                use_claude = gr.Checkbox(
                    label="启用 Claude 语义检测层（需 ANTHROPIC_API_KEY）",
                    value=bool(os.environ.get("ANTHROPIC_API_KEY")),
                )
                strict = gr.Checkbox(label="严格模式（低风险实体也默认选中）", value=False)
                ocr_provider = gr.Dropdown(
                    label="OCR provider（图片/扫描件）",
                    choices=["", "glm_ocr", "mock"], value="",
                )
                detect_btn = gr.Button("🔍 开始检测", variant="primary")
            with gr.Column(scale=2):
                log_box = gr.Textbox(
                    label="Agent 过程日志（实时）", lines=14, max_lines=24, interactive=False,
                )

        stage_md = gr.Markdown("")
        entity_df = gr.Dataframe(
            headers=DF_HEADERS,
            datatype=["bool", "str", "str", "str", "str", "str", "str", "str"],
            interactive=True,
            label="候选实体（可勾选「选中」、修改「替换为」）",
            wrap=True,
        )
        with gr.Row():
            new_text = gr.Textbox(label="新增实体原文", scale=2)
            new_type = gr.Dropdown(label="类型", choices=ENTITY_TYPES, value="其他敏感信息", scale=1)
            add_btn = gr.Button("➕ 新增", scale=1)
        add_msg = gr.Markdown("")

        redact_btn = gr.Button("✂️ 开始脱敏", variant="primary")
        result_md = gr.Markdown("")
        files_out = gr.File(label="输出文件下载", file_count="multiple", visible=False)

        detect_btn.click(
            do_detect,
            inputs=[file_in, use_claude, strict, ocr_provider],
            outputs=[log_box, entity_df, detection_state, stage_md],
        )
        add_btn.click(
            do_add_entity,
            inputs=[detection_state, new_text, new_type, entity_df],
            outputs=[entity_df, detection_state, add_msg],
        )
        redact_btn.click(
            do_redact,
            inputs=[detection_state, entity_df],
            outputs=[log_box, result_md, files_out, detection_state],
        )
    return demo


def main() -> None:
    build_app().launch()


if __name__ == "__main__":
    main()
