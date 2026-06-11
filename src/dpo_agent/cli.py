"""CLI entry point: `dpo-redact ui|detect|redact`."""

from __future__ import annotations

import json
import sys

import click
from dotenv import load_dotenv

load_dotenv()

# Windows consoles default to a legacy codepage; force UTF-8 so CN text renders.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


@click.group()
def main() -> None:
    """DPO Agent — 文档脱敏工具。"""


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=7860, show_default=True, type=int)
@click.option("--share", is_flag=True, default=False)
def ui(host: str, port: int, share: bool) -> None:
    """启动 Gradio UI。"""
    from .app import build_app

    build_app().launch(server_name=host, server_port=port, share=share)


@main.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "output_dir", default="outputs", show_default=True)
@click.option("--use-claude/--no-claude", default=False, show_default=True)
@click.option("--strict", is_flag=True, default=False, help="低风险实体也默认选中")
@click.option("--ocr-provider", default=None, type=click.Choice(["glm_ocr", "mock"]))
def detect(file: str, output_dir: str, use_claude: bool, strict: bool, ocr_provider: str | None) -> None:
    """仅检测，打印候选实体 JSON。"""
    from .pipeline import detect as run_detect

    result = run_detect(
        file, use_claude=use_claude, strict=strict, ocr_provider=ocr_provider,
        progress=lambda m: click.echo(m, err=True),
    )
    click.echo(
        json.dumps(
            [
                {
                    "id": e.id, "type": e.entity_type, "masked": e.masked_text,
                    "replacement": e.replacement, "risk": e.risk_level,
                    "source": e.source, "selected": e.selected,
                }
                for e in result.entities
            ],
            ensure_ascii=False, indent=2,
        )
    )
    if result.warnings:
        for w in result.warnings:
            click.echo(f"warning: {w}", err=True)


@main.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "output_dir", default="outputs", show_default=True)
@click.option("--use-claude/--no-claude", default=False, show_default=True)
@click.option("--strict", is_flag=True, default=False)
@click.option("--ocr-provider", default=None, type=click.Choice(["glm_ocr", "mock"]))
def redact(file: str, output_dir: str, use_claude: bool, strict: bool, ocr_provider: str | None) -> None:
    """检测并脱敏，输出脱敏文件 + 报告。"""
    from .pipeline import run_pipeline

    _, result = run_pipeline(
        file, output_dir=output_dir, use_claude=use_claude, strict=strict,
        ocr_provider=ocr_provider, progress=lambda m: click.echo(m, err=True),
    )
    click.echo(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    sys.exit(0 if result.validation_passed else 1)


if __name__ == "__main__":
    main()
