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


def test_local_fallback_produces_technical_draft_not_photographic_claim() -> None:
    payload = build_selected_editing_advice([_record(1, "street.jpg")], selected_ranks=[1], language="en")
    advice = payload["selected_editing_advice"][0]

    assert advice["recommended_style"] == "high_contrast_bw_documentary"
    assert advice["tone_recommendation"]["recommendation"] == "black_and_white"
    assert advice["editing_advice_source"] == "technical_draft"
    assert advice["blocked_reason"]
    assert advice["analysis_status"]["level"] == "local_prefilter"
    assert advice["lightroom_parameters"]["exposure"] == "+0.15"
    assert advice["lightroom_parameters"]["shadows"] == "+32"
    assert "crop" not in advice["crop_strategy"].lower() or advice["crop_strategy"]
    assert len(advice["local_adjustments"]) >= 3
    assert "Subject/gesture mask" not in " ".join(advice["local_adjustments"])
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
        analysis_source="qwen_vision",
        analysis_quality="concrete",
        editorial_verdict={"action": "keep", "confidence": 82, "one_line_reason": "left foreground cyclist overlaps with the crossing crowd before it dissolves"},
        visible_evidence=[
            "left foreground cyclist overlaps with the crossing crowd",
            "red storefront sign anchors the street corner",
            "background pedestrians form a second layer behind the cyclist",
        ],
        subject_relationship="The cyclist, crossing crowd, and storefront sign create a layered street relationship.",
        decisive_moment_read="The frame catches the cyclist before they cover the walking figures.",
        why_this_frame="The overlap is readable and the street sign still anchors place.",
        avoid_overediting="Keep the red sign and imperfect street texture.",
        editing_plan={
            "edit_intent": "clarify the left foreground cyclist and red storefront sign relationship",
            "crop_plan": {
                "aspect_ratio": "16:9",
                "keep": ["left foreground cyclist", "red storefront sign"],
                "remove_or_reduce": ["empty right edge"],
            },
            "local_masks": [
                {
                    "target": "left foreground cyclist",
                    "operation": "Exposure +0.20",
                    "settings": {"exposure": "+0.20"},
                    "reason": "keep the cyclist readable against the crossing crowd",
                }
            ],
        },
        crop_strategy="Use a 16:9 crop that keeps the walking direction open.",
        local_adjustments=["Radial mask on face: Exposure +0.25, Shadows +12."],
    )

    advice = build_selected_editing_advice([record], selected_paths=[Path("C:/photos/color.jpg")], language="en")[
        "selected_editing_advice"
    ][0]

    assert advice["recommended_style"] == "cinematic_urban_color"
    assert advice["editing_advice_source"] == "vision_evidence"
    assert advice["blocked_reason"] == ""
    assert advice["photo_reading"]["visible_evidence"][0].startswith("left foreground")
    assert advice["crop_plan"]["keep"]
    assert advice["local_masks"]
    assert advice["tone_recommendation"]["recommendation"] == "color"
    assert advice["lightroom_parameters"]["contrast"] == "+31"
    assert advice["lightroom_parameters"]["temperature"] == "-650K"
    assert advice["lightroom_parameters"]["highlights"]
    assert advice["crop_strategy"] == "Use a 16:9 crop that keeps the walking direction open."
    assert advice["local_adjustments"] == [
        "left foreground cyclist: Exposure +0.20; reason: keep the cyclist readable against the crossing crowd"
    ]


def test_vision_advice_uses_structured_editing_plan_when_available() -> None:
    record = _record(
        1,
        "qwen.jpg",
        analysis_source="qwen_vision",
        analysis_quality="concrete",
        editorial_verdict={"action": "maybe", "confidence": 70, "one_line_reason": "左下角戴白耳机的背影人物和 DB 标语形成车站关系"},
        visible_evidence=["左下角戴白耳机的背影人物遮挡栏杆", "上方 DB 标语提供柏林车站语境", "中景两名行人走向站台"],
        subject_relationship="前景旅客、中景行人和车站标语形成通勤空间关系。",
        decisive_moment_read="瞬间偏弱，人物之间没有直接互动。",
        why_this_frame="这帧保留完整标语和前景遮挡关系。",
        editing_plan={
            "edit_intent": "压弱前景遮挡，让 DB 标语和中景行人承担车站故事。",
            "crop_plan": {
                "aspect_ratio": "3:2",
                "keep": ["DB 标语", "中景两名行人"],
                "remove_or_reduce": ["左下角过重的后脑勺遮挡"],
            },
            "local_masks": [
                {
                    "target": "左下角前景人物",
                    "operation": "曝光 -0.20，清晰度 -5",
                    "settings": {"exposure": "-0.20"},
                    "reason": "避免遮挡物抢走标语和行人关系",
                }
            ],
            "do_not_overedit": ["保留车站冷色环境"],
        },
    )

    advice = build_selected_editing_advice([record], selected_ranks=[1])["selected_editing_advice"][0]

    assert advice["editing_intent"].startswith("压弱前景遮挡")
    assert advice["crop_plan"]["keep"] == ["DB 标语", "中景两名行人"]
    assert advice["local_masks"][0]["target"] == "左下角前景人物"
    assert advice["evidence_snapshot"]["visible_evidence"][0].startswith("左下角")


def test_markdown_report_renders_selected_advice() -> None:
    payload = build_selected_editing_advice([_record(1, "street.jpg")], selected_ranks=[1], language="en")

    markdown = render_selected_editing_advice_markdown(payload)

    assert "# Selected Editing Advice" in markdown
    assert "## Rank 1: street.jpg" in markdown
    assert "### Lightroom Parameters" in markdown
    assert "### Photo Read" in markdown
    assert "Local pre-screen only" in markdown
    assert "Exposure" in markdown
    assert "### Crop" in markdown
    assert "### Local Adjustments" in markdown
    assert "### Grain, Sharpness, Motion Blur" in markdown


def test_default_markdown_report_is_chinese() -> None:
    payload = build_selected_editing_advice([_record(1, "street.jpg")], selected_ranks=[1])

    markdown = render_selected_editing_advice_markdown(payload)
    advice = payload["selected_editing_advice"][0]

    assert payload["language"] == "zh"
    assert "# 选中照片修图方案" in markdown
    assert "## 第 1 张：street.jpg" in markdown
    assert "### Lightroom 参数" in markdown
    assert "### 照片阅读" in markdown
    assert "仅本地预筛" in markdown
    assert "曝光" in markdown
    assert "Amount" not in advice["grain_sharpness_motion_blur"]["grain"]
