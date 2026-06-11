---
name: dpo-ocr
description: DPO OCR 策略 —— provider 选择、GLM OCR 调用、bbox 规范、降级路径。处理图片或扫描件输入时使用。
---

# dpo-ocr skill

## Provider 选择

1. `glm_ocr`：生产路径，需要 `ZHIPU_API_KEY`。两个官方端点（由 `GLM_OCR_ENDPOINT` 决定）：
   - **`/api/paas/v4/files/ocr`（默认）**：multipart/form-data 上传（字段 `file` + `tool_type` + `language_type` + `probability`），响应 `words_result[]` 每行带 `words` 文本和 `location{left,top,width,height}` bbox —— 图片黑框遮盖必须用这个端点。⚠️ 不能发 JSON，否则报 `Current request is not a multipart request`。
   - **`/api/paas/v4/layout_parsing`**：JSON 请求 `{"model": "glm-ocr", "file": "<url 或 base64 data-uri>"}`，返回文档级 markdown；无 bbox 时只能做文本脱敏，不能画黑框。
2. `mock`：测试/离线路径。读取图片旁的 `<image>.ocr.json` sidecar（`[{"text","bbox","confidence"}]`），无 sidecar 时返回一条假数据保证管线可跑。

代码入口：`src/dpo_agent/ocr/`，agent 工具：`ocr_image(image_path, provider)`。

## 输出规范

行级 `OCRBlock`：`text`、`bbox=[x0,y0,x1,y1]`（像素坐标，多边形需归一为外接矩形）、`confidence`、`page`。

## 降级规则

- 无 key / 调用失败 → 不中断管线：记 warning，提示用户配置 `ZHIPU_API_KEY` 或改用 mock。
- 置信度 < 0.6 的行在 review 阶段标注提醒，不直接丢弃。
- 绝不把图片发给未授权的第三方服务。
