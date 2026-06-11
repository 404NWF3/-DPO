"""Claude Agent SDK entry point: `python -m dpo_agent.agent_runner <file>`.

Wires the DPO custom tools (detect/redact/OCR) into an in-process MCP server
and lets a Claude agent drive the detect → review → redact → validate loop,
guided by the dpo-* skills in .claude/skills/.
"""

from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """\
你是 DPO 文档脱敏 Agent。对用户给定的文件执行完整脱敏闭环：
1. 调用 detect_entities 获取三层检测的候选实体；
2. 审阅候选清单，结合上下文补充遗漏的客户名称/合同方/地址等语义实体（可直接修改 entities JSON）；
3. 调用 redact_document 执行脱敏并生成报告；
4. 若 validation_passed=false，分析残留项、调整实体清单后重试（最多 3 轮）；
5. 图片或扫描件先用 ocr_image 取得文本与 bbox。
最后用中文总结：实体数量、输出文件、复检结论。规则细节见 dpo-redaction / dpo-ocr / dpo-review skills。"""


async def run(file_path: str, output_dir: str = "outputs") -> None:
    try:
        from claude_agent_sdk import (
            ClaudeAgentOptions,
            create_sdk_mcp_server,
            query,
        )
    except ImportError:
        print(
            "claude-agent-sdk 未安装。请先执行: pip install dpo-agent[agent]",
            file=sys.stderr,
        )
        raise SystemExit(1)

    from .tools.ocr_tool import ocr_image
    from .tools.redaction_tool import detect_entities, redact_document

    server = create_sdk_mcp_server(
        name="dpo", version="0.1.0",
        tools=[detect_entities, redact_document, ocr_image],
    )
    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"dpo": server},
        allowed_tools=[
            "mcp__dpo__detect_entities",
            "mcp__dpo__redact_document",
            "mcp__dpo__ocr_image",
        ],
        setting_sources=["project"],  # load .claude/skills/
        max_turns=20,
    )
    prompt = f"请对文件 {file_path} 执行脱敏，输出目录 {output_dir}。"
    async for message in query(prompt=prompt, options=options):
        _print_message(message)


def _print_message(message) -> None:
    content = getattr(message, "content", None)
    if isinstance(content, list):
        for block in content:
            text = getattr(block, "text", None)
            if text:
                print(text)
    result = getattr(message, "result", None)
    if result:
        print(result)


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python -m dpo_agent.agent_runner <file> [output_dir]", file=sys.stderr)
        raise SystemExit(2)
    asyncio.run(run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "outputs"))


if __name__ == "__main__":
    main()
