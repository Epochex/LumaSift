from __future__ import annotations

from pathlib import Path
from typing import Any

from lumasift.analysis.editing_advice import ADVANCED_LIGHTROOM_SECTION_ORDER


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
        f"- Analysis: {_analysis_label(item)}",
        f"- Blocked reason: {item.get('blocked_reason', '')}",
        "",
        "### Photo Read",
        "",
        _photo_read_text(item),
        "",
        "### Content Decision",
        "",
        _content_decision_text(item),
        "",
        "### Direction",
        "",
        str(item.get("editing_intent") or item.get("editing_direction", "")).strip(),
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
    advanced = _advanced_parameters_markdown(item, language="en")
    if advanced:
        lines.extend(["", advanced])
    lines.extend(
        [
            "",
            "### Crop",
            "",
            str(item.get("crop_strategy", "")).strip(),
            "",
            _crop_plan_text(item, language="en"),
            "",
            "### Local Adjustments",
            "",
        ]
    )
    for adjustment in item.get("local_adjustments", []) or []:
        lines.append(f"- {adjustment}")
    mask_text = _local_masks_text(item, language="en")
    if mask_text:
        lines.extend(["", "### Evidence-Bound Local Masks", "", mask_text])
    avoid = str(item.get("avoid_overediting", "") or "").strip()
    if avoid:
        lines.extend(["", "### Do Not Remove", "", avoid])
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
        f"- 分析状态：{_analysis_label(item)}",
        f"- 阻断原因：{item.get('blocked_reason', '')}",
        "",
        "### 照片阅读",
        "",
        _photo_read_text(item),
        "",
        "### 内容判断",
        "",
        _content_decision_text(item),
        "",
        "### 总体方向",
        "",
        str(item.get("editing_intent") or item.get("editing_direction", "")).strip(),
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
    advanced = _advanced_parameters_markdown(item, language="zh")
    if advanced:
        lines.extend(["", advanced])
    lines.extend(
        [
            "",
            "### 裁切建议",
            "",
            str(item.get("crop_strategy", "")).strip(),
            "",
            _crop_plan_text(item, language="zh"),
            "",
            "### 局部调整",
            "",
        ]
    )
    for adjustment in item.get("local_adjustments", []) or []:
        lines.append(f"- {adjustment}")
    mask_text = _local_masks_text(item, language="zh")
    if mask_text:
        lines.extend(["", "### 证据绑定局部蒙版", "", mask_text])
    avoid = str(item.get("avoid_overediting", "") or "").strip()
    if avoid:
        lines.extend(["", "### 别修掉", "", avoid])
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


def _advanced_parameters_markdown(item: dict[str, Any], *, language: str) -> str:
    sections = item.get("advanced_lightroom_parameters")
    labels = item.get("advanced_lightroom_parameter_labels")
    if not isinstance(sections, dict):
        return ""
    label_map = labels if isinstance(labels, dict) else {}
    section_labels = label_map.get("sections") if isinstance(label_map.get("sections"), dict) else {}
    key_labels = label_map.get("keys") if isinstance(label_map.get("keys"), dict) else {}
    lines: list[str] = []
    for section_key in ADVANCED_LIGHTROOM_SECTION_ORDER:
        if section_key == "basic":
            continue
        value = sections.get(section_key)
        if not isinstance(value, dict) or not value:
            continue
        title = str(section_labels.get(section_key) or _fallback_label(section_key, language=language))
        lines.extend([f"#### {title}", ""])
        for key, row_value in value.items():
            label = str(key_labels.get(key) or _fallback_label(key, language=language))
            if isinstance(row_value, dict):
                parts = []
                for nested_key, nested_value in row_value.items():
                    nested_label = str(key_labels.get(nested_key) or _fallback_label(nested_key, language=language))
                    parts.append(f"{nested_label} {_localized_value(nested_value, key_labels)}")
                lines.append(f"- {label}：`{' / '.join(parts)}`" if language == "zh" else f"- {label}: `{' / '.join(parts)}`")
            else:
                lines.append(f"- {label}：`{_localized_value(row_value, key_labels)}`" if language == "zh" else f"- {label}: `{_localized_value(row_value, key_labels)}`")
        lines.append("")
    return "\n".join(lines).rstrip()


def _localized_value(value: Any, key_labels: dict[str, Any]) -> str:
    text = str(value)
    return str(key_labels.get(text, text))


def _fallback_label(key: str, *, language: str) -> str:
    if language != "zh":
        return key.replace("_", " ").title()
    return {
        "tone_curve": "曲线",
        "hsl_color_mixer": "HSL / 颜色混合",
        "color_grading": "色彩分级",
        "calibration": "校准",
        "detail": "细节",
        "noise_reduction": "降噪",
        "lens_corrections": "镜头校正",
        "effects_grain_vignette": "效果 / 颗粒 / 暗角",
    }.get(key, key.replace("_", " "))


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


def _analysis_label(item: dict[str, Any]) -> str:
    status = item.get("analysis_status")
    if isinstance(status, dict):
        note = str(status.get("note", "")).strip()
        label = str(status.get("label", "")).strip()
        return f"{label} - {note}" if note else label
    return ""


def _photo_read_text(item: dict[str, Any]) -> str:
    read = item.get("photo_reading")
    if not isinstance(read, dict):
        return str(item.get("story_interpretation", "")).strip()
    lines: list[str] = []
    summary = str(read.get("summary", "")).strip()
    if summary:
        lines.append(summary)
    evidence = read.get("visible_evidence")
    if isinstance(evidence, list) and evidence:
        lines.append("")
        lines.append("可见证据：" if _looks_zh(item) else "Visible evidence:")
        lines.extend(f"- {entry}" for entry in evidence if str(entry).strip())
    labels = [
        ("主体关系", "subject_relationship"),
        ("决定性瞬间", "decisive_moment_read"),
        ("为什么是这张", "why_this_frame"),
    ] if _looks_zh(item) else [
        ("Subject relationship", "subject_relationship"),
        ("Decisive moment", "decisive_moment_read"),
        ("Why this frame", "why_this_frame"),
    ]
    for label, key in labels:
        value = str(read.get(key, "")).strip()
        if value:
            lines.append(f"- {label}: {value}")
    return "\n".join(lines).strip()


def _content_decision_text(item: dict[str, Any]) -> str:
    decision = item.get("content_decision")
    if not isinstance(decision, dict):
        return ""
    lines = [str(decision.get("editor_note", "")).strip()]
    keep = decision.get("keep_reasons")
    if isinstance(keep, list) and keep:
        prefix = "保留" if _looks_zh(item) else "Keep"
        lines.extend(f"- {prefix}: {entry}" for entry in keep if str(entry).strip())
    risks = decision.get("risks")
    if isinstance(risks, list) and risks:
        prefix = "风险" if _looks_zh(item) else "Risk"
        lines.extend(f"- {prefix}: {entry}" for entry in risks if str(entry).strip())
    return "\n".join(line for line in lines if line).strip()


def _crop_plan_text(item: dict[str, Any], *, language: str) -> str:
    plan = item.get("crop_plan")
    if not isinstance(plan, dict):
        return ""
    keep = plan.get("keep") if isinstance(plan.get("keep"), list) else []
    remove = plan.get("remove_or_reduce") if isinstance(plan.get("remove_or_reduce"), list) else []
    aspect = str(plan.get("aspect_ratio", "")).strip()
    if language == "zh":
        lines = [f"- 比例：{aspect}" if aspect else ""]
        lines.extend(f"- 保留：{entry}" for entry in keep if str(entry).strip())
        lines.extend(f"- 压弱/裁掉：{entry}" for entry in remove if str(entry).strip())
    else:
        lines = [f"- Aspect ratio: {aspect}" if aspect else ""]
        lines.extend(f"- Keep: {entry}" for entry in keep if str(entry).strip())
        lines.extend(f"- Reduce/remove: {entry}" for entry in remove if str(entry).strip())
    return "\n".join(line for line in lines if line)


def _local_masks_text(item: dict[str, Any], *, language: str) -> str:
    masks = item.get("local_masks")
    if not isinstance(masks, list):
        return ""
    lines: list[str] = []
    for mask in masks:
        if not isinstance(mask, dict):
            continue
        target = str(mask.get("target", "")).strip()
        operation = str(mask.get("operation", "")).strip()
        reason = str(mask.get("reason", "")).strip()
        if not (target or operation or reason):
            continue
        if language == "zh":
            lines.append(f"- 区域：{target}；动作：{operation}；原因：{reason}")
        else:
            lines.append(f"- Target: {target}; Operation: {operation}; Reason: {reason}")
    return "\n".join(lines)


def _looks_zh(item: dict[str, Any]) -> bool:
    text = " ".join(str(item.get(key, "")) for key in ("recommended_style_label", "category_label"))
    status = item.get("analysis_status")
    if isinstance(status, dict):
        text += " " + str(status.get("label", ""))
    return any("\u4e00" <= char <= "\u9fff" for char in text)
