---
name: dpo-redaction
description: DPO 脱敏规则 —— 实体类型、风险分级、占位符格式、替换策略。执行文档脱敏或审阅候选实体时使用。
---

# dpo-redaction skill

## 检测目标（实体类型）

| 类型 | 示例 | 默认风险 |
|---|---|---|
| 手机号 | 138xxxx5678（CN 1[3-9]开头11位） | high |
| 邮箱 | a@b.com | high |
| 银行账号 / IBAN / SWIFT | 16-19位卡号、IBAN、SWIFT BIC | high |
| 客户名称 / 合同方 | 甲方/乙方指代的公司、客户全称 | high |
| 联系人 | 联系人/经办人/法定代表人姓名 | medium |
| 地址 | 能定位到单位/个人的地址 | medium |
| 开户行 | 开户银行支行名 | medium |
| 座机 | 010-12345678 | medium |

组合风险升级：地址+单位名、单位名+银行账号同段出现 → 一律 high。

## 风险分级与默认勾选

- `high` / `medium`：始终默认选中。
- `low`：仅严格模式（--strict）默认选中。

## 占位符格式

`<类型_序号>`，如 `<手机号_1>`、`<客户名称_2>`。同一原文必须映射到同一占位符（全文一致性）。

## 替换顺序

按原文长度**从长到短**替换，防止短串先替换破坏长串。实现：`src/dpo_agent/redactors.py::redact_text`。

## 图片遮盖

OCR bbox 上画黑色实心矩形，行级粒度即可。实现：`redactors.py::redact_image`。

## 红线

- 绝不把未脱敏原文发给任何外部 LLM 之外的第三方服务。
- 报告（report.json/md）中实体原文一律用掩码（`mask_text`），不落盘明文。
