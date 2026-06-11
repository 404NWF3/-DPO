---
name: dpo-review
description: DPO 复检（validation）工作流 —— 脱敏后必查项、残留扫描、失败回环。完成脱敏输出后必须使用。
---

# dpo-review skill

## 必查项（最低要求）

对**脱敏后的文本**逐项检查：

1. 手机号 / 邮箱 / 银行账号 regex 重扫 → 0 命中；
2. 地址关键词（地址/住所/Address）后是否仍跟真实地址；
3. 甲方/乙方/Party A/B 标记后是否仍有未替换实体；
4. 所有 selected 实体的原文不再出现在任何输出文件中。

实现：`src/dpo_agent/redactors.py::validate_redaction`。

## 结果呈现

- 通过项：`✅ 手机号已全部替换`
- 残留项：`⚠️ 第 2 页仍有 1 个未替换邮箱`（带页码/掩码片段，不展示明文）

## 失败回环

`validation_passed = false` 时回到 Review 阶段：

1. 把残留片段补录为新实体（source=user 或 claude）；
2. 重新执行 redact；
3. 最多 3 轮，仍失败则向用户报告残留清单并停止，绝不静默放行。
