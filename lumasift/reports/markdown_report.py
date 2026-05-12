from __future__ import annotations

from pathlib import Path
from typing import Any


def render_selected_editing_advice_markdown(payload: dict[str, Any]) -> str:
    advice_items = payload.get("selected_editing_advice", [])
    language = "en" if payload.get("language") == "en" else "zh"
    if language == "zh":
        return _render_selected_editing_advice_markdown_zh(advice_items)
    lines = [
        "# Selected Editing Advice",
        "",
        f"Selected photos: {len(advice_items)}",
        "",
    ]
    for item in advice_items:
        lines.extend(_render_item(item))
    return "\n".join(lines).rstrip() + "\n"


def _render_selected_editing_advice_markdown_zh(advice_items: list[dict[str, Any]]) -> str:
    lines = [
        "# 选中照片修图方案",
        "",
        f"选中照片：{len(advice_items)} 张",
        "",
    ]
    for item in advice_items:
        lines.extend(_render_item_zh(item))
    return "\n".join(lines).rstrip() + "\n"


def render_editing_advice_markdown(payload: dict[str, Any]) -> str:
    return render_selected_editing_advice_markdown(payload)


def write_markdown_report(path: Path, markdown: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")


def write_selected_editing_advice_markdown(path: Path, payload: dict[str, Any]) -> None:
    write_markdown_report(path, render_selected_editing_advice_markdown(payload))


def _render_item(item: dict[str, Any]) -> list[str]:
    rank = item.get("rank", "?")
    filename = item.get("filename") or Path(str(item.get("path", ""))).name or "unknown"
    score = item.get("final_selection_score", 0.0)
    style = item.get("recommended_style", "unknown")
    lines = [
        f"## Rank {rank}: {filename}",
        "",
        f"- Path: `{item.get('path', '')}`",
        f"- Score: {score}",
        f"- Category: {item.get('category', '')}",
        f"- Recommended style: `{style}`",
        f"- B&W/color: {_tone_text(item.get('tone_recommendation'))}",
        "",
        "### Direction",
        "",
        str(item.get("editing_direction", "")).strip(),
        "",
        "### Lightroom Parameters",
        "",
    ]
    parameters = item.get("lightroom_parameters", {})
    if isinstance(parameters, dict):
        for key in [
            "exposure",
            "contrast",
            "highlights",
            "shadows",
            "whites",
            "blacks",
            "texture",
            "clarity",
            "dehaze",
            "vibrance",
            "saturation",
            "temperature",
            "tint",
        ]:
            lines.append(f"- {key.replace('_', ' ').title()}: `{parameters.get(key, '')}`")
    lines.extend(
        [
            "",
            "### Crop",
            "",
            str(item.get("crop_strategy", "")).strip(),
            "",
            "### Local Adjustments",
            "",
        ]
    )
    for adjustment in item.get("local_adjustments", []) or []:
        lines.append(f"- {adjustment}")
    handling = item.get("grain_sharpness_motion_blur", {})
    lines.extend(
        [
            "",
            "### Grain, Sharpness, Motion Blur",
            "",
            f"- Grain: {handling.get('grain', '') if isinstance(handling, dict) else ''}",
            f"- Sharpness: {handling.get('sharpness', '') if isinstance(handling, dict) else ''}",
            f"- Motion blur: {handling.get('motion_blur', '') if isinstance(handling, dict) else ''}",
            "",
        ]
    )
    return lines


def _render_item_zh(item: dict[str, Any]) -> list[str]:
    rank = item.get("rank", "?")
    filename = item.get("filename") or Path(str(item.get("path", ""))).name or "unknown"
    score = item.get("final_selection_score", 0.0)
    style = item.get("recommended_style_label") or str(item.get("recommended_style", "")).replace("_", " ")
    category = item.get("category_label") or str(item.get("category", "")).replace("_", " ")
    tone = item.get("tone_recommendation")
    lines = [
        f"## 第 {rank} 张：{filename}",
        "",
        f"- 路径：`{item.get('path', '')}`",
        f"- 综合分：{score}",
        f"- 分类：{category}",
        f"- 推荐风格：{style}",
        f"- 黑白/彩色：{_tone_text_zh(tone)}",
        "",
        "### 总体方向",
        "",
        str(item.get("editing_direction", "")).strip(),
        "",
        "### Lightroom 参数",
        "",
    ]
    parameters = item.get("lightroom_parameters", {})
    labels = item.get("lightroom_parameter_labels", {})
    if isinstance(parameters, dict):
        for key in [
            "exposure",
            "contrast",
            "highlights",
            "shadows",
            "whites",
            "blacks",
            "texture",
            "clarity",
            "dehaze",
            "vibrance",
            "saturation",
            "temperature",
            "tint",
        ]:
            label = labels.get(key, key) if isinstance(labels, dict) else key
            lines.append(f"- {label}：`{parameters.get(key, '')}`")
    lines.extend(
        [
            "",
            "### 裁切建议",
            "",
            str(item.get("crop_strategy", "")).strip(),
            "",
            "### 局部调整",
            "",
        ]
    )
    for adjustment in item.get("local_adjustments", []) or []:
        lines.append(f"- {adjustment}")
    handling = item.get("grain_sharpness_motion_blur", {})
    lines.extend(
        [
            "",
            "### 颗粒、锐化、运动模糊",
            "",
            f"- 颗粒：{handling.get('grain', '') if isinstance(handling, dict) else ''}",
            f"- 锐化：{handling.get('sharpness', '') if isinstance(handling, dict) else ''}",
            f"- 运动模糊：{handling.get('motion_blur', '') if isinstance(handling, dict) else ''}",
            "",
        ]
    )
    return lines


def _tone_text(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    recommendation = str(value.get("recommendation", "")).replace("_", " ")
    rationale = str(value.get("rationale", ""))
    return f"{recommendation} - {rationale}" if rationale else recommendation


def _tone_text_zh(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    recommendation = str(value.get("label") or value.get("recommendation", "")).replace("_", " ")
    rationale = str(value.get("rationale", ""))
    return f"{recommendation} - {rationale}" if rationale else recommendation
