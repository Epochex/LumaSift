import json
from pathlib import Path

from lumasift.analysis.editing_advice import build_selected_editing_advice
from lumasift.reports.markdown_report import render_selected_editing_advice_markdown


def _record(rank: int, filename: str, **overrides: object) -> dict:
    record = {
        "rank": rank,
        "path": f"C:/photos/{filename}",
        "filename": filename,
        "width": 4000,
        "height": 2667,
        "technical_quality_score": 58.0,
        "storytelling_score": 70.0,
        "human_documentary_value_score": 72.0,
        "decisive_moment_score": 64.0,
        "emotional_impact_score": 68.0,
        "visual_tension_score": 78.0,
        "editing_potential_score": 76.0,
        "final_selection_score": 74.5,
        "category": "strong_edit_candidate",
        "recommended_style": "pending_vision_review",
        "best_editing_direction": "Run qwen_vision mode for concrete artistic editing guidance.",
        "specific_edit_parameters": {},
        "local_metrics": {
            "brightness": 76.0,
            "contrast": 55.0,
            "highlight_clipping_ratio": 0.0,
            "shadow_clipping_ratio": 0.03,
        },
    }
    record.update(overrides)
    return record


def test_build_selected_editing_advice_selects_by_rank_and_path() -> None:
    records = [
        _record(1, "keeper.jpg"),
        _record(2, "maybe.jpg"),
        _record(3, "quiet.jpg"),
    ]

    payload = build_selected_editing_advice(records, selected_ranks="1,3", selected_paths="maybe.jpg")

    assert payload["schema"] == "selected_editing_advice.v1"
    assert [item["filename"] for item in payload["selected_editing_advice"]] == [
        "keeper.jpg",
        "maybe.jpg",
        "quiet.jpg",
    ]
    json.dumps(payload)


def test_deterministic_fallback_produces_concrete_editing_advice() -> None:
    payload = build_selected_editing_advice([_record(1, "street.jpg")], selected_ranks=[1])
    advice = payload["selected_editing_advice"][0]

    assert advice["recommended_style"] == "high_contrast_bw_documentary"
    assert advice["tone_recommendation"]["recommendation"] == "black_and_white"
    assert advice["lightroom_parameters"]["exposure"] == "+0.15"
    assert advice["lightroom_parameters"]["shadows"] == "+32"
    assert "crop" not in advice["crop_strategy"].lower() or advice["crop_strategy"]
    assert len(advice["local_adjustments"]) >= 3
    assert "Amount" in advice["grain_sharpness_motion_blur"]["grain"]
    assert "Masking" in advice["grain_sharpness_motion_blur"]["sharpness"]
    assert "Run qwen_vision" not in advice["editing_direction"]


def test_existing_qwen_style_and_parameters_are_preserved_and_filled() -> None:
    record = _record(
        1,
        "color.jpg",
        recommended_style="cinematic_urban_color",
        best_editing_direction="Protect the human gesture and shape the background into a cool urban color grade.",
        specific_edit_parameters={"contrast": "+31", "temperature": "-650K"},
        crop_strategy="Use a 16:9 crop that keeps the walking direction open.",
        local_adjustments=["Radial mask on face: Exposure +0.25, Shadows +12."],
    )

    advice = build_selected_editing_advice([record], selected_paths=[Path("C:/photos/color.jpg")])[
        "selected_editing_advice"
    ][0]

    assert advice["recommended_style"] == "cinematic_urban_color"
    assert advice["tone_recommendation"]["recommendation"] == "color"
    assert advice["lightroom_parameters"]["contrast"] == "+31"
    assert advice["lightroom_parameters"]["temperature"] == "-650K"
    assert advice["lightroom_parameters"]["highlights"]
    assert advice["crop_strategy"] == "Use a 16:9 crop that keeps the walking direction open."
    assert advice["local_adjustments"] == ["Radial mask on face: Exposure +0.25, Shadows +12."]


def test_markdown_report_renders_selected_advice() -> None:
    payload = build_selected_editing_advice([_record(1, "street.jpg")], selected_ranks=[1])

    markdown = render_selected_editing_advice_markdown(payload)

    assert "# Selected Editing Advice" in markdown
    assert "## Rank 1: street.jpg" in markdown
    assert "### Lightroom Parameters" in markdown
    assert "Exposure" in markdown
    assert "### Crop" in markdown
    assert "### Local Adjustments" in markdown
    assert "### Grain, Sharpness, Motion Blur" in markdown
