from __future__ import annotations

from pathlib import Path
from typing import Any


def render_selected_editing_advice_markdown(payload: dict[str, Any]) -> str:
    advice_items = payload.get("selected_editing_advice", [])
    lines = [
        "# Selected Editing Advice",
        "",
        f"Selected photos: {len(advice_items)}",
        "",
    ]
    for item in advice_items:
        lines.extend(_render_item(item))
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


def _tone_text(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    recommendation = str(value.get("recommendation", "")).replace("_", " ")
    rationale = str(value.get("rationale", ""))
    return f"{recommendation} - {rationale}" if rationale else recommendation
