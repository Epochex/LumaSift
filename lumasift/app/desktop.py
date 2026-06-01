from __future__ import annotations

import html
import ctypes
import json
import logging
import os
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractListModel, QEasingCurve, QEvent, QItemSelectionModel, QModelIndex, QObject, QPropertyAnimation, QRect, QSettings, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lumasift.analysis.editing_advice import ADVANCED_LIGHTROOM_SECTION_ORDER, build_selected_editing_advice
from lumasift.analysis.qwen_account import (
    VisionModelCapability,
    format_vision_model_summary,
    query_vision_model_capabilities,
    recommended_vision_model,
)
from lumasift.analysis.qwen_client import QwenVisionClient
from lumasift.analysis.qwen_story import (
    QWEN_STORY_PROMPT_VERSION,
    build_qwen_story_prompt,
    clear_qwen_review_fields,
    is_current_concrete_qwen_review,
    merge_qwen_story_analysis,
    validate_qwen_story_response,
)
from lumasift.analysis.scoring import rank_records
from lumasift.analysis.user_feedback import apply_user_feedback_fields, normalized_user_label
from lumasift.core.config import Settings
from lumasift.core.harness import LumaSiftHarness
from lumasift.core.keyring import ApiKeyRing
from lumasift.core.logging_setup import configure_logging
from lumasift.io.preview import create_jpeg_preview
from lumasift.reports.csv_report import write_csv_report
from lumasift.reports.json_report import write_json_report
from lumasift.reports.markdown_report import render_selected_editing_advice_markdown, write_markdown_report
from lumasift.storage.state_db import LumaSiftStateDb


DEFAULT_VISION_BASE_URL = "https://api.newcoin.top/v1"
STALE_VISION_MODEL_VALUES = {"custom-vision-model", "example-vision-model"}
THEME_VALUES = {"dark", "light"}


def _clean_vision_base_url(value: object) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text or "example.test" in text:
        return DEFAULT_VISION_BASE_URL
    return text


def _vision_base_url_override(value: object) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text or "example.test" in text or text == DEFAULT_VISION_BASE_URL:
        return ""
    return text


def _clean_vision_model_override(value: object) -> str:
    text = str(value or "").strip()
    if text in STALE_VISION_MODEL_VALUES:
        return ""
    return text


def lumasift_resource_path(filename: str) -> Path | None:
    candidates = [
        Path(__file__).resolve().parents[1] / "resources" / filename,
        Path(getattr(sys, "_MEIPASS", "")) / "lumasift" / "resources" / filename,
        Path(sys.executable).resolve().parent / "lumasift" / "resources" / filename,
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def lumasift_icon_path() -> Path | None:
    return lumasift_resource_path("lumasift.ico")


def lumasift_app_icon() -> QIcon:
    path = lumasift_icon_path()
    return QIcon(str(path)) if path else QIcon()


def configure_windows_app_identity() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LumaSift.LumaSift.0.1")
    except Exception:
        return


def _qt_value(value: Any) -> int:
    return int(getattr(value, "value", value))


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _record_crop_plan(record: dict[str, Any]) -> dict[str, Any]:
    editing_plan = record.get("editing_plan")
    if isinstance(editing_plan, dict) and isinstance(editing_plan.get("crop_plan"), dict):
        return editing_plan["crop_plan"]
    crop_plan = record.get("crop_plan")
    return crop_plan if isinstance(crop_plan, dict) else {}


def _record_crop_box(record: dict[str, Any]) -> dict[str, float] | None:
    crop_plan = _record_crop_plan(record)
    raw_box = crop_plan.get("crop_box")
    if not isinstance(raw_box, dict):
        raw_box = crop_plan.get("box")
    if not isinstance(raw_box, dict):
        return None

    x = _float_or_none(raw_box.get("x"))
    y = _float_or_none(raw_box.get("y"))
    width = _float_or_none(raw_box.get("width"))
    height = _float_or_none(raw_box.get("height"))
    if x is None or y is None or width is None or height is None:
        return None
    if width <= 0.02 or height <= 0.02:
        return None

    x = max(0.0, min(0.98, x))
    y = max(0.0, min(0.98, y))
    width = max(0.02, min(1.0 - x, width))
    height = max(0.02, min(1.0 - y, height))
    return {"x": x, "y": y, "width": width, "height": height}


def _record_crop_reason(record: dict[str, Any]) -> str:
    crop_plan = _record_crop_plan(record)
    raw_box = crop_plan.get("crop_box")
    reason_parts: list[str] = []
    if isinstance(raw_box, dict):
        for key in ("reason", "composition_goal"):
            value = str(raw_box.get(key) or "").strip()
            if value:
                reason_parts.append(value)
    for key in ("reason", "composition_goal"):
        value = str(crop_plan.get(key) or "").strip()
        if value and value not in reason_parts:
            reason_parts.append(value)
    fallback = str(record.get("crop_strategy") or "").strip()
    if fallback and fallback not in reason_parts:
        reason_parts.append(fallback)
    return "；".join(reason_parts[:3])


def _light_theme_stylesheet(css: str) -> str:
    replacements = {
        "#090d12": "#f6f8fb",
        "#0a0f15": "#f8fafc",
        "#0b0f14": "#f8fafc",
        "#0c1117": "#ffffff",
        "#0d1218": "#ffffff",
        "#0d131a": "#ffffff",
        "#0f141a": "#ffffff",
        "#10161d": "#ffffff",
        "#101820": "#ffffff",
        "#111820": "#ffffff",
        "#111827": "#f8fafc",
        "#121922": "#f8fafc",
        "#14231e": "#eaf7f1",
        "#15120a": "#fff7d6",
        "#151b22": "#eef3f8",
        "#17212b": "#e2e8f0",
        "#172232": "#eaf4ff",
        "#17324a": "#e0f2fe",
        "#1b1b1b": "#f8fafc",
        "#1e2b3a": "#e0f2fe",
        "#20242a": "#e2e8f0",
        "#233044": "#e2e8f0",
        "#242424": "#e2e8f0",
        "#26313d": "#cbd5e1",
        "#263244": "#cbd5e1",
        "#26384a": "#cbd5e1",
        "#293646": "#cbd5e1",
        "#2a3645": "#cbd5e1",
        "#2f3640": "#cbd5e1",
        "#334155": "#94a3b8",
        "#344457": "#cbd5e1",
        "#36506a": "#94a3b8",
        "#66778a": "#94a3b8",
        "#8fa4b8": "#475569",
        "#8fd3ff": "#0369a1",
        "#93a4b8": "#64748b",
        "#94a3b8": "#64748b",
        "#9fb0c2": "#64748b",
        "#a7a7a7": "#475569",
        "#c8d4e0": "#334155",
        "#dbe7f3": "#1f2937",
        "#e5edf7": "#1f2937",
        "#f8fafc": "#0f172a",
        "#ffffff": "#ffffff",
        "#061019": "#ffffff",
        "#00a6ff": "#5e6ad2",
        "#45c0ff": "#7170ff",
        "#2ea8ff": "#5e6ad2",
        "#ffd400": "#5e6ad2",
        "#ffe45c": "#8299ff",
        "#245d82": "#dfe3ff",
    }
    pattern = re.compile("|".join(re.escape(color) for color in sorted(replacements, key=len, reverse=True)))
    return pattern.sub(lambda match: replacements[match.group(0)], css)


def _shortcut_code(key: Any, modifiers: Any = 0) -> int:
    return _qt_value(key) | _qt_value(modifiers)


SHORTCUT_ACTIONS = ("keep", "reject", "toggle_mark", "maybe", "select_all", "invert_selection")
DEFAULT_SHORTCUT_KEYS = {
    "keep": _shortcut_code(Qt.Key.Key_Up),
    "reject": _shortcut_code(Qt.Key.Key_Down),
    "toggle_mark": _shortcut_code(Qt.Key.Key_S),
    "maybe": _shortcut_code(Qt.Key.Key_D),
    "select_all": _shortcut_code(Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier),
    "invert_selection": _shortcut_code(Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier),
}
SHORTCUT_KEY_CHOICES = [
    ("↑", _shortcut_code(Qt.Key.Key_Up)),
    ("↓", _shortcut_code(Qt.Key.Key_Down)),
    ("←", _shortcut_code(Qt.Key.Key_Left)),
    ("→", _shortcut_code(Qt.Key.Key_Right)),
    ("S", _shortcut_code(Qt.Key.Key_S)),
    ("D", _shortcut_code(Qt.Key.Key_D)),
    ("A", _shortcut_code(Qt.Key.Key_A)),
    ("W", _shortcut_code(Qt.Key.Key_W)),
    ("P", _shortcut_code(Qt.Key.Key_P)),
    ("X", _shortcut_code(Qt.Key.Key_X)),
    ("U", _shortcut_code(Qt.Key.Key_U)),
    ("M", _shortcut_code(Qt.Key.Key_M)),
    ("Space", _shortcut_code(Qt.Key.Key_Space)),
    ("Ctrl+A", _shortcut_code(Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)),
    ("Ctrl+I", _shortcut_code(Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)),
]


UI_TEXT: dict[str, dict[str, str]] = {
    "zh": {
        "app_title": "LumaSift - 本地 AI 选片",
        "hero_title": "LumaSift",
        "hero_subtitle": "本地优先的 AI 选片工作台",
        "scanned": "已扫描",
        "shown": "已显示",
        "selected": "已选择",
        "mode": "模式",
        "local": "本地模式(不消耗token)",
        "qwen": "LLM深度分析(需要填入API，消耗token)",
        "step_import": "1. 导入",
        "step_import_caption": "选择本地照片文件夹",
        "step_local": "2. 初筛",
        "step_local_caption": "本地预览与快速评分",
        "step_qwen": "3. 深度分析",
        "step_qwen_caption": "LLM 只分析高价值候选",
        "step_edit": "4. 修图",
        "step_edit_caption": "多选生成参数方案",
        "photo_folder": "照片目录",
        "output_folder": "结果保存目录（可选）",
        "browse": "浏览",
        "scan": "扫描",
        "qwen_top": "深评",
        "advice_top": "修图",
        "show": "显示",
        "qwen_keys": "LLM深度分析 API",
        "vision_base_url": "接口地址",
        "vision_model": "模型",
        "vision_base_url_placeholder": "留空自动使用默认接口",
        "vision_model_placeholder": "留空自动检测最佳视觉模型",
        "api_placeholder": "可选：输入一个 LLM API key，留空则读取 .env",
        "save_keys": "本机保存密钥",
        "cache_note": "深度模式仅上传 Top-N 压缩预览，RAW 留在本机；默认兼容 OpenAI 图像接口。",
        "analyze": "开始分析",
        "cancel": "取消",
        "ready": "就绪",
        "review_board": "选片板",
        "search": "搜索文件名/分类/风格",
        "all_categories": "全部分类",
        "all_tones": "全部色调",
        "tone_monochrome_or_near_bw": "近黑白",
        "tone_high_contrast": "高反差",
        "tone_low_key": "低调暗部",
        "tone_high_key": "高调明亮",
        "tone_warm_tone": "暖调",
        "tone_cool_tone": "冷调",
        "tone_vivid_color": "高饱和",
        "tone_muted_color": "低饱和",
        "all_labels": "全部标记",
        "unlabeled": "未标记",
        "all_groups": "全部组",
        "group_best": "组最佳",
        "grouped_only": "成组",
        "singletons": "单张",
        "group_time": "时间组",
        "group_visual": "相似组",
        "all_pairs": "全部配对",
        "raw_jpeg_pairs": "RAW+JPG",
        "raw_only": "仅 RAW",
        "jpeg_only": "仅 JPG",
        "other_files": "其他文件",
        "all_review_status": "全部深评",
        "reviewed_qwen": "LLM已读",
        "reviewed_concrete": "完整证据",
        "not_reviewed": "未深评",
        "review_failed": "失败/重试",
        "review_skipped": "已跳过",
        "sort_high": "高分优先",
        "sort_low": "低分优先",
        "sort_rank": "排名",
        "sort_name": "文件名",
        "sort_user": "标记优先",
        "no_results": "无结果",
        "review_cockpit": "评审",
        "detail_hint": "选中照片后查看评分、理由和修图参数。",
        "keep": "保留",
        "maybe": "待定",
        "reject": "淘汰",
        "editing_plan": "修图方案",
        "deep_review_selected": "深评选中照片",
        "deep_review_selected_tooltip": "对当前选中的照片运行 LLM 内容深评：人物、故事、构图、瞬间和修图潜力。",
        "deep_review_running": "正在深评选中照片...",
        "deep_review_done": "选中照片深评完成。",
        "deep_review_failed": "选中照片深评失败",
        "selected_actions": "选中照片操作",
        "crop_preview": "裁切预览",
        "crop_preview_tooltip": "查看选中照片在原图上的推荐裁切框和原因。",
        "crop_preview_disabled": "这张照片还没有裁切框；先运行 LLM 深度分析或生成修图方案。",
        "open_output": "打开输出",
        "open_contact": "联系表",
        "empty_grid": "选择目录后开始分析",
        "grid_tooltip": "双击照片打开大图预览",
        "advanced_settings": "高级设置",
        "hide_advanced": "收起高级",
        "review_mode": "筛片模式",
        "show_setup": "展开设置",
        "new_scan": "重新分析",
        "nav_main": "工作流",
        "settings": "设置",
        "hide_settings": "收起设置",
        "nav_run": "运行",
        "nav_view": "工作流",
        "nav_output": "输出",
        "nav_shortcuts": "快捷键",
        "nav_help": "帮助",
        "theme_dark": "暗色",
        "theme_light": "亮色",
        "theme_tooltip": "切换暗色/白天主题",
        "shortcuts_title": "快捷键",
        "shortcuts_hint": "这些快捷键在选片板和详情页生效；输入框、下拉框和设置项获得焦点时不会触发。",
        "shortcut_keep": "保留",
        "shortcut_reject": "淘汰",
        "shortcut_toggle_mark": "标记 / 取消标记",
        "shortcut_maybe": "待定",
        "shortcut_select_all": "全选",
        "shortcut_invert_selection": "反选",
        "reset_shortcuts": "恢复默认",
        "shortcuts_saved": "快捷键已保存。",
        "shortcuts_reset_done": "快捷键已恢复默认。",
        "running_grid": "正在分析，结果会自动出现。",
        "empty_filtered": "没有匹配结果，调整筛选条件。",
        "done": "完成",
        "workflow_done": "✓ 已完成",
        "workflow_active": "正在进行",
        "workflow_idle": "待开始",
        "confirm_run_title": "确认本次分析",
        "confirm_run_start": "开始分析",
        "confirm_run_settings": "返回设置",
        "confirm_run_local": "本地初筛",
        "confirm_run_qwen": "LLM 深度分析 Top-{n}",
        "confirm_run_body": "读取照片目录：{input_dir}\n保存结果目录：{output_dir}\n模式：{mode}\n\n不会移动、覆盖或上传原始 RAW 文件。",
        "running_alive_hint": "仍在运行，较大的 RAW 文件或网络请求可能需要更久",
        "elapsed": "已运行",
        "failed": "失败",
        "closing": "正在等待后台任务安全结束...",
        "missing_input_title": "目录不存在",
        "missing_key_title": "缺少 LLM API 密钥",
        "missing_key_body": "深度分析模式需要 API key。请填入密钥或配置 .env。",
        "qwen_key_local_title": "检测到 LLM API 密钥",
        "qwen_key_local_body": "当前仍是本地快速选片模式，不会调用 API。要切换到 LLM深度分析并只分析 Top-N 候选吗？",
        "qwen_key_local_hint": "已检测到 LLM API 密钥，但当前是本地模式；本次不会调用 API 或深度分析。",
        "local_mode_hint": "本地模式不消耗 token，只做本地快速筛片、RAW/JPG 配对、技术和故事潜力初筛。",
        "llm_setup_missing_hint": "LLM深度分析需要 API key；接口地址和模型可留空自动探测，失败时再手动填写。",
        "input_missing_hint": "请先设置照片目录：选择一个可读取的照片文件夹后再开始分析。",
        "output_folder_hint": "输出目录只是保存报告、缓存预览和修图建议；留默认即可。",
        "startup_config_title": "启动前确认配置",
        "startup_config_body": "请确认本次读取和保存路径：\n读取照片目录：{input_dir}\n保存结果目录：{output_dir}\n\n当前模式：{mode}\n{api_note}\n\n原始 RAW 不会被移动、覆盖；只有选择 LLM 深度分析并配置 API key 时，才会上传 Top-N 压缩预览。",
        "startup_input_missing": "照片目录不存在或未设置，请先选择正确的输入目录。",
        "startup_output_note": "输出目录用于保存报告、缓存预览和修图建议。",
        "startup_api_local_no_key": "你当前没有导入 API key：将按本地模式使用，不会调用 API，也不会深度分析。",
        "startup_api_local_has_key": "已检测到 API key，但当前是本地模式：本次不会调用 API，除非切换到 LLM 深度分析。",
        "startup_api_qwen_missing": "当前选择了 LLM 深度分析，但还没有 API key；请配置 key，或确认改用本地模式。",
        "startup_api_qwen_ready": "LLM 深度分析已配置 API key：只会上传 Top-N 压缩预览，不上传 RAW。",
        "startup_confirm_paths": "确认路径",
        "startup_use_local_no_api": "不导入 API，用本地模式",
        "startup_configure_api": "配置 API",
        "deep_top_tooltip": "深评：把本地筛出的 Top-N 压缩预览交给视觉 LLM，分析内容、构图、故事和编辑潜力，会消耗 token。",
        "advice_top_tooltip": "修图：为选中照片或默认 Top-N 生成 Lightroom/裁切/局部调整方案；优先复用已有深评结果。",
        "qwen_key_promoted": "已切换到 LLM深度分析：只上传 Top-N 压缩预览。",
        "qwen_not_run_local": "本次是本地快速选片，未调用 API。",
        "check_key": "检查",
        "checking_key": "正在检查 LLM API key...",
        "key_check_ok": "密钥检查通过。",
        "key_check_failed": "密钥检查失败",
        "qwen_failures_hint": "LLM深度分析失败：把鼠标停在这里查看原因，或先点击密钥检查。",
        "no_selection": "未选择照片",
        "select_first": "请先选择一张或多张照片。",
        "no_crop_box_title": "暂无裁切框",
        "unmark": "取消标记",
        "no_records": "没有结果",
        "run_first": "请先运行分析。",
    },
    "en": {
        "app_title": "LumaSift - Local AI Photo Curation",
        "hero_title": "LumaSift",
        "hero_subtitle": "Local-first AI photo curation workspace",
        "scanned": "Scanned",
        "shown": "Shown",
        "selected": "Selected",
        "mode": "Mode",
        "local": "Local mode (no token cost)",
        "qwen": "LLM Deep Analysis (API required, uses tokens)",
        "step_import": "1. Import",
        "step_import_caption": "Choose local photo folder",
        "step_local": "2. Pre-score",
        "step_local_caption": "Local preview and fast score",
        "step_qwen": "3. Deep Analysis",
        "step_qwen_caption": "LLM for high-value candidates",
        "step_edit": "4. Edit",
        "step_edit_caption": "Multi-select tuning plan",
        "photo_folder": "Photo folder",
        "output_folder": "Result folder (optional)",
        "browse": "Browse",
        "scan": "Scan",
        "qwen_top": "Deep",
        "advice_top": "Advice",
        "show": "Show",
        "qwen_keys": "LLM API",
        "vision_base_url": "Base URL",
        "vision_model": "Model",
        "vision_base_url_placeholder": "Leave empty to use the default endpoint",
        "vision_model_placeholder": "Leave empty to auto-detect the best vision model",
        "api_placeholder": "Optional: enter one LLM API key. Leave empty to use .env.",
        "save_keys": "Save keys locally",
        "cache_note": "Deep mode uploads only Top-N compressed previews; RAW stays local. OpenAI-compatible vision endpoints are supported.",
        "analyze": "Analyze",
        "cancel": "Cancel",
        "ready": "Ready",
        "review_board": "Review board",
        "search": "Search filename/category/style",
        "all_categories": "All categories",
        "all_tones": "All tones",
        "tone_monochrome_or_near_bw": "Near B&W",
        "tone_high_contrast": "High contrast",
        "tone_low_key": "Low key",
        "tone_high_key": "High key",
        "tone_warm_tone": "Warm",
        "tone_cool_tone": "Cool",
        "tone_vivid_color": "Vivid",
        "tone_muted_color": "Muted",
        "all_labels": "All labels",
        "unlabeled": "unlabeled",
        "all_groups": "All groups",
        "group_best": "Group best",
        "grouped_only": "Grouped",
        "singletons": "Singles",
        "group_time": "Time groups",
        "group_visual": "Similar groups",
        "all_pairs": "All pairs",
        "raw_jpeg_pairs": "RAW+JPG",
        "raw_only": "RAW only",
        "jpeg_only": "JPG only",
        "other_files": "Other files",
        "all_review_status": "All review",
        "reviewed_qwen": "LLM-read",
        "reviewed_concrete": "Concrete read",
        "not_reviewed": "Not reviewed",
        "review_failed": "Failed/retry",
        "review_skipped": "Skipped",
        "sort_high": "Score high to low",
        "sort_low": "Score low to high",
        "sort_rank": "Rank",
        "sort_name": "Filename A-Z",
        "sort_user": "Label priority",
        "no_results": "No results",
        "review_cockpit": "Review",
        "detail_hint": "Select photos to inspect scores, reasons, and editing parameters.",
        "keep": "Keep",
        "maybe": "Maybe",
        "reject": "Reject",
        "editing_plan": "Editing Plan",
        "deep_review_selected": "Deep Review Selected",
        "deep_review_selected_tooltip": "Run LLM content analysis for the selected photo: people, story, composition, moment, and editing potential.",
        "deep_review_running": "Deep-reviewing selected photo...",
        "deep_review_done": "Selected photo deep review complete.",
        "deep_review_failed": "Selected photo deep review failed",
        "selected_actions": "Selected Photo Actions",
        "crop_preview": "Crop Preview",
        "crop_preview_tooltip": "Show the recommended crop box and rationale on the original composition.",
        "crop_preview_disabled": "No crop box yet. Run LLM Deep Analysis or generate an editing plan first.",
        "open_output": "Open Output",
        "open_contact": "Contact Sheet",
        "empty_grid": "Choose a folder, then analyze",
        "grid_tooltip": "Double-click a photo to open the large preview",
        "advanced_settings": "Advanced",
        "hide_advanced": "Hide Advanced",
        "review_mode": "Review Mode",
        "show_setup": "Show Setup",
        "new_scan": "Analyze Again",
        "nav_main": "Workflow",
        "settings": "Settings",
        "hide_settings": "Hide Settings",
        "nav_run": "Run",
        "nav_view": "Workflow",
        "nav_output": "Output",
        "nav_shortcuts": "Shortcuts",
        "nav_help": "Help",
        "theme_dark": "Dark",
        "theme_light": "Light",
        "theme_tooltip": "Switch dark/light theme",
        "shortcuts_title": "Shortcuts",
        "shortcuts_hint": "These shortcuts work on the review board and detail panel. They are ignored while typing or editing settings.",
        "shortcut_keep": "Keep",
        "shortcut_reject": "Reject",
        "shortcut_toggle_mark": "Mark / unmark",
        "shortcut_maybe": "Maybe",
        "shortcut_select_all": "Select all",
        "shortcut_invert_selection": "Invert selection",
        "reset_shortcuts": "Reset Defaults",
        "shortcuts_saved": "Shortcuts saved.",
        "shortcuts_reset_done": "Shortcuts reset to defaults.",
        "running_grid": "Analysis is running. Results will appear here.",
        "empty_filtered": "No matches. Adjust filters.",
        "done": "Done",
        "workflow_done": "✓ Done",
        "workflow_active": "Running",
        "workflow_idle": "Pending",
        "confirm_run_title": "Confirm This Analysis",
        "confirm_run_start": "Start Analysis",
        "confirm_run_settings": "Back to Settings",
        "confirm_run_local": "Local pre-score",
        "confirm_run_qwen": "LLM Deep Analysis Top-{n}",
        "confirm_run_body": "Read photo folder: {input_dir}\nSave results to: {output_dir}\nMode: {mode}\n\nOriginal RAW files will not be moved, overwritten, or uploaded.",
        "running_alive_hint": "Still running. Large RAW files or network requests can take longer.",
        "elapsed": "Elapsed",
        "failed": "Failed",
        "closing": "Waiting for background tasks to stop safely...",
        "missing_input_title": "Input folder missing",
        "missing_key_title": "LLM API key missing",
        "missing_key_body": "Deep analysis mode requires API keys. Enter keys or configure .env.",
        "qwen_key_local_title": "LLM API key detected",
        "qwen_key_local_body": "The current mode is still local fast culling, so no API call will run. Switch to LLM Deep Analysis for Top-N candidates?",
        "qwen_key_local_hint": "LLM API key detected, but the current mode is Local. This run will not call APIs or deep-review.",
        "local_mode_hint": "Local mode does not use tokens. It only runs local fast culling, RAW/JPG pairing, technical checks, and story-potential pre-scoring.",
        "llm_setup_missing_hint": "LLM Deep Analysis needs an API key. Base URL and model can stay empty for auto-probing; fill them manually only if probing fails.",
        "input_missing_hint": "Set the photo folder first. Choose a readable folder before analysis.",
        "output_folder_hint": "The result folder only stores reports, preview cache, and editing advice. The default is fine.",
        "startup_config_title": "Confirm Setup Before Launch",
        "startup_config_body": "Confirm the folders for this run:\nRead photo folder: {input_dir}\nSave results to: {output_dir}\n\nCurrent mode: {mode}\n{api_note}\n\nOriginal RAW files will not be moved or overwritten. Top-N compressed previews are uploaded only when LLM Deep Analysis is selected and an API key is configured.",
        "startup_input_missing": "The photo folder is missing or not set. Choose the correct input folder first.",
        "startup_output_note": "The result folder stores reports, preview cache, and editing advice.",
        "startup_api_local_no_key": "No API key is imported: the app will stay in Local mode, with no API calls or deep analysis.",
        "startup_api_local_has_key": "An API key is detected, but the current mode is Local: no API call will run unless you switch to LLM Deep Analysis.",
        "startup_api_qwen_missing": "LLM Deep Analysis is selected but no API key is configured. Configure a key, or confirm Local mode.",
        "startup_api_qwen_ready": "LLM Deep Analysis has an API key configured. Only Top-N compressed previews are uploaded; RAW files stay local.",
        "startup_confirm_paths": "Confirm Folders",
        "startup_use_local_no_api": "No API, Use Local",
        "startup_configure_api": "Configure API",
        "deep_top_tooltip": "Deep: send Top-N compressed previews to a vision LLM for content, composition, story, and editing-potential analysis. This uses tokens.",
        "advice_top_tooltip": "Edit: generate Lightroom, crop, and local-adjustment plans for selected photos or the default Top-N, reusing deep-analysis results when available.",
        "qwen_key_promoted": "Switched to LLM Deep Analysis. Only Top-N compressed previews will be uploaded.",
        "qwen_not_run_local": "This was a local fast-culling run. No API was called.",
        "check_key": "Check",
        "checking_key": "Checking LLM API key...",
        "key_check_ok": "Key check passed.",
        "key_check_failed": "Key check failed",
        "qwen_failures_hint": "LLM Deep Analysis failed. Hover here for the reason, or check the API key first.",
        "no_selection": "No selection",
        "select_first": "Select one or more photos first.",
        "no_crop_box_title": "No crop box yet",
        "unmark": "Unmark",
        "no_records": "No records",
        "run_first": "Run an analysis first.",
    },
}


PREFERRED_UI_FONTS = [
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "SimHei",
    "PingFang SC",
    "Arial Unicode MS",
    "Segoe UI",
]

WINDOWS_UI_FONT_FILES = [
    Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc",
    Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyhbd.ttc",
    Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "simhei.ttf",
]


def preferred_ui_font_family() -> str:
    for font_file in WINDOWS_UI_FONT_FILES:
        if font_file.exists():
            QFontDatabase.addApplicationFont(str(font_file))
    available = set(QFontDatabase.families())
    for family in PREFERRED_UI_FONTS:
        if family in available:
            return family
    return QApplication.font().family()


def apply_application_font(app: QApplication) -> str:
    family = preferred_ui_font_family()
    font = QFont(family, 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)
    return family


def crash_log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home()
    path = root / "LumaSift" / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def install_crash_logging() -> None:
    log_path = crash_log_dir() / "crash.log"
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    def excepthook(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n--- unhandled exception ---\n")
            traceback.print_exception(exc_type, exc, tb, file=handle)
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = excepthook


class AnalysisWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)
    progress = Signal(str, int, int)
    qwen_event = Signal(dict)

    def __init__(self, settings: Settings, run_id: str, state_db_path: Path | None = None) -> None:
        super().__init__()
        self.settings = settings
        self.run_id = run_id
        self.state_db_path = state_db_path

    def run(self) -> None:
        try:
            configure_logging(self.settings.output_dir)
            if self.settings.ai_mode == "qwen_vision":
                capability = _verified_vision_capability(
                    self.settings,
                    timeout_seconds=min(20, max(5, self.settings.request_timeout_seconds)),
                )
                _apply_verified_vision_capability(self.settings, capability)
                self.qwen_event.emit(
                    {
                        "type": "qwen_vision_verified",
                        "model": self.settings.vision_model,
                        "base_url": self.settings.vision_api_base_url,
                    }
                )
            result = LumaSiftHarness(
                settings=self.settings,
                run_id=self.run_id,
                progress_callback=lambda stage, current, total: self.progress.emit(stage, current, total),
                event_callback=lambda event: self.qwen_event.emit(event),
                state_db=LumaSiftStateDb(self.state_db_path) if self.state_db_path else None,
            ).run()
            report = json.loads(result.report_json.read_text(encoding="utf-8"))
            self.finished.emit({"summary": result.summary, "report": report, "output_dir": str(self.settings.output_dir)})
        except Exception as exc:  # noqa: BLE001 - GUI must show failures instead of crashing.
            logging.exception("Analysis failed")
            self.failed.emit(str(exc))


class VisionKeyCheckWorker(QObject):
    finished = Signal(str, str, str)
    failed = Signal(str)

    def __init__(self, api_keys: list[str], language: str, base_url: str, preferred_model: str) -> None:
        super().__init__()
        self.api_keys = api_keys
        self.language = language
        self.base_url = base_url
        self.preferred_model = preferred_model

    def run(self) -> None:
        try:
            capabilities = query_vision_model_capabilities(
                self.api_keys,
                base_url=self.base_url,
                preferred_model=self.preferred_model,
                timeout_seconds=20,
            )
            detected_base_url = next((capability.base_url for capability in capabilities if capability.base_url), self.base_url)
            self.finished.emit(
                format_vision_model_summary(capabilities, language=self.language),
                recommended_vision_model(capabilities),
                detected_base_url,
            )
        except Exception as exc:  # noqa: BLE001 - GUI should surface provider failures.
            self.failed.emit(str(exc))


def _preferred_vision_model(settings: Settings) -> str:
    model = _clean_vision_model_override(settings.vision_model)
    if model in {"qwen3.6-plus", "qwen3.5-plus"}:
        return ""
    return model if model else ""


def _verified_vision_capability(settings: Settings, *, timeout_seconds: int = 20) -> VisionModelCapability:
    capabilities = query_vision_model_capabilities(
        settings.vision_api_keys,
        base_url=_vision_base_url_override(settings.vision_api_base_url),
        preferred_model=_preferred_vision_model(settings),
        timeout_seconds=timeout_seconds,
    )
    for capability in capabilities:
        if capability.supports_vision and capability.model:
            return capability
    raise RuntimeError("No model passed the live image-vision probe")


def _apply_verified_vision_capability(settings: Settings, capability: VisionModelCapability) -> None:
    settings.vision_api_base_url = _clean_vision_base_url(capability.base_url or settings.vision_api_base_url)
    settings.vision_model = _clean_vision_model_override(capability.model) or settings.vision_model


class SelectedDeepReviewWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, record: dict[str, Any], settings: Settings, output_dir: Path) -> None:
        super().__init__()
        self.record = dict(record)
        self.settings = settings
        self.output_dir = output_dir

    def run(self) -> None:
        try:
            self.progress.emit("vision_check")
            capability = _verified_vision_capability(
                self.settings,
                timeout_seconds=min(20, max(5, self.settings.request_timeout_seconds)),
            )
            _apply_verified_vision_capability(self.settings, capability)
            self.progress.emit("preview")
            preview_path = create_jpeg_preview(
                Path(str(self.record["path"])),
                self.output_dir / "previews",
                max_side=self.settings.vision_preview_max_side,
            )
            self.record["preview_path"] = str(preview_path)
            client = QwenVisionClient(
                base_url=self.settings.vision_api_base_url,
                model=self.settings.vision_model,
                keyring=ApiKeyRing(self.settings.vision_api_keys),
                max_tokens=self.settings.vision_max_tokens,
                timeout_seconds=self.settings.request_timeout_seconds,
                max_retries=self.settings.vision_max_retries,
                response_validator=validate_qwen_story_response,
            )
            self.progress.emit("deep_review")
            response = client.analyze_image(
                preview_path,
                build_qwen_story_prompt(self.record),
                prompt_version=QWEN_STORY_PROMPT_VERSION,
            )
            merge_qwen_story_analysis(self.record, response)
            self.record["qwen_status"] = "cache-hit" if client.last_cache_hit else "done"
            self.record["qwen_prompt_version"] = QWEN_STORY_PROMPT_VERSION
            if client.last_cache_key_digest:
                self.record["qwen_cache_key"] = client.last_cache_key_digest
            self.finished.emit(self.record)
        except Exception as exc:  # noqa: BLE001 - surface selected-photo failures in the GUI.
            logging.exception("Selected deep review failed")
            self.failed.emit(str(exc))


class ThumbnailWorker(QObject):
    thumbnail_ready = Signal(int, int, str)
    finished = Signal()

    def __init__(self, jobs: list[tuple[int, dict[str, Any]]], output_dir: Path, generation: int, max_side: int = 360) -> None:
        super().__init__()
        self.jobs = jobs
        self.output_dir = output_dir
        self.generation = generation
        self.max_side = max_side
        self.cancelled = False

    def stop(self) -> None:
        self.cancelled = True

    def run(self) -> None:
        preview_dir = self.output_dir / "gui_previews"
        for row, record in self.jobs:
            if self.cancelled:
                break
            try:
                preview_path = create_jpeg_preview(Path(record["path"]), preview_dir, max_side=self.max_side)
                self.thumbnail_ready.emit(self.generation, row, str(preview_path))
            except Exception:
                self.thumbnail_ready.emit(self.generation, row, "")
        self.finished.emit()


class LargePreviewWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, path: Path, output_dir: Path, max_side: int = 2400) -> None:
        super().__init__()
        self.path = path
        self.output_dir = output_dir
        self.max_side = max_side

    def run(self) -> None:
        try:
            preview_dir = self.output_dir / "large_previews"
            preview_path = create_jpeg_preview(self.path, preview_dir, max_side=self.max_side)
            self.finished.emit(str(preview_path))
        except Exception as exc:  # noqa: BLE001 - preview failure should stay inside the dialog.
            logging.exception("Large preview failed for %s", self.path)
            self.failed.emit(str(exc))


class LargePreviewDialog(QDialog):
    def __init__(self, record: dict[str, Any], output_dir: Path, language: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.record = record
        self.output_dir = output_dir
        self.language = language if language in {"zh", "en"} else "zh"
        self.preview_thread: QThread | None = None
        self.preview_worker: LargePreviewWorker | None = None
        self.original_pixmap: QPixmap | None = None
        self.crop_box = _record_crop_box(record)
        self.crop_reason = _record_crop_reason(record) if self.crop_box else ""
        self.fit_to_window = True
        self.zoom_factor = 1.0
        self.pending_close = False

        filename = str(record.get("filename") or Path(str(record.get("path", ""))).name)
        title = f"大图预览 - {filename}" if self.language == "zh" else f"Large Preview - {filename}"
        self.setWindowTitle(title)
        self.setObjectName("largePreviewDialog")
        self.resize(1280, 860)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QFrame()
        header.setObjectName("previewHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(8)
        title_label = QLabel(filename)
        title_label.setObjectName("sectionTitle")
        self.status_label = QLabel("正在生成 RAW 预览..." if self.language == "zh" else "Generating RAW preview...")
        self.status_label.setObjectName("muted")
        self.fit_button = QPushButton("适应窗口" if self.language == "zh" else "Fit")
        self.fit_button.setObjectName("secondaryButton")
        self.fit_button.clicked.connect(self._fit)
        self.actual_button = QPushButton("100%")
        self.actual_button.setObjectName("secondaryButton")
        self.actual_button.clicked.connect(self._actual_size)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("zoomLabel")
        self.zoom_label.setMinimumWidth(58)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title_label, stretch=1)
        header_layout.addWidget(self.status_label)
        header_layout.addWidget(self.fit_button)
        header_layout.addWidget(self.actual_button)
        header_layout.addWidget(self.zoom_label)
        layout.addWidget(header)

        self.image_label = QLabel("加载中..." if self.language == "zh" else "Loading...")
        self.image_label.setObjectName("previewImage")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(640, 420)
        self.image_label.setScaledContents(False)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("previewScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.viewport().installEventFilter(self)
        self.image_label.installEventFilter(self)
        layout.addWidget(self.scroll_area, stretch=1)

        self.crop_note_label = QLabel("")
        self.crop_note_label.setObjectName("cropOverlayNote")
        self.crop_note_label.setWordWrap(True)
        if self.crop_box:
            prefix = "LLM裁切建议" if self.language == "zh" else "LLM crop suggestion"
            self.crop_note_label.setText(f"{prefix}: {self.crop_reason or ('按框内主体关系裁切' if self.language == 'zh' else 'Crop to the visible subject relationship')}")
            self.crop_note_label.setToolTip(self.crop_note_label.text())
        else:
            self.crop_note_label.hide()
        layout.addWidget(self.crop_note_label)

        self.setStyleSheet(
            """
            QDialog#largePreviewDialog { background: #0f172a; color: #e5edf7; }
            QFrame#previewHeader {
                background: #111827;
                border: 1px solid #263244;
                border-radius: 8px;
            }
            QLabel#sectionTitle { font-size: 14px; font-weight: 800; color: #f8fafc; }
            QLabel#muted { color: #94a3b8; }
            QLabel#zoomLabel {
                background: #233044;
                border-radius: 6px;
                color: #f8fafc;
                font-weight: 800;
                padding: 7px 9px;
            }
            QLabel#previewImage {
                background: #020617;
                color: #94a3b8;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
            QScrollArea#previewScrollArea {
                background: #020617;
                border: none;
            }
            QLabel#cropOverlayNote {
                background: #111827;
                border: 1px solid #334155;
                border-left: 5px solid #ffd400;
                border-radius: 8px;
                color: #e5edf7;
                padding: 8px 10px;
            }
            QPushButton {
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                font-weight: 800;
            }
            QPushButton#secondaryButton { background: #233044; color: #f8fafc; }
            QPushButton#secondaryButton:hover { background: #334155; }
            """
        )

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if (obj is self.scroll_area.viewport() or obj is self.image_label) and event.type() == QEvent.Type.Wheel and self.original_pixmap is not None:
            delta = event.angleDelta().y() if hasattr(event, "angleDelta") else 0
            if delta:
                self._zoom_by(1.15 if delta > 0 else 1 / 1.15)
                event.accept()
                return True
        return super().eventFilter(obj, event)

    def showEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if self.preview_thread is None and self.original_pixmap is None:
            QTimer.singleShot(0, self._start_load)

    def resizeEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if self.fit_to_window:
            self._apply_fit()

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        if self.preview_thread is not None and self.preview_thread.isRunning():
            event.ignore()
            self.pending_close = True
            self.status_label.setText("预览生成中，完成后关闭..." if self.language == "zh" else "Preview is loading. Closing after it finishes...")
            return
        super().closeEvent(event)

    def _start_load(self) -> None:
        path = Path(str(self.record.get("path", "")))
        self.preview_thread = QThread()
        self.preview_worker = LargePreviewWorker(path, self.output_dir, max_side=2400)
        self.preview_worker.moveToThread(self.preview_thread)
        self.preview_thread.started.connect(self.preview_worker.run)
        self.preview_worker.finished.connect(self._load_finished)
        self.preview_worker.failed.connect(self._load_failed)
        self.preview_worker.finished.connect(self.preview_thread.quit)
        self.preview_worker.failed.connect(self.preview_thread.quit)
        self.preview_thread.finished.connect(self._thread_finished)
        self.preview_thread.finished.connect(self.preview_thread.deleteLater)
        self.preview_thread.start()

    def _load_finished(self, preview_path: str) -> None:
        pixmap = QPixmap(preview_path)
        if pixmap.isNull():
            self._load_failed("Cannot decode generated preview.")
            return
        self.original_pixmap = pixmap
        size_text = f"{pixmap.width()} x {pixmap.height()}"
        self.status_label.setText(size_text)
        self._fit()

    def _load_failed(self, message: str) -> None:
        text = f"预览失败：{message}" if self.language == "zh" else f"Preview failed: {message}"
        self.status_label.setText(text)
        self.image_label.setText(text)

    def _thread_finished(self) -> None:
        self.preview_worker = None
        self.preview_thread = None
        if self.pending_close:
            QTimer.singleShot(0, self.close)

    def _fit(self) -> None:
        self.fit_to_window = True
        self._apply_fit()

    def _actual_size(self) -> None:
        if self.original_pixmap is None:
            return
        self._set_zoom_factor(1.0)

    def _apply_fit(self) -> None:
        if self.original_pixmap is None:
            return
        self.scroll_area.setWidgetResizable(True)
        available = self.scroll_area.viewport().size() - QSize(24, 24)
        if available.width() <= 0 or available.height() <= 0:
            return
        scaled = self.original_pixmap.scaled(
            available,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.zoom_factor = scaled.width() / max(1, self.original_pixmap.width())
        self._update_zoom_label()
        self.image_label.setPixmap(self._pixmap_with_crop_overlay(scaled))
        self.image_label.resize(scaled.size())

    def _zoom_by(self, multiplier: float) -> None:
        if self.original_pixmap is None:
            return
        base = self.zoom_factor if not self.fit_to_window else max(self.zoom_factor, 0.1)
        self._set_zoom_factor(base * multiplier)

    def _set_zoom_factor(self, factor: float) -> None:
        if self.original_pixmap is None:
            return
        factor = max(0.08, min(4.0, factor))
        old_size = self.image_label.size()
        viewport = self.scroll_area.viewport().size()
        hbar = self.scroll_area.horizontalScrollBar()
        vbar = self.scroll_area.verticalScrollBar()
        rel_x = (hbar.value() + viewport.width() / 2) / max(1, old_size.width())
        rel_y = (vbar.value() + viewport.height() / 2) / max(1, old_size.height())

        self.fit_to_window = False
        self.zoom_factor = factor
        self.scroll_area.setWidgetResizable(False)
        target_size = QSize(
            max(1, int(round(self.original_pixmap.width() * factor))),
            max(1, int(round(self.original_pixmap.height() * factor))),
        )
        scaled = self.original_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(self._pixmap_with_crop_overlay(scaled))
        self.image_label.resize(scaled.size())
        hbar.setValue(max(0, int(rel_x * scaled.width() - viewport.width() / 2)))
        vbar.setValue(max(0, int(rel_y * scaled.height() - viewport.height() / 2)))
        self._update_zoom_label()

    def _update_zoom_label(self) -> None:
        if hasattr(self, "zoom_label"):
            self.zoom_label.setText(f"{max(1, int(round(self.zoom_factor * 100)))}%")

    def _pixmap_with_crop_overlay(self, pixmap: QPixmap) -> QPixmap:
        if not self.crop_box or pixmap.isNull():
            return pixmap
        width = pixmap.width()
        height = pixmap.height()
        crop = QRect(
            int(round(self.crop_box["x"] * width)),
            int(round(self.crop_box["y"] * height)),
            int(round(self.crop_box["width"] * width)),
            int(round(self.crop_box["height"] * height)),
        ).intersected(QRect(0, 0, width, height))
        if crop.width() < 8 or crop.height() < 8:
            return pixmap

        rendered = QPixmap(pixmap)
        painter = QPainter(rendered)
        overlay = QColor(2, 6, 23, 150)
        painter.fillRect(QRect(0, 0, width, crop.top()), overlay)
        painter.fillRect(QRect(0, crop.bottom() + 1, width, height - crop.bottom() - 1), overlay)
        painter.fillRect(QRect(0, crop.top(), crop.left(), crop.height()), overlay)
        painter.fillRect(QRect(crop.right() + 1, crop.top(), width - crop.right() - 1, crop.height()), overlay)

        border_width = max(2, int(round(min(width, height) * 0.004)))
        painter.setPen(QPen(QColor("#ffd400"), border_width))
        painter.drawRect(crop.adjusted(border_width // 2, border_width // 2, -border_width // 2, -border_width // 2))

        guide = max(18, int(round(min(crop.width(), crop.height()) * 0.09)))
        painter.setPen(QPen(QColor("#f8fafc"), max(2, border_width - 1)))
        left = crop.left()
        right = crop.right()
        top = crop.top()
        bottom = crop.bottom()
        painter.drawLine(left, top, left + guide, top)
        painter.drawLine(left, top, left, top + guide)
        painter.drawLine(right, top, right - guide, top)
        painter.drawLine(right, top, right, top + guide)
        painter.drawLine(left, bottom, left + guide, bottom)
        painter.drawLine(left, bottom, left, bottom - guide)
        painter.drawLine(right, bottom, right - guide, bottom)
        painter.drawLine(right, bottom, right, bottom - guide)
        painter.end()
        return rendered


class PhotoListModel(QAbstractListModel):
    def __init__(self, placeholder_icon: QIcon) -> None:
        super().__init__()
        self.records: list[dict[str, Any]] = []
        self.icons: dict[int, QIcon] = {}
        self.placeholder_icon = placeholder_icon
        self.empty_message = "Drop into the workflow by choosing a folder, then run analysis."
        self.language = "zh"
        self.category_labels = {
            "zh": {
                "portfolio_candidate": "作品候选",
                "strong_edit_candidate": "强修图候选",
                "story_candidate": "故事候选",
                "technically_weak_but_interesting": "技术弱但有趣",
                "ordinary_record": "普通记录",
                "reject_candidate": "淘汰候选",
                "failed": "失败",
            },
            "en": {},
        }
        self.user_label_labels = {
            "zh": {"keep": "保留", "maybe": "待定", "reject": "淘汰", "unlabeled": "未标记"},
            "en": {},
        }
        self.style_labels = {
            "zh": {
                "high_contrast_bw": "高反差黑白",
                "soft_documentary_color": "柔和纪实彩色",
                "cinematic_warm": "电影暖调",
                "cold_urban": "冷调城市",
                "low_key_noir": "低调暗黑",
                "natural_editorial": "自然纪实",
                "do_not_overedit": "克制修图",
            },
            "en": {},
        }
        self.pair_status_labels = {
            "zh": {"raw_jpeg_pair": "RAW+JPG", "raw_only": "仅RAW", "jpeg_only": "仅JPG", "single": "单文件"},
            "en": {"raw_jpeg_pair": "RAW+JPG", "raw_only": "RAW only", "jpeg_only": "JPG only", "single": "single"},
        }

    def set_language(self, language: str) -> None:
        self.language = language if language in {"zh", "en"} else "zh"
        if self.records:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self.records) - 1, 0)
            self.dataChanged.emit(top_left, bottom_right, [int(Qt.ItemDataRole.DisplayRole)])

    def _display_value(self, value: Any, mapping: dict[str, dict[str, str]]) -> str:
        raw = str(value or "")
        if not raw:
            return ""
        translated = mapping.get(self.language, {}).get(raw)
        if translated:
            return translated
        return raw.replace("_", " ")

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802 - Qt API
        if parent.isValid():
            return 0
        return len(self.records) if self.records else 1

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> Any:
        if not index.isValid():
            return None
        row = index.row()
        if not self.records:
            if role == int(Qt.ItemDataRole.DisplayRole):
                return self.empty_message
            return None
        if row < 0 or row >= len(self.records):
            return None
        record = self.records[row]
        if role == int(Qt.ItemDataRole.UserRole):
            return record
        if role == int(Qt.ItemDataRole.DecorationRole):
            return self.icons.get(row, self.placeholder_icon)
        if role == int(Qt.ItemDataRole.DisplayRole):
            score = float(record.get("final_selection_score", 0) or 0)
            category = self._display_value(record.get("category", ""), self.category_labels)
            user_label = self._display_value(record.get("user_label", "") or "unlabeled", self.user_label_labels)
            group_badge = ""
            group_size = int(record.get("group_size", 1) or 1)
            if group_size > 1:
                group_badge = f"  G{group_size}{'*' if record.get('is_group_best') else ''}"
            pair_status = self._display_value(record.get("pair_status", ""), self.pair_status_labels)
            pair_badge = f"  {pair_status}" if pair_status else ""
            return f"#{record.get('rank')}  {score:.1f}  {user_label}{group_badge}{pair_badge}\n{record.get('filename')}\n{category}"
        if role == int(Qt.ItemDataRole.ToolTipRole):
            return str(record.get("path", ""))
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid() or not self.records:
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def set_records(self, records: list[dict[str, Any]], empty_message: str | None = None) -> None:
        self.beginResetModel()
        self.records = records
        self.icons.clear()
        if empty_message:
            self.empty_message = empty_message
        self.endResetModel()

    def set_icon(self, row: int, icon: QIcon) -> None:
        if row < 0 or row >= len(self.records):
            return
        self.icons[row] = icon
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [int(Qt.ItemDataRole.DecorationRole)])

    def refresh_row(self, row: int) -> None:
        if row < 0 or row >= len(self.records):
            return
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [int(Qt.ItemDataRole.DisplayRole), int(Qt.ItemDataRole.UserRole)])


class PhotoCardDelegate(QStyledItemDelegate):
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802 - Qt API
        if not index.data(Qt.ItemDataRole.UserRole):
            return QSize(360, 120)
        return QSize(238, 246)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        record = index.data(Qt.ItemDataRole.UserRole)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(4, 4, -4, -4)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        light = bool(option.widget and option.widget.property("theme") == "light")
        palette = (
            {
                "muted": "#6b7280",
                "border": "#e6e8ee",
                "hover_border": "#d1d5db",
                "selected_border": "#5e6ad2",
                "card": "#ffffff",
                "hover_card": "#f7f8fb",
                "selected_card": "#f1f3ff",
                "image_border": "#d7dce5",
                "title": "#111827",
                "rank_bg": "#5e6ad2",
                "rank_fg": "#ffffff",
                "score_bg": "#eef2ff",
                "score_fg": "#3f46a3",
                "group_bg": "#eef0f4",
                "group_fg": "#4b5563",
                "category_bg": "#f2f4f8",
                "category_fg": "#5e6ad2",
            }
            if light
            else {
                "muted": "#8fa4b8",
                "border": "#26313d",
                "hover_border": "#36506a",
                "selected_border": "#00a6ff",
                "card": "#10161d",
                "hover_card": "#121922",
                "selected_card": "#172232",
                "image_border": "#314154",
                "title": "#f8fafc",
                "rank_bg": "#00a6ff",
                "rank_fg": "#061019",
                "score_bg": "#ffd400",
                "score_fg": "#111827",
                "group_bg": "#31415a",
                "group_fg": "#dbe7f3",
                "category_bg": "#1e2b3a",
                "category_fg": "#9fd7ff",
            }
        )

        if not isinstance(record, dict):
            painter.setPen(QColor(palette["muted"]))
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap), str(index.data(Qt.ItemDataRole.DisplayRole) or ""))
            painter.restore()
            return

        painter.setPen(QColor(palette["selected_border"] if selected else palette["hover_border"] if hovered else palette["border"]))
        painter.setBrush(QColor(palette["selected_card"] if selected else palette["hover_card"] if hovered else palette["card"]))
        painter.drawRoundedRect(rect, 8, 8)

        image_rect = QRect(rect.left() + 14, rect.top() + 12, rect.width() - 28, 112)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        pixmap = icon.pixmap(image_rect.size()) if isinstance(icon, QIcon) else QPixmap()
        if not pixmap.isNull():
            scaled = pixmap.scaled(image_rect.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            x = image_rect.left() + (image_rect.width() - scaled.width()) // 2
            y = image_rect.top() + (image_rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.setPen(QColor(palette["image_border"]))
            painter.drawRect(image_rect)

        rank = str(record.get("rank") or "-")
        score = float(record.get("final_selection_score", 0) or 0)
        user_label_raw = normalized_user_label(record.get("user_label")) or "unlabeled"
        filename = str(record.get("filename") or "")
        category = self._localized(index, record.get("category", ""), "category_labels")
        tone = self._tone_label(index, record.get("tone_category", ""))
        user_label = self._localized(index, user_label_raw, "user_label_labels")
        group_size = int(record.get("group_size", 1) or 1)
        group_rank = int(record.get("group_rank", 1) or 1)
        if self._language(index) == "zh":
            group_text = f"组 {group_rank}/{group_size}{' 最佳' if record.get('is_group_best') else ''}" if group_size > 1 else ""
        else:
            group_text = f"Group {group_rank}/{group_size}{' best' if record.get('is_group_best') else ''}" if group_size > 1 else ""
        pair_text = self._localized(index, record.get("pair_status", ""), "pair_status_labels")

        max_right = rect.right() - 12
        tag_y = image_rect.bottom() + 8
        x = rect.left() + 12
        x = self._draw_tag(painter, x, tag_y, f"#{rank}", palette["rank_bg"], palette["rank_fg"], max_right=max_right)
        x = self._draw_tag(painter, x + 6, tag_y, f"{score:.1f}", palette["score_bg"], palette["score_fg"], max_right=max_right)
        self._draw_tag(
            painter,
            x + 6,
            tag_y,
            user_label,
            self._label_color(user_label_raw, light=light),
            "#ffffff" if light or user_label_raw == "reject" else "#061019",
            max_right=max_right,
        )
        meta_y = tag_y + 28
        x = rect.left() + 12
        if group_text:
            x = self._draw_tag(painter, x, meta_y, group_text, palette["group_bg"], palette["group_fg"], max_right=max_right)
        if pair_text:
            self._draw_tag(
                painter,
                x + (6 if group_text else 0),
                meta_y,
                pair_text,
                "#eaf7f1" if light and record.get("has_raw_jpeg_pair") else "#fff7ed" if light else "#1f3b2f" if record.get("has_raw_jpeg_pair") else "#3b2f1f",
                "#166534" if light and record.get("has_raw_jpeg_pair") else "#9a3412" if light else "#dbe7f3",
                max_right=max_right,
            )

        painter.setPen(QColor(palette["title"]))
        file_font = QFont(option.font)
        file_font.setBold(True)
        painter.setFont(file_font)
        filename_rect = QRect(rect.left() + 12, tag_y + 57, rect.width() - 24, 20)
        painter.drawText(filename_rect, int(Qt.AlignmentFlag.AlignCenter), painter.fontMetrics().elidedText(filename, Qt.TextElideMode.ElideMiddle, filename_rect.width()))
        category_y = tag_y + 83
        if category:
            x = self._draw_tag(painter, rect.left() + 12, category_y, category, palette["category_bg"], palette["category_fg"], max_right=max_right)
            if tone:
                self._draw_tag(painter, x + 6, category_y, tone, palette["group_bg"], palette["group_fg"], max_right=max_right)
        elif tone:
            self._draw_tag(painter, rect.left() + 12, category_y, tone, palette["group_bg"], palette["group_fg"], max_right=max_right)
        painter.restore()

    def _localized(self, index: QModelIndex, value: Any, mapping_name: str) -> str:
        model = index.model()
        mapping = getattr(model, mapping_name, None)
        display = getattr(model, "_display_value", None)
        if callable(display) and isinstance(mapping, dict):
            return str(display(value, mapping))
        return str(value or "").replace("_", " ")

    def _language(self, index: QModelIndex) -> str:
        return str(getattr(index.model(), "language", "zh") or "zh")

    def _tone_label(self, index: QModelIndex, value: Any) -> str:
        raw = str(value or "")
        if not raw:
            return ""
        if self._language(index) == "zh":
            return {
                "monochrome_or_near_bw": "近黑白",
                "high_contrast": "高反差",
                "low_key": "低调",
                "high_key": "高调",
                "warm_tone": "暖调",
                "cool_tone": "冷调",
                "vivid_color": "高饱和",
                "muted_color": "低饱和",
            }.get(raw, raw.replace("_", " "))
        return raw.replace("_", " ")

    def _draw_tag(self, painter: QPainter, x: int, y: int, text: str, bg: str, fg: str, *, max_right: int | None = None) -> int:
        if max_right is not None and x > max_right - 24:
            return x
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSize(max(8, font.pointSize()))
        painter.setFont(font)
        metrics = painter.fontMetrics()
        available = None if max_right is None else max(30, max_right - x)
        rendered_text = text
        raw_width = metrics.horizontalAdvance(text) + 16
        if available is not None and raw_width > available:
            rendered_text = metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(12, available - 16))
        width = min(raw_width, available) if available is not None else raw_width
        rect = QRect(x, y, width, 22)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(rect, 6, 6)
        painter.setPen(QColor(fg))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), rendered_text)
        return x + width

    def _label_color(self, label: str, *, light: bool = False) -> str:
        if light:
            return {
                "keep": "#5e6ad2",
                "maybe": "#8b5cf6",
                "reject": "#ef4444",
                "unlabeled": "#94a3b8",
            }.get(label, "#94a3b8")
        return {
            "keep": "#00a6ff",
            "maybe": "#ffd400",
            "reject": "#ff3b30",
            "unlabeled": "#344052",
        }.get(label, "#344052")


class ShortcutListView(QListView):
    def keyPressEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        window = self.window()
        if hasattr(window, "_handle_shortcut_event") and window._handle_shortcut_event(event):
            return
        super().keyPressEvent(event)


class LumaSiftWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowIcon(lumasift_app_icon())
        self.ui_font_family = apply_application_font(QApplication.instance() or QApplication([]))
        self.setProperty("lumasift_ui_font_family", self.ui_font_family)
        self.resize(1440, 900)
        self.setMinimumSize(1220, 800)
        self.records: list[dict[str, Any]] = []
        self.output_dir = Path("./outputs/gui")
        self.settings_store = QSettings("LumaSift", "LumaSift")
        self.language = "zh"
        self.theme = str(self.settings_store.value("theme", "dark"))
        if self.theme not in THEME_VALUES:
            self.theme = "dark"
        self.settings_store.remove("language")
        self.worker_thread: QThread | None = None
        self.worker: AnalysisWorker | None = None
        self.key_check_thread: QThread | None = None
        self.key_check_worker: VisionKeyCheckWorker | None = None
        self.selected_review_thread: QThread | None = None
        self.selected_review_worker: SelectedDeepReviewWorker | None = None
        self.thumbnail_thread: QThread | None = None
        self.thumbnail_worker: ThumbnailWorker | None = None
        self.visible_records: list[dict[str, Any]] = []
        self.photo_model: PhotoListModel | None = None
        self.thumbnail_generation = 0
        self.loaded_thumbnail_rows: set[int] = set()
        self.pending_thumbnail_rows: set[int] = set()
        self.workflow_steps: dict[str, QFrame] = {}
        self.stat_labels: dict[str, QLabel] = {}
        self.workflow_labels: dict[str, tuple[QLabel, QLabel]] = {}
        self.workflow_state_labels: dict[str, QLabel] = {}
        self.static_labels: dict[str, QLabel] = {}
        self._animations: list[QPropertyAnimation] = []
        self.run_heartbeat_timer = QTimer(self)
        self.run_heartbeat_timer.setInterval(1000)
        self.run_heartbeat_timer.timeout.connect(self._run_heartbeat_tick)
        self.run_started_at = 0.0
        self.last_progress_at = 0.0
        self.last_progress_text = ""
        self.heartbeat_phase = 0
        self.state_db = LumaSiftStateDb()
        self.current_run_id = ""
        self.pending_close = False
        self.allow_close = False
        self.review_mode = False
        self.current_nav_page = "main"
        self.nav_buttons: dict[str, QPushButton] = {}
        self.qwen_queue_state: dict[str, Any] = {}
        self.detected_vision_model = str(self.settings_store.value("vision_model", "qwen3.6-plus"))
        self.shortcut_keys: dict[str, int] = dict(DEFAULT_SHORTCUT_KEYS)
        self.shortcut_combos: dict[str, QComboBox] = {}
        self.preview_dialogs: list[LargePreviewDialog] = []
        self._build_ui()
        self._load_preferences()
        self._apply_style()
        self._retranslate_ui()
        self._update_workflow("import")
        self._update_dashboard()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        QTimer.singleShot(0, self._show_startup_setup_prompt)

    def _t(self, key: str) -> str:
        return UI_TEXT.get(self.language, UI_TEXT["zh"]).get(key, key)

    def _change_language(self, label: str) -> None:
        self.language = "en" if label == "English" else "zh"
        self._retranslate_ui()

    def _change_theme(self, *_: Any) -> None:
        if not hasattr(self, "theme_combo"):
            return
        value = str(self.theme_combo.currentData() or "dark")
        if value not in THEME_VALUES or value == self.theme:
            return
        self.theme = value
        self.settings_store.setValue("theme", self.theme)
        self._apply_style()
        if hasattr(self, "help_text"):
            self.help_text.setHtml(self._help_page_html())
        if hasattr(self, "detail_text"):
            self._show_selected_detail()
        if self.photo_model is not None and hasattr(self, "photo_list"):
            self.photo_list.viewport().update()

    def _show_startup_setup_prompt(self) -> None:
        if not hasattr(self, "input_edit"):
            return
        self._refresh_setup_attention()
        message = self._startup_setup_message()
        if hasattr(self, "cache_note"):
            self.cache_note.setText(message.replace("\n", " "))
            self._set_attention(self.cache_note, True)
        if hasattr(self, "status_label"):
            input_missing = not self.input_edit.text().strip() or not Path(self.input_edit.text().strip()).expanduser().exists()
            self.status_label.setText(self._t("input_missing_hint") if input_missing else self._t("startup_output_note"))
        if self._should_skip_startup_dialog():
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(self._t("startup_config_title"))
        box.setText(message)
        confirm_button = box.addButton(self._t("startup_confirm_paths"), QMessageBox.ButtonRole.AcceptRole)
        local_button = box.addButton(self._t("startup_use_local_no_api"), QMessageBox.ButtonRole.ActionRole)
        api_button = box.addButton(self._t("startup_configure_api"), QMessageBox.ButtonRole.ActionRole)
        box.setDefaultButton(confirm_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked == local_button:
            local_index = self.mode_combo.findData("local_only")
            if local_index >= 0:
                self.mode_combo.setCurrentIndex(local_index)
            self._save_preferences()
            self._refresh_setup_attention()
        elif clicked == api_button:
            qwen_index = self.mode_combo.findData("qwen_vision")
            if qwen_index >= 0:
                self.mode_combo.setCurrentIndex(qwen_index)
            self._show_nav_page("settings")
            self.advanced_panel.setVisible(True)
            self.api_key_edit.setFocus()
        else:
            self._show_nav_page("settings")
            self.input_edit.setFocus()

    def _startup_setup_message(self) -> str:
        input_text = self.input_edit.text().strip()
        output_text = self.output_edit.text().strip() or "./outputs/gui"
        input_missing = not input_text or not Path(input_text).expanduser().exists()
        qwen_enabled = (self.mode_combo.currentData() or self.mode_combo.currentText()) == "qwen_vision"
        has_key = self._has_configured_qwen_keys()
        if input_missing:
            api_note = self._t("startup_input_missing")
        elif qwen_enabled and not has_key:
            api_note = self._t("startup_api_qwen_missing")
        elif qwen_enabled and has_key:
            api_note = self._t("startup_api_qwen_ready")
        elif has_key:
            api_note = self._t("startup_api_local_has_key")
        else:
            api_note = self._t("startup_api_local_no_key")
        mode_text = self._t("qwen") if qwen_enabled else self._t("local")
        return self._t("startup_config_body").format(
            input_dir=input_text or self._t("missing_input_title"),
            output_dir=output_text,
            mode=mode_text,
            api_note=api_note,
        )

    def _should_skip_startup_dialog(self) -> bool:
        platform = os.environ.get("QT_QPA_PLATFORM", "").lower()
        return platform == "offscreen" or bool(os.environ.get("LUMASIFT_NO_STARTUP_DIALOG")) or bool(os.environ.get("PYTEST_CURRENT_TEST"))

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(self._t("app_title"))
        if self.photo_model is not None:
            self.photo_model.set_language(self.language)
        if hasattr(self, "language_combo"):
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentText("English" if self.language == "en" else "中文")
            self.language_combo.blockSignals(False)
        if hasattr(self, "theme_combo"):
            self.theme_combo.blockSignals(True)
            self.theme_combo.clear()
            self.theme_combo.addItem(self._t("theme_dark"), "dark")
            self.theme_combo.addItem(self._t("theme_light"), "light")
            self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(self.theme)))
            self.theme_combo.setToolTip(self._t("theme_tooltip"))
            self.theme_combo.blockSignals(False)
        if hasattr(self, "title_label"):
            self._set_header_logo()
        if hasattr(self, "subtitle_label"):
            self.subtitle_label.setText(self._t("hero_subtitle"))
        step_keys = {
            "import": ("step_import", "step_import_caption"),
            "local": ("step_local", "step_local_caption"),
            "qwen": ("step_qwen", "step_qwen_caption"),
            "edit": ("step_edit", "step_edit_caption"),
        }
        for step, (title_key, caption_key) in step_keys.items():
            labels = self.workflow_labels.get(step)
            if labels:
                labels[0].setText(self._t(title_key))
                labels[1].setText(self._t(caption_key))
        for key, label in [
            ("photo_folder", self.static_labels.get("photo_folder")),
            ("output_folder", self.static_labels.get("output_folder")),
            ("qwen_keys", self.static_labels.get("qwen_keys")),
            ("review_board", self.static_labels.get("review_board")),
            ("review_cockpit", self.static_labels.get("review_cockpit")),
            ("review_mode", self.static_labels.get("review_mode")),
            ("shortcuts_title", self.static_labels.get("shortcuts_page_title")),
            ("nav_help", self.static_labels.get("help_page_title")),
        ]:
            if label:
                label.setText(self._t(key))
        if hasattr(self, "browse_input_button"):
            self.browse_input_button.setText(self._t("browse"))
            self.browse_output_button.setText(self._t("browse"))
            self.output_edit.setToolTip(self._t("output_folder_hint"))
        for page, text_key in [("main", "nav_main"), ("settings", "settings"), ("shortcuts", "nav_shortcuts"), ("help", "nav_help")]:
            button = self.nav_buttons.get(page)
            if button:
                button.setText(self._t(text_key))
        if hasattr(self, "settings_nav_button"):
            self._sync_setup_nav_button()
        mini_map = {
            "mini_Mode": "mode",
            "mini_Scan": "scan",
            "mini_Deep Top": "qwen_top",
            "mini_Advice Top": "advice_top",
            "mini_Show": "show",
        }
        for key, text_key in mini_map.items():
            if key in self.static_labels:
                self.static_labels[key].setText(self._t(text_key))
        if hasattr(self, "api_key_edit"):
            mode_value = self.mode_combo.currentData() or "local_only"
            self.mode_combo.blockSignals(True)
            self.mode_combo.clear()
            self.mode_combo.addItem(self._t("local"), "local_only")
            self.mode_combo.addItem(self._t("qwen"), "qwen_vision")
            mode_index = self.mode_combo.findData(mode_value)
            self.mode_combo.setCurrentIndex(mode_index if mode_index >= 0 else 0)
            self.mode_combo.blockSignals(False)
            self.top_n_spin.setToolTip(self._t("deep_top_tooltip"))
            self.selected_top_spin.setToolTip(self._t("advice_top_tooltip"))
            self._sync_mode_controls()
            self.api_key_edit.setPlaceholderText(self._t("api_placeholder"))
            if hasattr(self, "vision_base_url_edit"):
                self.static_labels["vision_base_url"].setText(self._t("vision_base_url"))
                self.static_labels["vision_model"].setText(self._t("vision_model"))
                self.vision_base_url_edit.setPlaceholderText(f"{self._t('vision_base_url_placeholder')}: {DEFAULT_VISION_BASE_URL}")
                self.vision_model_edit.setPlaceholderText(self._t("vision_model_placeholder"))
            self.check_key_button.setText(self._t("check_key"))
            self.show_key_checkbox.setText(self._t("show"))
            self.save_keys_checkbox.setText(self._t("save_keys"))
            self.run_button.setText(self._t("analyze"))
            self.cancel_button.setText(self._t("cancel"))
            self.main_run_button.setText(self._t("analyze"))
            self.main_cancel_button.setText(self._t("cancel"))
            if hasattr(self, "shortcut_reset_button"):
                self.shortcut_reset_button.setText(self._t("reset_shortcuts"))
                self.shortcut_hint_label.setText(self._t("shortcuts_hint"))
                for action, label in self.shortcut_labels.items():
                    label.setText(self._t(f"shortcut_{action}"))
            self.help_text.setHtml(self._help_page_html())
            self.review_setup_button.setText(self._t("show_setup"))
            self.review_new_scan_button.setText(self._t("new_scan"))
            self.search_edit.setPlaceholderText(self._t("search"))
            self.photo_list.setToolTip(self._t("grid_tooltip"))
            self.detail_hint_label.setText(self._t("detail_hint"))
            if hasattr(self, "tone_filter"):
                current_tone = self.tone_filter.currentData() or "all"
                self.tone_filter.blockSignals(True)
                self.tone_filter.clear()
                self.tone_filter.addItem(self._t("all_tones"), "all")
                for tone in sorted({str(record.get("tone_category", "")) for record in self.records if record.get("tone_category")}):
                    self.tone_filter.addItem(self._display_tone_category(tone), tone)
                tone_index = self.tone_filter.findData(current_tone)
                self.tone_filter.setCurrentIndex(tone_index if tone_index >= 0 else 0)
                self.tone_filter.blockSignals(False)
            self.keep_button.setText(f"▲ {self._t('keep')}")
            self.keep_button.setToolTip(self._t("keep"))
            self.maybe_button.setText(f"◆ {self._t('maybe')}")
            self.maybe_button.setToolTip(self._t("maybe"))
            self.reject_button.setText(f"■ {self._t('reject')}")
            self.reject_button.setToolTip(self._t("reject"))
            self.deep_review_selected_button.setText(self._t("deep_review_selected"))
            self.deep_review_selected_button.setToolTip(self._t("deep_review_selected_tooltip"))
            self.generate_advice_button.setText(self._t("editing_plan"))
            self.generate_advice_button.setToolTip(self._t("editing_plan"))
            self.crop_preview_button.setText(self._t("crop_preview"))
            self._sync_crop_preview_button()
            self.open_output_button.setText(self._t("open_output"))
            self.open_output_button.setToolTip(self._t("open_output"))
            self.open_contact_button.setText(self._t("open_contact"))
            self.open_contact_button.setToolTip(self._t("open_contact"))
            self._sync_deep_review_selected_button()
            if not self.records:
                self.result_count_label.setText(self._t("no_results"))
                self.status_label.setText(self._t("ready"))
                self._show_empty_grid(self._t("empty_grid"))
                self.detail_text.setHtml(self._empty_detail_html())
        self._reset_filter_combos()
        self._update_dashboard()

    def _reset_filter_combos(self) -> None:
        if not hasattr(self, "category_filter"):
            return
        category = self.category_filter.currentData() or self.category_filter.currentText()
        tone_value = self.tone_filter.currentData() if hasattr(self, "tone_filter") else "all"
        label_value = self.label_filter.currentData() or "all"
        group_value = self.group_filter.currentData() if hasattr(self, "group_filter") else "all"
        pair_value = self.pair_filter.currentData() if hasattr(self, "pair_filter") else "all"
        review_value = self.review_filter.currentData() if hasattr(self, "review_filter") else "all"
        sort_value = self.sort_combo.currentData() or "score_desc"
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem(self._t("all_categories"), "all")
        categories = sorted({str(record.get("category", "")) for record in self.records if record.get("category")})
        for item in categories:
            self.category_filter.addItem(item, item)
        category_index = self.category_filter.findData(category)
        self.category_filter.setCurrentIndex(category_index if category_index >= 0 else 0)
        self.category_filter.blockSignals(False)

        self.tone_filter.blockSignals(True)
        self.tone_filter.clear()
        self.tone_filter.addItem(self._t("all_tones"), "all")
        tones = sorted({str(record.get("tone_category", "")) for record in self.records if record.get("tone_category")})
        for tone in tones:
            self.tone_filter.addItem(self._display_tone_category(tone), tone)
        tone_index = self.tone_filter.findData(tone_value)
        self.tone_filter.setCurrentIndex(tone_index if tone_index >= 0 else 0)
        self.tone_filter.blockSignals(False)

        self.label_filter.blockSignals(True)
        self.label_filter.clear()
        for text_key, data in [
            ("all_labels", "all"),
            ("keep", "keep"),
            ("maybe", "maybe"),
            ("reject", "reject"),
            ("unlabeled", "unlabeled"),
        ]:
            self.label_filter.addItem(self._t(text_key), data)
        label_index = self.label_filter.findData(label_value)
        self.label_filter.setCurrentIndex(label_index if label_index >= 0 else 0)
        self.label_filter.blockSignals(False)

        self.group_filter.blockSignals(True)
        self.group_filter.clear()
        for text_key, data in [
            ("all_groups", "all"),
            ("group_best", "best"),
            ("grouped_only", "grouped"),
            ("group_time", "time"),
            ("group_visual", "visual"),
            ("singletons", "singletons"),
        ]:
            self.group_filter.addItem(self._t(text_key), data)
        group_index = self.group_filter.findData(group_value)
        self.group_filter.setCurrentIndex(group_index if group_index >= 0 else 0)
        self.group_filter.blockSignals(False)

        self.pair_filter.blockSignals(True)
        self.pair_filter.clear()
        for text_key, data in [
            ("all_pairs", "all"),
            ("raw_jpeg_pairs", "raw_jpeg_pair"),
            ("raw_only", "raw_only"),
            ("jpeg_only", "jpeg_only"),
            ("other_files", "single"),
        ]:
            self.pair_filter.addItem(self._t(text_key), data)
        pair_index = self.pair_filter.findData(pair_value)
        self.pair_filter.setCurrentIndex(pair_index if pair_index >= 0 else 0)
        self.pair_filter.blockSignals(False)

        self.review_filter.blockSignals(True)
        self.review_filter.clear()
        for text_key, data in [
            ("all_review_status", "all"),
            ("reviewed_qwen", "reviewed"),
            ("reviewed_concrete", "concrete"),
            ("not_reviewed", "not_reviewed"),
            ("review_failed", "failed"),
            ("review_skipped", "skipped"),
        ]:
            self.review_filter.addItem(self._t(text_key), data)
        review_index = self.review_filter.findData(review_value)
        self.review_filter.setCurrentIndex(review_index if review_index >= 0 else 0)
        self.review_filter.blockSignals(False)

        self.sort_combo.blockSignals(True)
        self.sort_combo.clear()
        for text_key, data in [
            ("sort_high", "score_desc"),
            ("sort_user", "user_priority"),
            ("sort_low", "score_asc"),
            ("sort_rank", "rank"),
            ("sort_name", "filename"),
        ]:
            self.sort_combo.addItem(self._t(text_key), data)
        sort_index = self.sort_combo.findData(sort_value)
        self.sort_combo.setCurrentIndex(sort_index if sort_index >= 0 else 0)
        self.sort_combo.blockSignals(False)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(6)

        self.header_frame = self._build_header()
        self.workflow_frame = self._build_workflow()
        self.review_bar = self._build_review_bar()
        root.addWidget(self.header_frame)

        self.main_page = QFrame()
        self.main_page.setObjectName("navPage")
        main_layout = QVBoxLayout(self.main_page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)
        main_layout.addWidget(self.workflow_frame)
        main_layout.addWidget(self.review_bar)
        self.review_bar.setVisible(False)
        self.qwen_status_frame = self._build_qwen_status_panel()
        main_layout.addWidget(self.qwen_status_frame)
        self.toolbar_frame = self._build_result_toolbar()
        main_layout.addWidget(self.toolbar_frame)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainSplitter")
        self.main_splitter = splitter
        self.photo_list = ShortcutListView()
        self.photo_list.setObjectName("photoGrid")
        self.photo_list.setViewMode(QListView.ViewMode.IconMode)
        self.photo_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.photo_list.setMovement(QListView.Movement.Static)
        self.photo_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.photo_list.setIconSize(QSize(210, 148))
        self.photo_list.setSpacing(10)
        self.photo_list.setUniformItemSizes(True)
        self.photo_list.setItemDelegate(PhotoCardDelegate(self.photo_list))
        self.photo_list.setLayoutMode(QListView.LayoutMode.Batched)
        self.photo_list.setBatchSize(96)
        self.photo_list.installEventFilter(self)
        self.photo_list.viewport().installEventFilter(self)
        self.select_all_shortcut = QShortcut(QKeySequence("Ctrl+A"), self.photo_list)
        self.select_all_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.select_all_shortcut.activated.connect(self._select_all_visible_records)
        self.invert_selection_shortcut = QShortcut(QKeySequence("Ctrl+I"), self.photo_list)
        self.invert_selection_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.invert_selection_shortcut.activated.connect(self._invert_visible_selection)
        self.photo_model = PhotoListModel(self._placeholder_icon())
        self.photo_model.set_language(self.language)
        self.photo_list.setModel(self.photo_model)
        self.photo_list.selectionModel().selectionChanged.connect(lambda *_: self._show_selected_detail())
        self.photo_list.doubleClicked.connect(self._open_large_preview)
        self.photo_list.verticalScrollBar().valueChanged.connect(lambda *_: self._queue_visible_thumbnails())
        self._show_empty_grid("Drop into the workflow by choosing a folder, then run analysis.")
        splitter.addWidget(self.photo_list)

        self.detail_panel = QFrame()
        self.detail_panel.setObjectName("detailPanel")
        self.detail_panel.setMinimumWidth(620)
        self._apply_shadow(self.detail_panel, blur=22, y=8, alpha=24)
        detail_layout = QVBoxLayout(self.detail_panel)
        detail_layout.setContentsMargins(10, 10, 10, 10)
        detail_layout.setSpacing(7)
        guide_strip = QFrame()
        guide_strip.setObjectName("constructGuide")
        guide_layout = QHBoxLayout(guide_strip)
        guide_layout.setContentsMargins(0, 0, 0, 0)
        guide_layout.setSpacing(6)
        for name, width in [("guideCyan", 90), ("guideYellow", 46), ("guideRed", 28)]:
            segment = QFrame()
            segment.setObjectName(name)
            segment.setFixedSize(width, 6)
            guide_layout.addWidget(segment)
        guide_layout.addStretch(1)
        detail_layout.addWidget(guide_strip)
        detail_title = QLabel("")
        detail_title.setObjectName("sectionTitle")
        self.static_labels["review_cockpit"] = detail_title
        detail_hint = QLabel("")
        detail_hint.setObjectName("muted")
        detail_hint.setWordWrap(True)
        self.detail_hint_label = detail_hint
        detail_layout.addWidget(detail_title)
        detail_layout.addWidget(detail_hint)
        self.detail_text = QTextEdit()
        self.detail_text.setObjectName("detailText")
        self.detail_text.setReadOnly(True)
        self.detail_text.setMinimumHeight(80)
        self.detail_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.detail_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.detail_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail_text.document().setDocumentMargin(0)
        self.detail_text.setHtml(self._empty_detail_html())
        detail_layout.addWidget(self.detail_text, stretch=1)

        action_bar = QFrame()
        action_bar.setObjectName("actionBar")
        action_grid = QGridLayout(action_bar)
        action_grid.setContentsMargins(5, 5, 5, 5)
        action_grid.setHorizontalSpacing(5)
        action_grid.setVerticalSpacing(5)
        self.keep_button = QPushButton("")
        self.keep_button.setObjectName("markKeepButton")
        self.keep_button.setMinimumHeight(32)
        self.keep_button.setMinimumWidth(48)
        self.keep_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.keep_button.clicked.connect(lambda: self._mark_selected("keep"))
        self.deep_review_selected_button = QPushButton("")
        self.deep_review_selected_button.setObjectName("primaryButton")
        self.deep_review_selected_button.setMinimumHeight(38)
        self.deep_review_selected_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.deep_review_selected_button.clicked.connect(self._deep_review_selected)
        action_grid.addWidget(self.deep_review_selected_button, 0, 0, 1, 4)
        self.action_status_label = QLabel("")
        self.action_status_label.setObjectName("actionStatus")
        self.action_status_label.setWordWrap(True)
        action_grid.addWidget(self.action_status_label, 1, 0, 1, 4)
        action_grid.addWidget(self.keep_button, 2, 0)
        self.maybe_button = QPushButton("")
        self.maybe_button.setObjectName("markMaybeButton")
        self.maybe_button.setMinimumHeight(32)
        self.maybe_button.setMinimumWidth(48)
        self.maybe_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.maybe_button.clicked.connect(lambda: self._mark_selected("maybe"))
        action_grid.addWidget(self.maybe_button, 2, 1)
        self.reject_button = QPushButton("")
        self.reject_button.setObjectName("markRejectButton")
        self.reject_button.setMinimumHeight(32)
        self.reject_button.setMinimumWidth(48)
        self.reject_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.reject_button.clicked.connect(lambda: self._mark_selected("reject"))
        action_grid.addWidget(self.reject_button, 2, 2, 1, 2)
        self.generate_advice_button = QPushButton("")
        self.generate_advice_button.setObjectName("primaryButton")
        self.generate_advice_button.setMinimumHeight(32)
        self.generate_advice_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        self.generate_advice_button.setIconSize(QSize(18, 18))
        self.generate_advice_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.generate_advice_button.clicked.connect(self._generate_selected_advice)
        action_grid.addWidget(self.generate_advice_button, 3, 0)
        self.crop_preview_button = QPushButton("")
        self.crop_preview_button.setObjectName("secondaryButton")
        self.crop_preview_button.setMinimumHeight(32)
        self.crop_preview_button.setMinimumWidth(88)
        self.crop_preview_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.crop_preview_button.clicked.connect(self._open_selected_crop_preview)
        action_grid.addWidget(self.crop_preview_button, 3, 1)
        self.open_output_button = QPushButton("")
        self.open_output_button.setObjectName("secondaryButton")
        self.open_output_button.setMinimumHeight(32)
        self.open_output_button.setMinimumWidth(44)
        self.open_output_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.open_output_button.setIconSize(QSize(18, 18))
        self.open_output_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.open_output_button.clicked.connect(lambda: self._open_path(self.output_dir))
        action_grid.addWidget(self.open_output_button, 3, 2)
        self.open_contact_button = QPushButton("")
        self.open_contact_button.setObjectName("secondaryButton")
        self.open_contact_button.setMinimumHeight(32)
        self.open_contact_button.setMinimumWidth(44)
        self.open_contact_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.open_contact_button.setIconSize(QSize(18, 18))
        self.open_contact_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.open_contact_button.clicked.connect(lambda: self._open_path(self.output_dir / "contact_sheet_top50.jpg"))
        action_grid.addWidget(self.open_contact_button, 3, 3)
        detail_layout.addWidget(action_bar, stretch=0)
        splitter.addWidget(self.detail_panel)
        splitter.setSizes([760, 700])
        main_layout.addWidget(splitter, stretch=1)
        root.addWidget(self.main_page, stretch=1)

        self.settings_page = QFrame()
        self.settings_page.setObjectName("navPage")
        settings_layout = QVBoxLayout(self.settings_page)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(0)
        self.controls_frame = self._build_controls()
        settings_layout.addWidget(self.controls_frame, stretch=1)
        root.addWidget(self.settings_page, stretch=1)

        self.shortcuts_page = self._build_shortcuts_page()
        root.addWidget(self.shortcuts_page, stretch=1)
        self.help_page = self._build_help_page()
        root.addWidget(self.help_page, stretch=1)

        self.setCentralWidget(central)
        self._show_nav_page("main")

    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("topNav")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel("")
        title.setObjectName("navLogo")
        title.setFixedSize(42, 34)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label = title
        self._set_header_logo()
        subtitle = QLabel("")
        subtitle.setVisible(False)
        subtitle.setObjectName("subtitle")
        self.subtitle_label = subtitle
        layout.addWidget(title)

        for page, text_key, handler in [
            ("main", "nav_main", lambda: self._show_nav_page("main")),
            ("settings", "settings", lambda: self._show_nav_page("settings")),
            ("shortcuts", "nav_shortcuts", lambda: self._show_nav_page("shortcuts")),
            ("help", "nav_help", lambda: self._show_nav_page("help")),
        ]:
            button = QPushButton("")
            button.setObjectName("navButton")
            button.setText(self._t(text_key))
            button.clicked.connect(handler)
            self.nav_buttons[page] = button
            self.static_labels[f"nav_{text_key}"] = button
            layout.addWidget(button)
        self.settings_nav_button = self.nav_buttons["settings"]

        layout.addStretch(1)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem(self._t("theme_dark"), "dark")
        self.theme_combo.addItem(self._t("theme_light"), "light")
        self.theme_combo.setFixedWidth(92)
        self.theme_combo.currentIndexChanged.connect(self._change_theme)
        layout.addWidget(self.theme_combo)

        self.language_combo = QComboBox()
        self.language_combo.addItems(["中文", "English"])
        self.language_combo.setFixedWidth(104)
        self.language_combo.currentTextChanged.connect(self._change_language)
        layout.addWidget(self.language_combo)
        return frame

    def _set_header_logo(self) -> None:
        label = getattr(self, "title_label", None)
        if not isinstance(label, QLabel):
            return
        logo_path = lumasift_resource_path("lumasift.png")
        if logo_path:
            pixmap = QPixmap(str(logo_path))
            if not pixmap.isNull():
                label.setText("")
                label.setPixmap(
                    pixmap.scaled(
                        QSize(24, 24),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return
        label.setPixmap(QPixmap())
        label.setText("L")

    def _build_workflow(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("workflow")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        for key, title, caption in [
            ("import", "1. Import", "Choose local RAW/JPG folder"),
            ("local", "2. Pre-score", "Fast local CV and preview cache"),
            ("qwen", "3. Deep analysis", "LLM only for high-value candidates"),
            ("edit", "4. Edit plan", "Multi-select concrete tuning guidance"),
        ]:
            step = QFrame()
            step.setObjectName("stepCard")
            step.setProperty("state", "idle")
            step.setCursor(Qt.CursorShape.PointingHandCursor)
            step.mousePressEvent = lambda event, step_key=key: self._focus_workflow_step(step_key)  # type: ignore[method-assign]
            step_layout = QVBoxLayout(step)
            step_layout.setContentsMargins(14, 11, 14, 11)
            step_layout.setSpacing(4)
            heading = QLabel(title)
            heading.setObjectName("stepTitle")
            body = QLabel(caption)
            body.setObjectName("stepCaption")
            body.setWordWrap(True)
            state_label = QLabel("")
            state_label.setObjectName("stepState")
            step_layout.addWidget(heading)
            step_layout.addWidget(body)
            step_layout.addWidget(state_label)
            self.workflow_steps[key] = step
            self.workflow_labels[key] = (heading, body)
            self.workflow_state_labels[key] = state_label
            layout.addWidget(step, stretch=1)
        return frame

    def _build_review_bar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("reviewBar")
        self._apply_shadow(frame, blur=18, y=6, alpha=18)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(10)

        mode_label = QLabel("")
        mode_label.setObjectName("sectionTitle")
        self.static_labels["review_mode"] = mode_label
        self.review_summary_label = QLabel("")
        self.review_summary_label.setObjectName("muted")
        self.review_setup_button = QPushButton("")
        self.review_setup_button.setObjectName("ghostButton")
        self.review_setup_button.clicked.connect(lambda: self._exit_review_mode(show_advanced=True))
        self.review_new_scan_button = QPushButton("")
        self.review_new_scan_button.setObjectName("secondaryButton")
        self.review_new_scan_button.clicked.connect(lambda: self._exit_review_mode(show_advanced=False))

        layout.addWidget(mode_label)
        layout.addWidget(self.review_summary_label, stretch=1)
        layout.addWidget(self.review_setup_button)
        layout.addWidget(self.review_new_scan_button)
        return frame

    def _build_qwen_status_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("qwenStatusPanel")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)
        self.qwen_queue_label = QLabel("")
        self.qwen_queue_label.setObjectName("qwenQueueLabel")
        self.qwen_queue_label.setTextFormat(Qt.TextFormat.RichText)
        self.qwen_queue_label.setMinimumHeight(32)
        self.qwen_queue_label.setWordWrap(False)
        self.qwen_progress = QProgressBar()
        self.qwen_progress.setObjectName("qwenProgress")
        self.qwen_progress.setRange(0, 1)
        self.qwen_progress.setValue(0)
        self.qwen_progress.setFixedWidth(220)
        self.qwen_stage_label = QLabel("")
        self.qwen_stage_label.setObjectName("muted")
        self.qwen_stage_label.setMinimumWidth(260)
        layout.addWidget(self.qwen_queue_label, stretch=1)
        layout.addWidget(self.qwen_progress)
        layout.addWidget(self.qwen_stage_label)
        frame.setVisible(False)
        return frame

    def _build_shortcuts_page(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("navPage")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        title = QLabel("")
        title.setObjectName("sectionTitle")
        self.static_labels["shortcuts_page_title"] = title
        self.shortcut_hint_label = QLabel("")
        self.shortcut_hint_label.setObjectName("muted")
        self.shortcut_hint_label.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(self.shortcut_hint_label)

        card = QFrame()
        card.setObjectName("controlCard")
        card_layout = QGridLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setHorizontalSpacing(18)
        card_layout.setVerticalSpacing(12)
        self.shortcut_labels: dict[str, QLabel] = {}
        for row, action in enumerate(SHORTCUT_ACTIONS):
            label = QLabel("")
            label.setObjectName("fieldLabel")
            combo = self._build_shortcut_combo(action)
            self.shortcut_labels[action] = label
            self.shortcut_combos[action] = combo
            card_layout.addWidget(label, row, 0)
            card_layout.addWidget(combo, row, 1)
        card_layout.setColumnStretch(1, 1)
        layout.addWidget(card)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.shortcut_reset_button = QPushButton("")
        self.shortcut_reset_button.setObjectName("secondaryButton")
        self.shortcut_reset_button.setMinimumHeight(34)
        self.shortcut_reset_button.clicked.connect(self._reset_shortcuts_to_defaults)
        actions.addWidget(self.shortcut_reset_button)
        layout.addLayout(actions)
        layout.addStretch(1)
        return frame

    def _build_shortcut_combo(self, action: str) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName("settingInput")
        combo.setMinimumHeight(36)
        for label, key_code in SHORTCUT_KEY_CHOICES:
            combo.addItem(label, key_code)
        combo.currentIndexChanged.connect(lambda _index, action=action: self._shortcut_combo_changed(action))
        return combo

    def _build_help_page(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("navPage")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        title = QLabel("")
        title.setObjectName("sectionTitle")
        self.static_labels["help_page_title"] = title
        self.help_text = QTextEdit()
        self.help_text.setObjectName("detailText")
        self.help_text.setReadOnly(True)
        layout.addWidget(title)
        layout.addWidget(self.help_text, stretch=1)
        return frame

    def _build_controls(self) -> QFrame:
        group = QFrame()
        group.setObjectName("controlCard")
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._apply_shadow(group, blur=24, y=8, alpha=20)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        main_row = QGridLayout()
        main_row.setHorizontalSpacing(10)
        main_row.setVerticalSpacing(8)

        self.input_edit = QLineEdit("D:/DCIM")
        self.input_edit.setObjectName("pathEdit")
        self.input_edit.textChanged.connect(lambda *_: self._refresh_setup_attention())
        browse_input = QPushButton("Browse")
        self.browse_input_button = browse_input
        browse_input.setObjectName("secondaryButton")
        browse_input.clicked.connect(self._choose_input)
        source_label = QLabel("Photo folder")
        source_label.setObjectName("fieldLabel")
        self.static_labels["photo_folder"] = source_label
        main_row.addWidget(source_label, 0, 0)
        main_row.addWidget(self.input_edit, 0, 1)
        main_row.addWidget(browse_input, 0, 2)

        self.output_edit = QLineEdit(str(self.output_dir))
        self.output_edit.setObjectName("pathEdit")
        self.output_edit.textChanged.connect(lambda *_: self._refresh_setup_attention())
        browse_output = QPushButton("Browse")
        self.browse_output_button = browse_output
        browse_output.setObjectName("secondaryButton")
        browse_output.clicked.connect(self._choose_output)
        output_label = QLabel("Output folder")
        output_label.setObjectName("fieldLabel")
        self.static_labels["output_folder"] = output_label
        self.output_edit.setToolTip(self._t("output_folder_hint"))
        main_row.addWidget(output_label, 1, 0)
        main_row.addWidget(self.output_edit, 1, 1)
        main_row.addWidget(browse_output, 1, 2)

        self.run_button = QPushButton("Analyze Folder")
        self.run_button.setObjectName("primaryButton")
        self.run_button.setMinimumHeight(48)
        self.run_button.setMinimumWidth(104)
        self.run_button.clicked.connect(self._start_analysis)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.setMinimumHeight(48)
        self.cancel_button.setMinimumWidth(74)
        self.cancel_button.clicked.connect(lambda: self._cancel_analysis())
        self.cancel_button.setEnabled(False)
        main_row.addWidget(self.run_button, 0, 3, 2, 1)
        main_row.addWidget(self.cancel_button, 0, 4, 2, 1)
        main_row.setColumnStretch(1, 1)
        layout.addLayout(main_row)

        progress_row = QHBoxLayout()
        progress_row.setContentsMargins(0, 0, 0, 0)
        progress_row.setSpacing(10)
        self.progress = QProgressBar()
        self.progress.setObjectName("runProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("muted")
        progress_row.addWidget(self.progress, stretch=1)
        progress_row.addWidget(self.status_label, stretch=0)
        layout.addLayout(progress_row)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("local_only", "local_only")
        self.mode_combo.addItem("qwen_vision", "qwen_vision")
        self.mode_combo.currentTextChanged.connect(self._sync_mode_controls)
        self.mode_combo.setObjectName("settingInput")
        self.mode_combo.setFixedSize(360, 36)
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 100000)
        self.limit_spin.setValue(50)
        self.limit_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.limit_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.limit_spin.setObjectName("settingInput")
        self.limit_spin.setFixedSize(128, 36)
        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(1, 500)
        self.top_n_spin.setValue(5)
        self.top_n_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.top_n_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.top_n_spin.setObjectName("settingInput")
        self.top_n_spin.setFixedSize(128, 36)
        self.selected_top_spin = QSpinBox()
        self.selected_top_spin.setRange(1, 100)
        self.selected_top_spin.setValue(10)
        self.selected_top_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.selected_top_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.selected_top_spin.setObjectName("settingInput")
        self.selected_top_spin.setFixedSize(128, 36)
        self.display_limit_spin = QSpinBox()
        self.display_limit_spin.setRange(20, 2000)
        self.display_limit_spin.setValue(300)
        self.display_limit_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.display_limit_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.display_limit_spin.setObjectName("settingInput")
        self.display_limit_spin.setFixedSize(128, 36)

        self.advanced_panel = QFrame()
        self.advanced_panel.setObjectName("advancedPanel")
        self.advanced_panel.setMinimumHeight(224)
        self.advanced_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        advanced_layout = QVBoxLayout(self.advanced_panel)
        advanced_layout.setContentsMargins(10, 10, 10, 10)
        advanced_layout.setSpacing(10)

        settings_grid = QGridLayout()
        settings_grid.setContentsMargins(0, 0, 0, 0)
        settings_grid.setHorizontalSpacing(18)
        settings_grid.setVerticalSpacing(6)
        for col, (label, control) in enumerate([
            ("Mode", self.mode_combo),
            ("Scan", self.limit_spin),
            ("Deep Top", self.top_n_spin),
            ("Advice Top", self.selected_top_spin),
            ("Show", self.display_limit_spin),
        ]):
            mini_label = QLabel(label)
            mini_label.setObjectName("miniLabel")
            self.static_labels[f"mini_{label}"] = mini_label
            mini_label.setMinimumHeight(18)
            settings_grid.addWidget(mini_label, 0, col)
            settings_grid.addWidget(control, 1, col)
            settings_grid.setColumnMinimumWidth(col, 136 if label != "Mode" else 372)
        settings_grid.setColumnStretch(5, 1)
        advanced_layout.addLayout(settings_grid)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("Optional: enter one LLM API key. Leave empty to use .env.")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setMinimumHeight(34)
        self.api_key_edit.textEdited.connect(self._api_key_text_edited)
        self.vision_base_url_edit = QLineEdit()
        self.vision_base_url_edit.setObjectName("settingInput")
        self.vision_base_url_edit.setMinimumHeight(34)
        self.vision_base_url_edit.setPlaceholderText(f"Auto: {DEFAULT_VISION_BASE_URL}")
        self.vision_model_edit = QLineEdit()
        self.vision_model_edit.setObjectName("settingInput")
        self.vision_model_edit.setMinimumHeight(34)
        self.vision_model_edit.setPlaceholderText("Auto-detect best vision model")
        self.show_key_checkbox = QCheckBox("Show")
        self.show_key_checkbox.setMinimumHeight(24)
        self.show_key_checkbox.toggled.connect(self._toggle_key_visibility)
        self.check_key_button = QPushButton("")
        self.check_key_button.setObjectName("secondaryButton")
        self.check_key_button.setMinimumHeight(34)
        self.check_key_button.clicked.connect(self._check_qwen_key)
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.api_key_edit, stretch=1)
        key_layout.addWidget(self.check_key_button)
        key_layout.addWidget(self.show_key_checkbox)
        self.save_keys_checkbox = QCheckBox("Save API keys locally")
        self.save_keys_checkbox.setMinimumHeight(24)
        self.cache_note = QLabel("Deep mode uploads only Top-N compressed JPEG previews; RAW files stay local.")
        self.cache_note.setObjectName("muted")
        self.cache_note.setMinimumHeight(20)
        api_label = QLabel("LLM API")
        api_label.setObjectName("fieldLabel")
        self.static_labels["qwen_keys"] = api_label
        base_url_label = QLabel("")
        base_url_label.setObjectName("miniLabel")
        self.static_labels["vision_base_url"] = base_url_label
        model_label = QLabel("")
        model_label.setObjectName("miniLabel")
        self.static_labels["vision_model"] = model_label
        endpoint_row = QWidget()
        endpoint_layout = QHBoxLayout(endpoint_row)
        endpoint_layout.setContentsMargins(0, 0, 0, 0)
        endpoint_layout.setSpacing(8)
        endpoint_layout.addWidget(base_url_label)
        endpoint_layout.addWidget(self.vision_base_url_edit, stretch=2)
        endpoint_layout.addWidget(model_label)
        endpoint_layout.addWidget(self.vision_model_edit, stretch=1)
        key_grid = QGridLayout()
        key_grid.setHorizontalSpacing(10)
        key_grid.setVerticalSpacing(6)
        key_grid.addWidget(api_label, 0, 0)
        key_grid.addWidget(key_row, 0, 1)
        key_grid.addWidget(endpoint_row, 1, 1)
        key_grid.addWidget(self.save_keys_checkbox, 2, 1)
        key_grid.addWidget(self.cache_note, 3, 1)
        key_grid.setRowMinimumHeight(0, 34)
        key_grid.setRowMinimumHeight(1, 34)
        key_grid.setRowMinimumHeight(2, 24)
        key_grid.setRowMinimumHeight(3, 20)
        key_grid.setColumnStretch(1, 1)
        advanced_layout.addLayout(key_grid)
        self.advanced_panel.setVisible(True)
        layout.addWidget(self.advanced_panel)
        layout.addStretch(1)
        return group

    def _build_result_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("toolbar")
        self._apply_shadow(frame, blur=18, y=6, alpha=14)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("")
        self.search_edit.textChanged.connect(self._populate_records)
        self.category_filter = QComboBox()
        self.category_filter.addItems(
            [
                "All categories",
                "portfolio_candidate",
                "strong_edit_candidate",
                "story_candidate",
                "technically_weak_but_interesting",
                "ordinary_record",
                "reject_candidate",
                "failed",
            ]
        )
        self.category_filter.currentTextChanged.connect(self._populate_records)
        self.tone_filter = QComboBox()
        self.tone_filter.addItems(["All tones"])
        self.tone_filter.currentIndexChanged.connect(self._populate_records)
        self.label_filter = QComboBox()
        self.label_filter.addItems(["All labels", "keep", "maybe", "reject", "unlabeled"])
        self.label_filter.currentTextChanged.connect(self._populate_records)
        self.group_filter = QComboBox()
        self.group_filter.addItems(["All groups", "Group best", "Grouped", "Singles"])
        self.group_filter.currentTextChanged.connect(self._populate_records)
        self.pair_filter = QComboBox()
        self.pair_filter.addItems(["All pairs", "RAW+JPG", "RAW only", "JPG only", "Other files"])
        self.pair_filter.currentIndexChanged.connect(self._populate_records)
        self.review_filter = QComboBox()
        self.review_filter.addItems(["All review", "LLM-read", "Concrete read", "Not reviewed", "Failed/retry", "Skipped"])
        self.review_filter.currentIndexChanged.connect(self._populate_records)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Score high to low", "Label priority", "Score low to high", "Rank", "Filename A-Z"])
        self.sort_combo.currentTextChanged.connect(self._populate_records)
        self.result_count_label = QLabel("")
        self.result_count_label.setObjectName("resultCount")
        self.main_run_button = QPushButton("")
        self.main_run_button.setObjectName("primaryButton")
        self.main_run_button.setMinimumHeight(34)
        self.main_run_button.setMinimumWidth(96)
        self.main_run_button.clicked.connect(self._start_analysis)
        self.main_cancel_button = QPushButton("")
        self.main_cancel_button.setObjectName("secondaryButton")
        self.main_cancel_button.setMinimumHeight(34)
        self.main_cancel_button.setMinimumWidth(58)
        self.main_cancel_button.clicked.connect(lambda: self._cancel_analysis())
        self.main_cancel_button.setEnabled(False)

        filter_label = QLabel("")
        filter_label.setObjectName("sectionTitle")
        self.static_labels["review_board"] = filter_label
        layout.addWidget(filter_label)
        layout.addWidget(self.search_edit, stretch=1)
        layout.addWidget(self.category_filter)
        layout.addWidget(self.tone_filter)
        layout.addWidget(self.label_filter)
        layout.addWidget(self.group_filter)
        layout.addWidget(self.pair_filter)
        layout.addWidget(self.review_filter)
        layout.addWidget(self.sort_combo)
        layout.addWidget(self.result_count_label)
        layout.addWidget(self.main_run_button)
        layout.addWidget(self.main_cancel_button)
        return frame

    def _choose_input(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self._t("photo_folder"), self.input_edit.text())
        if folder:
            self.input_edit.setText(folder)
            self._save_preferences()
            self._update_workflow("import")

    def _choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self._t("output_folder"), self.output_edit.text())
        if folder:
            self.output_edit.setText(folder)
            self.output_dir = Path(folder)
            self._save_preferences()

    def _toggle_advanced_panel(self) -> None:
        self.controls_frame.setVisible(True)
        self.advanced_panel.setVisible(True)
        self._sync_setup_nav_button()

    def _toggle_setup_panel(self) -> None:
        if self.current_nav_page == "settings":
            self._show_nav_page("main")
            return
        self._show_nav_page("settings")

    def _show_nav_page(self, page: str) -> None:
        page = page if page in {"main", "settings", "shortcuts", "help"} else "main"
        self.current_nav_page = page
        if hasattr(self, "main_page"):
            self.main_page.setVisible(page == "main")
        if hasattr(self, "settings_page"):
            self.settings_page.setVisible(page == "settings")
        if hasattr(self, "shortcuts_page"):
            self.shortcuts_page.setVisible(page == "shortcuts")
        if hasattr(self, "help_page"):
            self.help_page.setVisible(page == "help")
        if page == "settings" and hasattr(self, "advanced_panel"):
            self.controls_frame.setVisible(True)
            self.advanced_panel.setVisible(True)
        for key, button in self.nav_buttons.items():
            button.setProperty("active", key == page)
            button.style().unpolish(button)
            button.style().polish(button)

    def _sync_setup_nav_button(self) -> None:
        if not hasattr(self, "settings_nav_button"):
            return
        self.settings_nav_button.setText(self._t("settings"))
        self.settings_nav_button.setProperty("active", self.current_nav_page == "settings")
        self.settings_nav_button.style().unpolish(self.settings_nav_button)
        self.settings_nav_button.style().polish(self.settings_nav_button)

    def _focus_workflow_step(self, step: str) -> None:
        if self.review_mode:
            self._exit_review_mode(show_advanced=step in {"local", "qwen"})
        if step in {"import", "local", "qwen"}:
            self._show_nav_page("settings")
        self._update_workflow(step)
        if step == "import":
            self.input_edit.setFocus()
        elif step == "local":
            self.limit_spin.setFocus()
            self.advanced_panel.setVisible(True)
        elif step == "qwen":
            mode_index = self.mode_combo.findData("qwen_vision")
            if mode_index >= 0:
                self.mode_combo.setCurrentIndex(mode_index)
            self.advanced_panel.setVisible(True)
            self.api_key_edit.setFocus()
        elif step == "edit":
            self.generate_advice_button.setFocus()

    def _enter_review_mode(self, summary: dict[str, Any] | None = None) -> None:
        self.review_mode = True
        self.header_frame.setVisible(True)
        self.workflow_frame.setVisible(False)
        self.review_bar.setVisible(True)
        self._show_nav_page("main")
        processed = summary.get("processed", len(self.records)) if summary else len(self.records)
        failed = summary.get("failed", 0) if summary else 0
        visible = len(self.visible_records)
        if self.language == "zh":
            self.review_summary_label.setText(f"已完成：{processed} 张 | 失败：{failed} | 当前显示：{visible}")
        else:
            self.review_summary_label.setText(f"Done: {processed} | Failed: {failed} | Showing: {visible}")
        self._update_dashboard(summary)

    def _exit_review_mode(self, *, show_advanced: bool) -> None:
        self.review_mode = False
        self.header_frame.setVisible(True)
        self.workflow_frame.setVisible(True)
        self.review_bar.setVisible(False)
        self.advanced_panel.setVisible(True)
        self._show_nav_page("settings" if show_advanced else "main")

    def _start_analysis(self) -> None:
        if self.review_mode:
            self._exit_review_mode(show_advanced=False)
        self._show_nav_page("main")
        input_dir = Path(self.input_edit.text()).expanduser()
        output_text = self.output_edit.text().strip() or "./outputs/gui"
        if not self.output_edit.text().strip():
            self.output_edit.setText(output_text)
        output_dir = Path(output_text).expanduser()
        if not input_dir.exists():
            QMessageBox.warning(self, self._t("missing_input_title"), str(input_dir))
            return

        self.output_dir = output_dir
        self.current_run_id = f"gui-{time.strftime('%Y%m%d-%H%M%S')}"
        settings = Settings.from_env()
        settings.input_dir = input_dir
        settings.output_dir = output_dir
        settings.ai_mode = str(self.mode_combo.currentData() or "local_only")
        if hasattr(self, "vision_base_url_edit"):
            settings.vision_api_base_url = _clean_vision_base_url(self.vision_base_url_edit.text())
        model_override = _clean_vision_model_override(self.vision_model_edit.text()) if hasattr(self, "vision_model_edit") else ""
        if model_override:
            settings.vision_model = model_override
            self.detected_vision_model = settings.vision_model
        elif self.detected_vision_model:
            settings.vision_model = self.detected_vision_model
        settings.limit = self.limit_spin.value()
        settings.top_n_api_analysis = self.top_n_spin.value()
        settings.selected_ranks = f"1-{self.selected_top_spin.value()}"
        keys_text = self.api_key_edit.text().strip()
        if keys_text:
            settings.vision_api_keys = [key.strip() for key in keys_text.split(",") if key.strip()]
        if settings.ai_mode != "qwen_vision" and settings.vision_api_keys:
            reply = QMessageBox.question(
                self,
                self._t("qwen_key_local_title"),
                self._t("qwen_key_local_body"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._set_qwen_mode()
                settings.ai_mode = "qwen_vision"
                self.status_label.setText(self._t("qwen_key_promoted"))
            else:
                self.status_label.setText(self._t("qwen_not_run_local"))
        if settings.ai_mode == "qwen_vision" and not settings.vision_api_keys:
            QMessageBox.warning(
                self,
                self._t("missing_key_title"),
                self._t("missing_key_body"),
            )
            return
        if not self._confirm_run_paths(input_dir, output_dir, settings):
            self._show_nav_page("settings")
            return

        self._save_preferences()
        stop_file = output_dir / "STOP_LUMASIFT"
        stop_file.unlink(missing_ok=True)

        self.run_button.setEnabled(False)
        self.main_run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.main_cancel_button.setEnabled(True)
        self.advanced_panel.setVisible(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label.setText(self._t("step_local"))
        self.run_started_at = time.monotonic()
        self.last_progress_at = self.run_started_at
        self.last_progress_text = self._t("step_local")
        self.heartbeat_phase = 0
        self.run_heartbeat_timer.start()
        self._reset_qwen_queue_state(settings)
        self._set_grid_records([], self._t("running_grid"))
        self.detail_text.setHtml(self._empty_detail_html())
        self._update_workflow("local")
        self._update_dashboard()

        self.worker_thread = QThread()
        self.worker = AnalysisWorker(settings=settings, run_id=self.current_run_id, state_db_path=self.state_db.path)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._analysis_finished)
        self.worker.failed.connect(self._analysis_failed)
        self.worker.progress.connect(self._analysis_progress)
        self.worker.qwen_event.connect(self._analysis_qwen_event)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._analysis_thread_finished)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def _confirm_run_paths(self, input_dir: Path, output_dir: Path, settings: Settings) -> bool:
        mode_text = (
            self._t("confirm_run_qwen").format(n=settings.top_n_api_analysis)
            if settings.ai_mode == "qwen_vision"
            else self._t("confirm_run_local")
        )
        body = self._t("confirm_run_body").format(
            input_dir=input_dir,
            output_dir=output_dir,
            mode=mode_text,
        )
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(self._t("confirm_run_title"))
        box.setText(body)
        start_button = box.addButton(self._t("confirm_run_start"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(self._t("confirm_run_settings"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(start_button)
        box.exec()
        return box.clickedButton() == start_button

    def _analysis_thread_finished(self) -> None:
        self.worker_thread = None
        self.worker = None
        self._finish_pending_close_if_ready()

    def _analysis_finished(self, payload: dict) -> None:
        self.run_heartbeat_timer.stop()
        self.records = list(payload["report"].get("records", []))
        self._merge_user_labels()
        self._write_current_reports()
        was_cancelled = (self.output_dir / "STOP_LUMASIFT").exists()
        self.status_label.setText(
            f"{self._t('cancel')}: {payload['summary']['processed']} / {payload['summary']['failed']}"
            if was_cancelled
            else f"{self._t('done')}: {payload['summary']['processed']} / {payload['summary']['failed']}"
        )
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.run_button.setEnabled(True)
        self.main_run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.main_cancel_button.setEnabled(False)
        self._refresh_filter_options()
        self._populate_records()
        self._update_workflow("edit")
        self._update_dashboard(payload["summary"])
        self._fade_in(self.photo_list)
        self._enter_review_mode(payload["summary"])

    def _analysis_failed(self, message: str) -> None:
        self.run_heartbeat_timer.stop()
        if self.review_mode:
            self._exit_review_mode(show_advanced=True)
        self.status_label.setText(self._t("failed"))
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.run_button.setEnabled(True)
        self.main_run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.main_cancel_button.setEnabled(False)
        self._update_workflow("import")
        QMessageBox.critical(self, "Analysis failed", message)

    def _check_qwen_key(self) -> None:
        keys = self._configured_qwen_keys()
        if not keys:
            QMessageBox.warning(self, self._t("missing_key_title"), self._t("missing_key_body"))
            return
        self.check_key_button.setEnabled(False)
        self.status_label.setText(self._t("checking_key"))
        self.cache_note.setText(self._t("checking_key"))
        self.key_check_thread = QThread()
        base_url = _vision_base_url_override(self.vision_base_url_edit.text() if hasattr(self, "vision_base_url_edit") else "")
        model_text = _clean_vision_model_override(self.vision_model_edit.text()) if hasattr(self, "vision_model_edit") else ""
        preferred_model = model_text if model_text and model_text != self.detected_vision_model else ""
        if hasattr(self, "vision_model_edit") and not preferred_model:
            self.vision_model_edit.clear()
        self.key_check_worker = VisionKeyCheckWorker(keys, self.language, base_url, preferred_model)
        self.key_check_worker.moveToThread(self.key_check_thread)
        self.key_check_thread.started.connect(self.key_check_worker.run)
        self.key_check_worker.finished.connect(self._qwen_key_check_finished)
        self.key_check_worker.failed.connect(self._qwen_key_check_failed)
        self.key_check_worker.finished.connect(self.key_check_thread.quit)
        self.key_check_worker.failed.connect(self.key_check_thread.quit)
        self.key_check_thread.finished.connect(self._qwen_key_check_thread_finished)
        self.key_check_thread.finished.connect(self.key_check_thread.deleteLater)
        self.key_check_thread.start()

    def _configured_qwen_keys(self) -> list[str]:
        keys_text = self.api_key_edit.text().strip() if hasattr(self, "api_key_edit") else ""
        if keys_text:
            return [key.strip() for key in keys_text.split(",") if key.strip()]
        try:
            return Settings.from_env().vision_api_keys
        except Exception:
            return []

    def _qwen_key_check_finished(self, summary: str, model: str, base_url: str) -> None:
        if hasattr(self, "vision_base_url_edit"):
            detected_base_url = _clean_vision_base_url(base_url)
            self.vision_base_url_edit.setText(detected_base_url)
            self.settings_store.setValue("vision_base_url", detected_base_url)
        if model:
            self.detected_vision_model = model
            self.settings_store.setValue("vision_model", model)
            if hasattr(self, "vision_model_edit"):
                self.vision_model_edit.setText(model)
        self.cache_note.setText(summary)
        self.status_label.setText(self._t("key_check_ok"))
        self.check_key_button.setEnabled(True)

    def _qwen_key_check_failed(self, message: str) -> None:
        compact = message[:220] + ("..." if len(message) > 220 else "")
        self.cache_note.setText(f"{self._t('key_check_failed')}: {compact}")
        self.status_label.setText(self._t("key_check_failed"))
        self.check_key_button.setEnabled(True)

    def _qwen_key_check_thread_finished(self) -> None:
        self.key_check_thread = None
        self.key_check_worker = None

    def _analysis_progress(self, stage: str, current: int, total: int) -> None:
        self._update_workflow("qwen" if stage == "qwen" else "local")
        if total <= 0:
            self.progress.setRange(0, 0)
            text = f"{stage}: preparing..."
            self.last_progress_at = time.monotonic()
            self.last_progress_text = text
            self.status_label.setText(text)
            return
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 100)
        value = int((current / total) * 100)
        self.progress.setValue(max(0, min(100, value)))
        label = {
            "manifest": "Scanning files",
            "local": "Local RAW/preview analysis",
            "qwen": "LLM Deep Analysis",
            "done": "Done",
        }.get(stage, stage)
        text = f"{label}: {current}/{total}"
        self.last_progress_at = time.monotonic()
        self.last_progress_text = text
        self.status_label.setText(text)

    def _run_heartbeat_tick(self) -> None:
        if self.worker_thread is None or not self.worker_thread.isRunning():
            self.run_heartbeat_timer.stop()
            return
        now = time.monotonic()
        elapsed = max(0, int(now - self.run_started_at)) if self.run_started_at else 0
        minutes, seconds = divmod(elapsed, 60)
        dots = "." * ((self.heartbeat_phase % 3) + 1)
        self.heartbeat_phase += 1
        base = self.last_progress_text or self._t("step_local")
        if self.last_progress_at and now - self.last_progress_at >= 10:
            base = self._t("running_alive_hint")
        self.status_label.setText(f"{base}{dots} {self._t('elapsed')} {minutes:02d}:{seconds:02d}")

    def _reset_qwen_queue_state(self, settings: Settings) -> None:
        enabled = settings.ai_mode == "qwen_vision"
        self.qwen_queue_state = {
            "enabled": enabled,
            "model": settings.vision_model,
            "total": settings.top_n_api_analysis if enabled else 0,
            "queued": settings.top_n_api_analysis if enabled else 0,
            "running": "",
            "done": 0,
            "cache": 0,
            "failed": 0,
            "last_error": "",
            "retrying": 0,
            "cancelled": 0,
            "cancelling": False,
            "phase": "等待候选队列" if self.language == "zh" else "Preparing candidate queue",
        }
        self._render_qwen_queue_state()

    def _analysis_qwen_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type", ""))
        if event_type == "qwen_queue_prepared":
            total = int(event.get("total", 0) or 0)
            self.qwen_queue_state.update(
                {
                    "enabled": True,
                    "model": str(event.get("model", self.qwen_queue_state.get("model", self._t("qwen")))),
                    "total": total,
                    "queued": total,
                    "running": "",
                    "done": 0,
                    "cache": 0,
                    "failed": 0,
                    "last_error": "",
                    "retrying": 0,
                    "cancelled": 0,
                    "cancelling": False,
                    "phase": "候选队列已生成" if self.language == "zh" else "Candidate queue ready",
                }
            )
        elif event_type == "qwen_candidate_running":
            self.qwen_queue_state["queued"] = max(0, int(self.qwen_queue_state.get("queued", 0) or 0) - 1)
            self.qwen_queue_state["running"] = str(event.get("filename") or Path(str(event.get("path", ""))).name)
            self.qwen_queue_state["phase"] = "压缩预览 / 上传 LLM 深度分析 / 等待模型返回" if self.language == "zh" else "Compressing preview / sending LLM deep-analysis request / waiting for model"
        elif event_type == "qwen_vision_verified":
            model = str(event.get("model") or "").strip()
            base_url = str(event.get("base_url") or "").strip()
            if model:
                self.qwen_queue_state["model"] = model
                self.detected_vision_model = model
                if hasattr(self, "vision_model_edit"):
                    self.vision_model_edit.setText(model)
                self.settings_store.setValue("vision_model", model)
            if base_url and hasattr(self, "vision_base_url_edit"):
                self.vision_base_url_edit.setText(base_url)
                self.settings_store.setValue("vision_base_url", base_url)
            self.qwen_queue_state["phase"] = "视觉模型探针通过，开始深度分析" if self.language == "zh" else "Vision probe passed; starting deep analysis"
        elif event_type == "qwen_candidate_finished":
            status = str(event.get("status", "done"))
            if status == "cache-hit":
                self.qwen_queue_state["cache"] = int(self.qwen_queue_state.get("cache", 0) or 0) + 1
            else:
                self.qwen_queue_state["done"] = int(self.qwen_queue_state.get("done", 0) or 0) + 1
            self.qwen_queue_state["running"] = ""
            self.qwen_queue_state["phase"] = "解析证据并写入结果" if self.language == "zh" else "Parsing evidence and writing result"
        elif event_type == "qwen_candidate_failed":
            self.qwen_queue_state["failed"] = int(self.qwen_queue_state.get("failed", 0) or 0) + 1
            self.qwen_queue_state["running"] = ""
            error = str(event.get("error", "") or "")
            if error:
                self.qwen_queue_state["last_error"] = error[:420]
            self.qwen_queue_state["phase"] = "当前照片失败，继续下一张" if self.language == "zh" else "Current photo failed; continuing"
        elif event_type == "qwen_candidate_cancelled":
            self.qwen_queue_state["queued"] = max(0, int(self.qwen_queue_state.get("queued", 0) or 0) - 1)
            self.qwen_queue_state["cancelled"] = int(self.qwen_queue_state.get("cancelled", 0) or 0) + 1
            self.qwen_queue_state["running"] = ""
            self.qwen_queue_state["cancelling"] = True
            self.qwen_queue_state["phase"] = "正在暂停深评" if self.language == "zh" else "Pausing deep review"
        elif event_type == "qwen_queue_cancelled":
            self.qwen_queue_state["queued"] = 0
            self.qwen_queue_state["cancelling"] = False
            self.qwen_queue_state["phase"] = "深评已暂停" if self.language == "zh" else "Deep review paused"
        elif event_type == "qwen_client_event":
            client_event = event.get("client_event", {})
            if isinstance(client_event, dict) and str(client_event.get("type", "")) == "retrying":
                self.qwen_queue_state["retrying"] = int(self.qwen_queue_state.get("retrying", 0) or 0) + 1
                self.qwen_queue_state["phase"] = "供应商限流/超时，正在重试" if self.language == "zh" else "Provider timeout/rate limit; retrying"
        self._render_qwen_queue_state()

    def _render_qwen_queue_state(self) -> None:
        if not hasattr(self, "qwen_queue_label"):
            return
        if not self.qwen_queue_state.get("enabled"):
            if (
                hasattr(self, "mode_combo")
                and (self.mode_combo.currentData() or self.mode_combo.currentText()) != "qwen_vision"
                and self._has_configured_qwen_keys()
            ):
                hint = self._t("qwen_key_local_hint")
                self.qwen_queue_label.setToolTip(hint)
                self.qwen_queue_label.setText(
                    f"<span style='font-weight:900; color:#f8fafc;'>{self._escape(self._t('qwen'))}</span>"
                    f"&nbsp;&nbsp;<span style='color:#ffd400;'>! {self._escape(hint)}</span>"
                )
                self.qwen_queue_label.setVisible(True)
                self.qwen_status_frame.setVisible(True)
                self.qwen_progress.setRange(0, 1)
                self.qwen_progress.setValue(0)
                self.qwen_stage_label.setText("")
            else:
                self.qwen_status_frame.setVisible(False)
                self.qwen_queue_label.setVisible(False)
                self.qwen_queue_label.setText("")
            return
        model = self.qwen_queue_state.get("model", self._t("qwen"))
        running = str(self.qwen_queue_state.get("running", "") or "")
        if len(running) > 32:
            running = f"{running[:29]}..."
        labels = {
            "queued": "排队" if self.language == "zh" else "Queued",
            "running": "运行" if self.language == "zh" else "Running",
            "done": "完成" if self.language == "zh" else "Done",
            "cache": "缓存" if self.language == "zh" else "Cache",
            "failed": "失败" if self.language == "zh" else "Failed",
            "retry": "重试" if self.language == "zh" else "Retry",
            "cancelled": "取消" if self.language == "zh" else "Cancelled",
        }
        queued = self.qwen_queue_state.get("queued", 0)
        done = self.qwen_queue_state.get("done", 0)
        cache = self.qwen_queue_state.get("cache", 0)
        failed = self.qwen_queue_state.get("failed", 0)
        last_error = str(self.qwen_queue_state.get("last_error", "") or "")
        retrying = self.qwen_queue_state.get("retrying", 0)
        cancelled = self.qwen_queue_state.get("cancelled", 0)
        cancelling = bool(self.qwen_queue_state.get("cancelling"))
        total = int(self.qwen_queue_state.get("total", 0) or 0)
        completed = int(done or 0) + int(cache or 0) + int(failed or 0) + int(cancelled or 0)
        text = (
            f"<span style='font-weight:900; color:#f8fafc;'>{self._escape(self._t('qwen'))}</span>"
            f"&nbsp;&nbsp;<span style='color:#9fb0c2;'>{self._escape(str(model))}</span>"
            f"&nbsp;&nbsp;&nbsp;<span title='{labels['queued']}' style='color:#9fb0c2;'>● <b>{queued}</b></span>"
            f"&nbsp;&nbsp;<span title='{labels['running']}' style='color:#ffd400;'>▶ <b>{self._escape(running or '0')}</b></span>"
            f"&nbsp;&nbsp;<span title='{labels['done']}' style='color:#00a6ff;'>√ <b>{done}</b></span>"
            f"&nbsp;&nbsp;<span title='{labels['cache']}' style='color:#61d394;'>⚡ <b>{cache}</b></span>"
            f"&nbsp;&nbsp;<span title='{labels['failed']}' style='color:#ff3b30;'>! <b>{failed}</b></span>"
            f"&nbsp;&nbsp;<span title='{labels['retry']}' style='color:#ff9f1c;'>↻ <b>{retrying}</b></span>"
            f"&nbsp;&nbsp;<span title='{labels['cancelled']}' style='color:#a78bfa;'>- <b>{cancelled}</b></span>"
        )
        phase = str(self.qwen_queue_state.get("phase", "") or "")
        if not phase:
            if cancelling:
                phase = "正在暂停深评" if self.language == "zh" else "Pausing deep review"
            elif running:
                phase = "压缩预览 / 上传 LLM 深度分析 / 等待模型返回" if self.language == "zh" else "Compressing preview / sending LLM deep-analysis request / waiting for model"
            elif completed and completed >= total and total:
                phase = "深评完成，正在汇总结果" if self.language == "zh" else "Deep review complete; consolidating results"
            else:
                phase = "等待候选队列" if self.language == "zh" else "Preparing candidate queue"
        if cancelling:
            text += "&nbsp;&nbsp;<span style='color:#a78bfa;'>...</span>"
        if failed and last_error:
            text += f"&nbsp;&nbsp;<span style='color:#ff9f1c;'>{self._escape(self._t('qwen_failures_hint'))}</span>"
        self.qwen_queue_label.setToolTip(
            f"{self._t('qwen')} {model}: {labels['queued']} {queued}, {labels['running']} {running or '0'}, "
            f"{labels['done']} {done}, {labels['cache']} {cache}, {labels['failed']} {failed}, "
            f"{labels['retry']} {retrying}, {labels['cancelled']} {cancelled}"
            + (f"\n\n{last_error}" if last_error else "")
        )
        self.qwen_queue_label.setText(text)
        self.qwen_queue_label.setVisible(True)
        self.qwen_progress.setRange(0, max(1, total))
        self.qwen_progress.setValue(max(0, min(max(1, total), completed)))
        self.qwen_stage_label.setText(phase)
        self.qwen_status_frame.setVisible(True)

    def _populate_records(self) -> None:
        if not hasattr(self, "photo_list"):
            return
        selected_keys = self._selected_record_keys()
        self._stop_thumbnail_worker()
        self.thumbnail_generation += 1
        self.loaded_thumbnail_rows.clear()
        self.pending_thumbnail_rows.clear()
        self.visible_records = self._filtered_records()[: self.display_limit_spin.value()]
        if not self.visible_records:
            self.result_count_label.setText(f"Showing 0/{len(self.records)}")
            self.status_label.setText(self._t("no_results"))
            self._update_dashboard()
            self._show_empty_grid(self._t("empty_filtered"))
            return
        self._set_grid_records(self.visible_records)
        self._restore_selection_by_keys(selected_keys)
        self.result_count_label.setText(f"{len(self.visible_records)}/{len(self.records)}")
        self.status_label.setText(f"{len(self.visible_records)}/{len(self.records)}")
        self._update_dashboard()
        self._queue_visible_thumbnails()

    def _show_empty_grid(self, message: str) -> None:
        self._set_grid_records([], message)

    def _set_grid_records(self, records: list[dict[str, Any]], empty_message: str | None = None) -> None:
        if self.photo_model is not None:
            self.photo_model.set_records(records, empty_message)

    def _record_key(self, record: dict[str, Any]) -> str:
        path = str(record.get("path", "") or "")
        if not path:
            return str(record.get("filename", "") or "")
        try:
            return str(Path(path).expanduser().resolve())
        except OSError:
            return str(Path(path).expanduser())

    def _canonical_record(self, record: dict[str, Any]) -> dict[str, Any]:
        key = self._record_key(record)
        for candidate in self.records:
            if self._record_key(candidate) == key:
                return candidate
        return record

    def _normalized_user_label(self, record: dict[str, Any]) -> str:
        return normalized_user_label(record.get("user_label"))

    def _selected_record_keys(self) -> set[str]:
        keys: set[str] = set()
        for index in self._selected_record_indexes():
            record = index.data(Qt.ItemDataRole.UserRole)
            if isinstance(record, dict):
                keys.add(self._record_key(record))
        return keys

    def _restore_selection_by_keys(self, selected_keys: set[str]) -> None:
        if not selected_keys or self.photo_model is None or self.photo_list.selectionModel() is None:
            return
        selection_model = self.photo_list.selectionModel()
        selection_model.clearSelection()
        first_selected: QModelIndex | None = None
        for row, record in enumerate(self.photo_model.records):
            if self._record_key(record) not in selected_keys:
                continue
            index = self.photo_model.index(row, 0)
            selection_model.select(
                index,
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
            )
            if first_selected is None:
                first_selected = index
        if first_selected is not None:
            self.photo_list.scrollTo(first_selected, QAbstractItemView.ScrollHint.PositionAtCenter)
            self.photo_list.setCurrentIndex(first_selected)

    def _filtered_records(self) -> list[dict[str, Any]]:
        records = list(self.records)
        query = self.search_edit.text().strip().lower() if hasattr(self, "search_edit") else ""
        category = self.category_filter.currentData() if hasattr(self, "category_filter") else "all"
        tone_filter = self.tone_filter.currentData() if hasattr(self, "tone_filter") else "all"
        label_filter = self.label_filter.currentData() if hasattr(self, "label_filter") else "all"
        group_filter = self.group_filter.currentData() if hasattr(self, "group_filter") else "all"
        pair_filter = self.pair_filter.currentData() if hasattr(self, "pair_filter") else "all"
        review_filter = self.review_filter.currentData() if hasattr(self, "review_filter") else "all"
        if category and category != "all":
            records = [record for record in records if str(record.get("category", "")) == category]
        if tone_filter and tone_filter != "all":
            records = [record for record in records if str(record.get("tone_category", "")) == str(tone_filter)]
        if label_filter and label_filter != "all":
            if label_filter == "unlabeled":
                records = [record for record in records if not self._normalized_user_label(record)]
            else:
                records = [record for record in records if self._normalized_user_label(record) == label_filter]
        if group_filter and group_filter != "all":
            if group_filter == "best":
                records = [record for record in records if int(record.get("group_size", 1) or 1) <= 1 or bool(record.get("is_group_best"))]
            elif group_filter == "grouped":
                records = [record for record in records if int(record.get("group_size", 1) or 1) > 1]
            elif group_filter == "time":
                records = [
                    record
                    for record in records
                    if int(record.get("group_size", 1) or 1) > 1 and "time" in str(record.get("group_basis") or "")
                ]
            elif group_filter == "visual":
                records = [
                    record
                    for record in records
                    if int(record.get("group_size", 1) or 1) > 1 and (str(record.get("group_basis") or "visual") in {"visual", "visual_time"})
                ]
            elif group_filter == "singletons":
                records = [record for record in records if int(record.get("group_size", 1) or 1) <= 1]
        if pair_filter and pair_filter != "all":
            records = [record for record in records if str(record.get("pair_status") or "single") == str(pair_filter)]
        if review_filter and review_filter != "all":
            records = [record for record in records if self._record_matches_review_filter(record, str(review_filter))]
        if query:
            records = [
                record
                for record in records
                if query
                in " ".join(
                    [
                        str(record.get("filename", "")),
                        str(record.get("path", "")),
                        str(record.get("category", "")),
                        str(record.get("tone_category", "")),
                        str(record.get("user_label", "")),
                        str(record.get("recommended_style", "")),
                        str(record.get("pair_status", "")),
                        str(record.get("paired_raw_path", "")),
                        str(record.get("paired_jpeg_path", "")),
                    ]
                ).lower()
            ]

        sort_key = self.sort_combo.currentData() if hasattr(self, "sort_combo") else "score_desc"
        if sort_key == "score_asc":
            records.sort(key=lambda item: float(item.get("final_selection_score", 0) or 0))
        elif sort_key == "user_priority":
            records.sort(
                key=lambda item: (
                    int(item.get("user_feedback_priority", 0) or 0),
                    float(item.get("final_selection_score", 0) or 0),
                ),
                reverse=True,
            )
        elif sort_key == "filename":
            records.sort(key=lambda item: str(item.get("filename", "")).lower())
        elif sort_key == "rank":
            records.sort(key=lambda item: int(item.get("rank", 999999) or 999999))
        else:
            records.sort(key=lambda item: float(item.get("final_selection_score", 0) or 0), reverse=True)
        return records

    def _record_matches_review_filter(self, record: dict[str, Any], review_filter: str) -> bool:
        bucket = self._qwen_review_bucket(record)
        if review_filter == "reviewed":
            return bucket == "concrete"
        return bucket == review_filter

    def _qwen_review_bucket(self, record: dict[str, Any]) -> str:
        status = str(record.get("qwen_status") or "").strip().lower()
        source = str(record.get("analysis_source") or "").strip().lower()
        quality = str(record.get("analysis_quality") or "").strip().lower()
        if is_current_concrete_qwen_review(record):
            return "concrete"
        if status in {"done", "cache-hit"} or source == "qwen_vision":
            return "not_reviewed" if quality == "concrete" else "weak"
        if status == "failed" or status.startswith("retry"):
            return "failed"
        if status == "cancelled" or status.startswith("skipped"):
            return "skipped"
        return "not_reviewed"

    def _refresh_filter_options(self) -> None:
        self._reset_filter_combos()

    def _placeholder_icon(self) -> QIcon:
        pixmap = QPixmap(210, 148)
        pixmap.fill(QColor("#e8edf3"))
        return QIcon(pixmap)

    def _start_thumbnail_worker(self) -> None:
        if not self.visible_records or self.thumbnail_thread is not None:
            return
        rows = sorted(self.pending_thumbnail_rows)[:96]
        if not rows:
            return
        for row in rows:
            self.pending_thumbnail_rows.discard(row)
        jobs = [(row, self.visible_records[row]) for row in rows if 0 <= row < len(self.visible_records)]
        if not jobs:
            return
        self.thumbnail_thread = QThread()
        self.thumbnail_worker = ThumbnailWorker(jobs, self.output_dir, self.thumbnail_generation, max_side=360)
        self.thumbnail_worker.moveToThread(self.thumbnail_thread)
        self.thumbnail_thread.started.connect(self.thumbnail_worker.run)
        self.thumbnail_worker.thumbnail_ready.connect(self._thumbnail_ready)
        self.thumbnail_worker.finished.connect(self.thumbnail_thread.quit)
        self.thumbnail_thread.finished.connect(self._thumbnail_thread_finished)
        self.thumbnail_thread.finished.connect(self.thumbnail_thread.deleteLater)
        self.thumbnail_thread.start()

    def _queue_visible_thumbnails(self) -> None:
        if not self.visible_records or self.photo_model is None:
            return
        viewport = self.photo_list.viewport().rect().adjusted(-260, -260, 260, 520)
        rows: list[int] = []
        row_count = self.photo_model.rowCount()
        for row in range(row_count):
            index = self.photo_model.index(row, 0)
            rect = self.photo_list.visualRect(index)
            if rect.isValid() and rect.intersects(viewport):
                rows.append(row)
        if not rows:
            rows = list(range(min(36, len(self.visible_records))))
        for row in rows[:120]:
            if row not in self.loaded_thumbnail_rows:
                self.pending_thumbnail_rows.add(row)
        self._start_thumbnail_worker()

    def _thumbnail_thread_finished(self) -> None:
        self.thumbnail_worker = None
        self.thumbnail_thread = None
        if self.pending_close:
            self._finish_pending_close_if_ready()
            return
        if self.pending_thumbnail_rows:
            self._start_thumbnail_worker()

    def _stop_thumbnail_worker(self) -> None:
        if self.thumbnail_worker is not None:
            self.thumbnail_worker.stop()
        if self.thumbnail_thread is not None and self.thumbnail_thread.isRunning():
            self.thumbnail_thread.quit()
            if not self.thumbnail_thread.wait(2500):
                return
        self.thumbnail_worker = None
        self.thumbnail_thread = None

    def _thumbnail_ready(self, generation: int, row: int, preview_path: str) -> None:
        if generation != self.thumbnail_generation or not preview_path or self.photo_model is None:
            return
        if row < 0 or row >= len(self.visible_records):
            return
        pixmap = QPixmap(preview_path)
        if not pixmap.isNull():
            self.loaded_thumbnail_rows.add(row)
            self.photo_model.set_icon(row, QIcon(pixmap))

    def _open_large_preview(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        record = index.data(Qt.ItemDataRole.UserRole)
        if not record:
            return
        path = Path(str(record.get("path", "")))
        if not path.exists():
            QMessageBox.information(self, self._t("no_results"), str(path))
            return
        dialog = LargePreviewDialog(record, self.output_dir, self.language, self)
        dialog.destroyed.connect(lambda *_: self.preview_dialogs.remove(dialog) if dialog in self.preview_dialogs else None)
        self.preview_dialogs.append(dialog)
        screen = QApplication.primaryScreen()
        if screen is not None:
            geometry = screen.availableGeometry()
            dialog.resize(int(geometry.width() * 0.92), int(geometry.height() * 0.9))
            dialog.move(
                geometry.x() + int((geometry.width() - dialog.width()) / 2),
                geometry.y() + int((geometry.height() - dialog.height()) / 2),
            )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _show_selected_detail(self) -> None:
        selected = self._selected_record_indexes()
        if not selected:
            self.detail_text.setHtml(self._empty_detail_html())
            self._sync_crop_preview_button()
            self._update_dashboard()
            return
        record = selected[0].data(Qt.ItemDataRole.UserRole)
        self.detail_text.setHtml(self._format_record_detail_html(record, len(selected)))
        self._sync_crop_preview_button()
        self._update_dashboard()
        self._fade_in(self.detail_text, duration=180)

    def _sync_crop_preview_button(self) -> None:
        if not hasattr(self, "crop_preview_button"):
            return
        selected = self._selected_record_indexes()
        record = selected[0].data(Qt.ItemDataRole.UserRole) if selected else None
        has_crop = isinstance(record, dict) and _record_crop_box(record) is not None
        self.crop_preview_button.setEnabled(has_crop)
        self.crop_preview_button.setToolTip(self._t("crop_preview_tooltip") if has_crop else self._t("crop_preview_disabled"))
        self._sync_deep_review_selected_button()

    def _open_selected_crop_preview(self) -> None:
        selected = self._selected_record_indexes()
        record = selected[0].data(Qt.ItemDataRole.UserRole) if selected else None
        if not isinstance(record, dict) or _record_crop_box(record) is None:
            QMessageBox.information(self, self._t("no_crop_box_title"), self._t("crop_preview_disabled"))
            return
        self._open_large_preview(selected[0])

    def _sync_deep_review_selected_button(self) -> None:
        if not hasattr(self, "deep_review_selected_button"):
            return
        selected = self._selected_record_indexes()
        running = self.selected_review_thread is not None and self.selected_review_thread.isRunning()
        self.deep_review_selected_button.setEnabled(bool(selected) and not running)
        self.deep_review_selected_button.setToolTip(self._t("deep_review_selected_tooltip") if selected else self._t("select_first"))

    def _settings_for_selected_deep_review(self) -> Settings:
        settings = Settings.from_env()
        output_text = self.output_edit.text().strip() if hasattr(self, "output_edit") else ""
        settings.output_dir = Path(output_text or str(self.output_dir)).expanduser()
        settings.ai_mode = "qwen_vision"
        if hasattr(self, "vision_base_url_edit"):
            settings.vision_api_base_url = _clean_vision_base_url(self.vision_base_url_edit.text())
        model_override = _clean_vision_model_override(self.vision_model_edit.text()) if hasattr(self, "vision_model_edit") else ""
        if model_override:
            settings.vision_model = model_override
        elif self.detected_vision_model:
            settings.vision_model = self.detected_vision_model
        keys_text = self.api_key_edit.text().strip() if hasattr(self, "api_key_edit") else ""
        if keys_text:
            settings.vision_api_keys = [key.strip() for key in keys_text.split(",") if key.strip()]
        return settings

    def _deep_review_selected(self) -> None:
        selected = self._selected_record_indexes()
        if not selected:
            QMessageBox.information(self, self._t("no_selection"), self._t("select_first"))
            return
        display_record = selected[0].data(Qt.ItemDataRole.UserRole)
        if not isinstance(display_record, dict):
            return
        record = self._canonical_record(display_record)
        if not record.get("path") or not Path(str(record.get("path"))).exists():
            QMessageBox.information(self, self._t("no_results"), str(record.get("path", "")))
            return
        settings = self._settings_for_selected_deep_review()
        if not settings.vision_api_keys:
            QMessageBox.warning(self, self._t("missing_key_title"), self._t("missing_key_body"))
            self._show_nav_page("settings")
            self.advanced_panel.setVisible(True)
            self.api_key_edit.setFocus()
            return
        self.output_dir = settings.output_dir
        settings.output_dir.mkdir(parents=True, exist_ok=True)
        self._save_preferences()
        self.deep_review_selected_button.setEnabled(False)
        self.action_status_label.setText(self._t("deep_review_running"))
        self.status_label.setText(self._t("deep_review_running"))
        self.selected_review_thread = QThread()
        self.selected_review_worker = SelectedDeepReviewWorker(record, settings, settings.output_dir)
        self.selected_review_worker.moveToThread(self.selected_review_thread)
        self.selected_review_thread.started.connect(self.selected_review_worker.run)
        self.selected_review_worker.progress.connect(self._selected_review_progress)
        self.selected_review_worker.finished.connect(self._selected_review_finished)
        self.selected_review_worker.failed.connect(self._selected_review_failed)
        self.selected_review_worker.finished.connect(self.selected_review_thread.quit)
        self.selected_review_worker.failed.connect(self.selected_review_thread.quit)
        self.selected_review_thread.finished.connect(self._selected_review_thread_finished)
        self.selected_review_thread.finished.connect(self.selected_review_thread.deleteLater)
        self.selected_review_thread.start()

    def _selected_review_progress(self, stage: str) -> None:
        text = self._t("deep_review_running")
        if stage == "vision_check":
            text = "正在确认当前模型真的能看图..." if self.language == "zh" else "Verifying the model can actually read images..."
        elif stage == "preview":
            text = "正在生成深评预览..." if self.language == "zh" else "Preparing preview for deep review..."
        elif stage == "deep_review":
            text = self._t("deep_review_running")
        self.action_status_label.setText(text)
        self.status_label.setText(text)

    def _selected_review_finished(self, updated_record: dict[str, Any]) -> None:
        selected_keys = self._selected_record_keys()
        target_key = self._record_key(updated_record)
        for index, record in enumerate(self.records):
            if self._record_key(record) == target_key:
                record.update(updated_record)
                break
        self.records = rank_records(self.records)
        self._write_current_reports()
        self._refresh_filter_options()
        self._populate_records()
        self._restore_selection_by_keys(selected_keys or {target_key})
        self._show_selected_detail()
        self.action_status_label.setText(self._t("deep_review_done"))
        self.status_label.setText(self._t("deep_review_done"))
        self._update_workflow("edit")

    def _selected_review_failed(self, message: str) -> None:
        compact = self._humanize_llm_failure_message(message)
        compact = compact[:300] + ("..." if len(compact) > 300 else "")
        self._mark_selected_deep_review_failed(message)
        self.action_status_label.setText(f"{self._t('deep_review_failed')}: {compact}")
        self.status_label.setText(self._t("deep_review_failed"))
        self._show_selected_detail()
        QMessageBox.warning(self, self._t("deep_review_failed"), compact)

    def _mark_selected_deep_review_failed(self, message: str) -> None:
        selected = self._selected_record_indexes()
        if not selected:
            return
        display_record = selected[0].data(Qt.ItemDataRole.UserRole)
        if not isinstance(display_record, dict):
            return
        record = self._canonical_record(display_record)
        clear_qwen_review_fields(record, status="failed", reason=message)
        self._write_current_reports()

    def _humanize_llm_failure_message(self, message: str) -> str:
        raw = str(message or "").strip()
        lower = raw.lower()
        if "metric-driven" in lower or "too indecisive" in lower or "too generic" in lower:
            if self.language == "zh":
                return (
                    "模型返回的是指标化/模棱两可内容，不是基于照片画面的专业判断。"
                    "这通常说明当前模型没有真正读取 image_url，或供应商把请求路由到了非视觉模型。"
                    "请先在设置里点“检查”，让程序选择通过视觉探针的模型；未通过前不要继续烧深评 token。"
                )
            return (
                "The model returned metric-driven or indecisive text instead of a visual photo read. "
                "This usually means the provider routed the request to a non-vision model or image_url was not actually consumed."
            )
        if "live image-vision probe" in lower or "no suitable model" in lower or "failed the live image" in lower:
            if self.language == "zh":
                return "当前接口/模型没有通过真实看图探针。key 可能有效，但这个模型不能用于照片深评；请检查接口地址或换支持视觉的模型。"
            return "The endpoint/key may be valid, but no configured model passed the live image-vision probe."
        return raw

    def _selected_review_thread_finished(self) -> None:
        self.selected_review_worker = None
        self.selected_review_thread = None
        self._sync_deep_review_selected_button()
        self._finish_pending_close_if_ready()

    def _first_score(self, record: dict[str, Any], *keys: str) -> float:
        for key in keys:
            value = self._number(record.get(key, 0))
            if value:
                return value
        return 0.0

    def _number(self, value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def _display_category(self, value: Any) -> str:
        raw = str(value or "")
        if self.language != "zh":
            return raw.replace("_", " ")
        return {
            "portfolio_candidate": "作品候选",
            "strong_edit_candidate": "强修图候选",
            "story_candidate": "故事候选",
            "technically_weak_but_interesting": "技术弱但有趣",
            "ordinary_record": "普通记录",
            "reject_candidate": "淘汰候选",
            "failed": "处理失败",
        }.get(raw, raw.replace("_", " "))

    def _display_style(self, value: Any) -> str:
        raw = str(value or "")
        if self.language != "zh":
            return raw.replace("_", " ")
        return {
            "pending_vision_review": "等待深评",
            "high_contrast_bw_documentary": "高反差黑白纪实",
            "low_key_noir_street": "低调黑色街头",
            "cinematic_urban_color": "电影感城市彩色",
            "muted_humanistic_color": "克制人文彩色",
            "gritty_flash_street": "粗粝闪光街头",
            "soft_editorial_documentary": "柔和编辑纪实",
            "cold_metropolitan": "冷调都市",
            "warm_memory_tone": "暖调记忆感",
            "do_not_overedit": "克制轻修",
        }.get(raw, raw.replace("_", " "))

    def _display_tone_category(self, value: Any) -> str:
        raw = str(value or "")
        if not raw:
            return ""
        if self.language != "zh":
            return raw.replace("_", " ")
        return {
            "monochrome_or_near_bw": "近黑白",
            "high_contrast": "高反差",
            "low_key": "低调暗部",
            "high_key": "高调明亮",
            "warm_tone": "暖调",
            "cool_tone": "冷调",
            "vivid_color": "高饱和",
            "muted_color": "低饱和",
        }.get(raw, raw.replace("_", " "))

    def _display_user_label(self, value: Any) -> str:
        raw = str(value or "unlabeled")
        if self.language != "zh":
            return raw.replace("_", " ")
        return {"keep": "保留", "maybe": "待定", "reject": "淘汰", "unlabeled": "未标记"}.get(raw, raw)

    def _display_story(self, record: dict[str, Any]) -> str:
        if str(record.get("analysis_source") or "") == "qwen_vision" and not self._is_displayable_qwen_review(record):
            return self._local_story_summary(record)
        raw = str(record.get("story_interpretation", "") or "").strip()
        if self.language == "zh" and (not raw or raw == "Not available in local_only mode." or raw.startswith("Local pre-screen only:")):
            return self._local_story_summary(record)
        return raw or ("LLM Deep Analysis has not been run yet." if self.language != "zh" else "等待 LLM 深度分析。")

    def _local_story_summary(self, record: dict[str, Any]) -> str:
        metrics = record.get("local_metrics") if isinstance(record.get("local_metrics"), dict) else {}
        brightness = self._number(metrics.get("brightness"))
        contrast = self._number(metrics.get("contrast"))
        tension = self._first_score(record, "visual_tension_score")
        editability = self._first_score(record, "editability_score", "editing_potential_score")
        if str(record.get("qwen_status") or "").lower() == "failed":
            failure = self._qwen_failure_message(record)
            return (
                "【LLM 深评失败】这不是专业深评结果。"
                f"{failure} "
                f"当前只保留本地技术草稿：亮度约 {brightness:.0f}、对比约 {contrast:.0f}、结构代理分 {tension:.0f}、可修潜力 {editability:.0f}。"
                "请先检查 API/网络后重跑深评，再根据人物、动作和瞬间做最终选片。"
            )
        parts = [
            "【仅本地预筛，不是专业深评】本地算法只能判断明暗、边缘密度、可修空间和技术风险；不能识别人、手势、情绪和决定性瞬间。",
            f"这张的亮度约 {brightness:.0f}、对比约 {contrast:.0f}、视觉结构代理分 {tension:.0f}、可修潜力 {editability:.0f}。",
        ]
        if tension >= 62:
            parts.append("本地结论只够把它送进深评队列；最终保留必须以选中照片深评看到的主体、动作和遮挡关系为准。")
        elif editability >= 68:
            parts.append("文件可修空间较好，但这不是故事价值判断；先点「深评选中照片」再决定留或淘汰。")
        else:
            parts.append("目前只是一张技术预筛候选；没有视觉深评前，不应把它当成作品候选。")
        return "".join(parts)

    def _display_direction(self, record: dict[str, Any]) -> str:
        raw = str(record.get("best_editing_direction", "") or "").strip()
        if self.language == "zh" and (not raw or raw in {"Run qwen_vision mode for concrete artistic editing guidance.", "Run vision LLM deep analysis for concrete artistic editing guidance."}):
            return "先点击“修图方案”生成中文参数建议；如果要判断主体关系、街拍瞬间和画面故事，再启用 LLM 深度分析。"
        return raw or ("Use the selected-photo editing plan for detailed parameters." if self.language != "zh" else "生成修图方案后查看具体参数。")

    def _localized_reasons(self, values: list[Any], *, positive: bool) -> list[str]:
        result: list[str] = []
        for item in values:
            text = str(item)
            if self.language == "zh":
                replacements = {
                    "Local proxy detected workable tonal/detail structure.": "本地指标显示画面仍有可用的明暗和细节结构。",
                    "Semantic story and human-documentary value require Qwen vision review.": "故事感、人物关系和人文价值需要 LLM 深度分析确认。",
                    "Semantic story and human-documentary value require a vision LLM or human review.": "故事感、人物关系和人文价值需要 LLM 深度分析或人工看图确认。",
                    "Local contrast and edge structure can support a stronger documentary edit.": "本地对比和边缘结构足以支撑更有力度的纪实处理。",
                    "Moderate tonal separation leaves room for a restrained humanistic edit.": "明暗分离中等，适合做克制的人文彩色或轻纪实处理。",
                    "Brightness is in a recoverable range with usable midtone information.": "亮度处在可恢复区间，中间调仍有可用信息。",
                    "Dense local structure suggests possible street-layer tension worth a vision pass.": "局部结构密度较高，可能有街头层次和现场张力，值得深评。",
                    "Tonal range suggests the file can tolerate meaningful Lightroom shaping.": "明暗范围允许较明确的 Lightroom 塑形。",
                    "Low contrast may need careful local separation before the frame reads clearly.": "对比较低，需要先做局部分离，否则主体关系可能不清楚。",
                    "The frame is dark; check whether shadow detail still carries story information.": "画面偏暗，要确认阴影里是否仍有故事信息。",
                    "The frame is bright; protect highlights before judging subtle subject detail.": "画面偏亮，先保护高光，再判断细节是否成立。",
                    "Highlight clipping is visible enough to constrain recovery.": "高光溢出会限制后期恢复。",
                    "Shadow clipping may hide important documentary cues.": "阴影死黑可能藏掉关键纪实线索。",
                    "Semantic story, human relationship, and decisive moment still require Qwen or human review.": "真实故事、人物关系和决定性瞬间仍需要 LLM 深度分析或人工看图确认。",
                    "Semantic story, human relationship, and decisive moment still require a vision LLM or human review.": "真实故事、人物关系和决定性瞬间仍需要 LLM 深度分析或人工看图确认。",
                    "Local proxy found enough recoverable structure for manual review.": "本地代理发现仍有可恢复结构，值得人工扫一眼。",
                    "pending vision review": "等待视觉深评",
                }
                text = replacements.get(text, text)
            result.append(text)
        if not result and self.language == "zh":
            result.append("本地指标显示仍有可修空间。" if positive else "暂无明显风险。")
        return result

    def _format_record_detail_html(self, record: dict[str, Any], selected_count: int) -> str:
        score = float(record.get("final_selection_score", 0) or 0)
        category = self._escape(self._display_category(record.get("category", "")))
        style = self._escape(self._display_style(record.get("recommended_style", "")))
        tone_category = self._escape(self._display_tone_category(record.get("tone_category", "")))
        user_label = self._escape(self._display_user_label(record.get("user_label", "") or "unlabeled"))
        filename = self._escape(str(record.get("filename", "")))
        story = self._escape(self._display_story(record))
        analysis_state_html = self._format_analysis_state_html(record)
        displayable_qwen_review = self._is_displayable_qwen_review(record)
        professional_review_html = self._format_professional_review_html(record) if displayable_qwen_review else ""
        direction = self._escape(self._display_direction(record)) if displayable_qwen_review else self._escape("深评通过后再给具体修图方向。" if self.language == "zh" else "Run a valid deep review for editing direction.")
        crop = self._escape(str(record.get("crop_strategy", "") or ("先不裁切；进入修图方案后再给具体比例。" if self.language == "zh" else "No crop instruction recorded."))) if displayable_qwen_review else self._escape("深评通过后再给裁切建议。" if self.language == "zh" else "Run a valid deep review for crop advice.")
        crop_box_html = self._format_crop_box_detail_html(record) if displayable_qwen_review else ""
        if displayable_qwen_review:
            risk_items = self._dedupe_display_strings(
                list(record.get("critical_flaws", []) or [])
                + list(record.get("negative_reasons", []) or [])
                + list(record.get("frame_failure_reasons", []) or [])
                + [
                    str(record.get("selection_risk") or ""),
                    str(record.get("edit_vs_select_warning") or ""),
                    str(record.get("subject_identity_uncertainty") or ""),
                ]
            )
            positive_items = list(record.get("positive_reasons", []) or [])
        else:
            risk_items = []
            positive_items = []
        positives = self._html_list(self._localized_reasons(positive_items[:4], positive=True), "本地指标显示仍有可修空间" if self.language == "zh" else "pending vision review")
        negatives = self._html_list(self._localized_reasons(risk_items[:6], positive=False), "未记录不可修复风险" if self.language == "zh" else "no non-fixable risks recorded")
        visible_evidence = self._html_list(record.get("visible_evidence", [])[:6], "") if displayable_qwen_review else ""
        subject_relationship = self._escape(str(record.get("subject_relationship", "") or "")) if displayable_qwen_review else ""
        decisive_moment = self._escape(str(record.get("decisive_moment_read", "") or "")) if displayable_qwen_review else ""
        why_this_frame = self._escape(str(record.get("why_this_frame", "") or "")) if displayable_qwen_review else ""
        avoid_overediting = self._escape(str(record.get("avoid_overediting", "") or "")) if displayable_qwen_review else ""
        params = record.get("specific_edit_parameters", {}) if displayable_qwen_review else {}
        params_rows = "".join(
            f"<tr><td>{self._escape(self._lightroom_detail_label(str(key)))}</td><td>{self._escape(str(value))}</td></tr>"
            for key, value in params.items()
        )
        if not params_rows:
            params_rows = f"<tr><td>{'参数' if self.language == 'zh' else 'Parameters'}</td><td>{'点击「修图方案」生成具体参数' if self.language == 'zh' else 'Generate an editing plan.'}</td></tr>"
        advanced_params = record.get("advanced_lightroom_parameters") if displayable_qwen_review else None
        advanced_labels = record.get("advanced_lightroom_parameter_labels")
        advanced_params_html = self._format_advanced_parameters_html(advanced_params, advanced_labels, include_basic=False) if isinstance(advanced_params, dict) else ""
        file_rows = self._format_file_metadata_rows(record)
        labels = {
            "selected": "已选" if self.language == "zh" else "Selected",
            "user_label": "标记" if self.language == "zh" else "Mark",
            "tone": "色调" if self.language == "zh" else "Tone",
            "group": "分组" if self.language == "zh" else "Group",
            "best": "组内最佳" if self.language == "zh" else "best",
            "basis": "依据" if self.language == "zh" else "basis",
            "time_group": "时间" if self.language == "zh" else "time",
            "visual_group": "视觉相似" if self.language == "zh" else "visual",
            "visual_time_group": "视觉+时间" if self.language == "zh" else "visual+time",
            "story": "故事" if self.language == "zh" else "Story",
            "human": "人文" if self.language == "zh" else "Human",
            "editability": "可修" if self.language == "zh" else "Edit",
            "story_read": "判断" if self.language == "zh" else "Read",
            "why": "亮点" if self.language == "zh" else "Signals",
            "risks": "风险" if self.language == "zh" else "Risks",
            "direction": "方向" if self.language == "zh" else "Direction",
            "crop": "裁切" if self.language == "zh" else "Crop",
            "params": "参数" if self.language == "zh" else "Parameters",
            "evidence": "可见证据" if self.language == "zh" else "Visible Evidence",
            "relationship": "关系" if self.language == "zh" else "Relationship",
            "moment": "瞬间" if self.language == "zh" else "Moment",
            "frame": "为什么是这张" if self.language == "zh" else "Why This Frame",
            "avoid": "别修掉" if self.language == "zh" else "Do Not Remove",
            "file_info": "文件信息" if self.language == "zh" else "File Info",
        }
        if str(record.get("analysis_source") or "") == "local_proxy":
            labels["story"] = "结构" if self.language == "zh" else "Structure"
            labels["human"] = "可修" if self.language == "zh" else "Recover"
            labels["editability"] = "风险" if self.language == "zh" else "Risk"
        group_size = int(record.get("group_size", 1) or 1)
        group_text = ""
        if group_size > 1:
            if record.get("is_group_best"):
                best_text = labels["best"]
            else:
                best_text = f"{labels['best']}: {self._escape(Path(str(record.get('group_best_path', ''))).name)}"
            basis_label = {
                "time": labels["time_group"],
                "visual": labels["visual_group"],
                "visual_time": labels["visual_time_group"],
            }.get(str(record.get("group_basis") or ""), str(record.get("group_basis") or ""))
            basis_text = f" {labels['basis']}: {self._escape(basis_label)}" if basis_label else ""
            time_span = record.get("group_time_span_seconds")
            if time_span not in (None, ""):
                try:
                    basis_text += f" {float(time_span):.0f}s"
                except (TypeError, ValueError):
                    pass
            group_text = f" | {labels['group']} {self._escape(str(record.get('group_rank', '-')))}/{group_size} {best_text}{basis_text}"
        if str(record.get("analysis_source") or "") == "local_proxy":
            metrics = record.get("local_metrics") if isinstance(record.get("local_metrics"), dict) else {}
            story_score = self._first_score(record, "visual_tension_score")
            human_score = self._first_score(record, "editability_score", "editing_potential_score")
            editability_score = max(0.0, min(100.0, self._number(metrics.get("highlight_clipping_ratio")) * 1200 + self._number(metrics.get("shadow_clipping_ratio")) * 1200))
        else:
            story_score = self._first_score(record, "street_documentary_potential_score", "storytelling_score")
            human_score = self._first_score(record, "human_documentary_value_score", "decisive_moment_score", "composition_score")
            editability_score = self._first_score(record, "editability_score", "editing_potential_score")
        return f"""
        <html><head>{self._detail_html_style()}</head><body>
        <div class="detail-shell">
          <div class="summary-card">
            <table class="head-table"><tr>
              <td><span class="rank">#{self._escape(str(record.get("rank", "-")))}</span><h2>{filename}</h2></td>
              <td class="score-cell">{score:.1f}</td>
            </tr></table>
            <p class="meta">{labels["selected"]} {selected_count} | {category} | {style}{f' | {labels["tone"]}: {tone_category}' if tone_category else ''} | {labels["user_label"]}: {user_label}{group_text}</p>
            <table class="metrics"><tr>
              <td><b>{story_score:.0f}</b><br><span>{labels["story"]}</span></td>
              <td><b>{human_score:.0f}</b><br><span>{labels["human"]}</span></td>
              <td><b>{editability_score:.0f}</b><br><span>{labels["editability"]}</span></td>
            </tr></table>
          </div>
          {analysis_state_html}
          {professional_review_html}
          <h3>{labels["story_read"]}</h3>
          <p>{story}</p>
          {f'<h3>{labels["file_info"]}</h3><table>{file_rows}</table>' if file_rows else ''}
          {f'<h3>{labels["evidence"]}</h3>{visible_evidence}' if visible_evidence else ''}
          {f'<h3>{labels["relationship"]}</h3><p>{subject_relationship}</p>' if subject_relationship else ''}
          {f'<h3>{labels["moment"]}</h3><p>{decisive_moment}</p>' if decisive_moment else ''}
          {f'<h3>{labels["frame"]}</h3><p>{why_this_frame}</p>' if why_this_frame else ''}
          <h3>{labels["risks"]}</h3>
          {negatives}
          <h3>{labels["why"]}</h3>
          {positives}
          <h3>{labels["direction"]}</h3>
          <p>{direction}</p>
          <h3>{labels["crop"]}</h3>
          <p>{crop}</p>
          {crop_box_html}
          <h3>{labels["params"]}</h3>
          <table>{params_rows}</table>
          {advanced_params_html}
          {f'<h3>{labels["avoid"]}</h3><p>{avoid_overediting}</p>' if avoid_overediting else ''}
        </div>
        </body></html>
        """

    def _format_analysis_state_html(self, record: dict[str, Any]) -> str:
        source = str(record.get("analysis_source") or "")
        qwen_status = str(record.get("qwen_status") or "").lower()
        quality = str(record.get("analysis_quality") or "")
        if qwen_status == "failed":
            title = "深评失败：当前不是专业摄影判断" if self.language == "zh" else "Deep review failed"
            body = (
                f"{self._qwen_failure_message(record)} 下面只显示本地技术草稿；不要据此判断人物关系、决定性瞬间或作品价值。"
                if self.language == "zh"
                else f"{self._qwen_failure_message(record)} The detail below is only a local technical draft."
            )
            return f'<div class="analysis-state failed"><b>{self._escape(title)}</b><p>{self._escape(body)}</p></div>'
        if source != "qwen_vision":
            title = "仅本地预筛：请先深评选中照片" if self.language == "zh" else "Local pre-screen only"
            body = (
                "这里的分数来自明暗、对比、边缘密度和可修空间，不能替代对人物、手势、情绪、遮挡和构图关系的阅读。"
                if self.language == "zh"
                else "Scores here come from tonal and structure proxies, not a semantic photo read."
            )
            return f'<div class="analysis-state local"><b>{self._escape(title)}</b><p>{self._escape(body)}</p></div>'
        prompt_version = str(record.get("qwen_prompt_version") or "")
        if prompt_version != QWEN_STORY_PROMPT_VERSION:
            title = "旧版深评：建议重跑选中照片深评" if self.language == "zh" else "Stale deep review"
            body = (
                f"这条结果来自 {prompt_version or '未知旧版'}，当前专业校验已升级到 {QWEN_STORY_PROMPT_VERSION}；旧报告可能偏指标化或不够有结论。"
                if self.language == "zh"
                else f"This result came from {prompt_version or 'an unknown old prompt'}; the current review prompt is {QWEN_STORY_PROMPT_VERSION}."
            )
            return f'<div class="analysis-state weak"><b>{self._escape(title)}</b><p>{self._escape(body)}</p></div>'
        if quality != "concrete":
            title = "深评返回不合格：请重跑选中照片深评" if self.language == "zh" else "Weak deep review"
            body = (
                "模型返回了部分信息，但没有形成可用的照片内容阅读；这条结果已降级，不应作为保留/淘汰依据。"
                if self.language == "zh"
                else "The model returned partial visual information, but the evidence chain is incomplete."
            )
            return f'<div class="analysis-state weak"><b>{self._escape(title)}</b><p>{self._escape(body)}</p></div>'
        return ""

    def _is_displayable_qwen_review(self, record: dict[str, Any]) -> bool:
        return is_current_concrete_qwen_review(record)

    def _qwen_failure_message(self, record: dict[str, Any]) -> str:
        errors = record.get("errors")
        if isinstance(errors, list):
            for item in reversed(errors):
                text = str(item)
                if "qwen_vision_failed:" in text:
                    return self._humanize_llm_failure_message(text.split("qwen_vision_failed:", 1)[1].strip())
                if text.strip():
                    return self._humanize_llm_failure_message(text.strip())
        return "LLM 深评没有成功返回可用结果。" if self.language == "zh" else "LLM Deep Analysis did not return a usable result."

    def _format_professional_review_html(self, record: dict[str, Any]) -> str:
        if str(record.get("qwen_status") or "").lower() == "failed":
            return ""
        review = record.get("professional_review")
        if not isinstance(review, dict):
            return ""
        field_order = [
            ("editorial_summary", "编辑总评" if self.language == "zh" else "Editorial Read"),
            ("story_read", "故事与人文价值" if self.language == "zh" else "Story Value"),
            ("composition_read", "构图判断" if self.language == "zh" else "Composition"),
            ("selection_logic", "选片逻辑" if self.language == "zh" else "Selection Logic"),
            ("editing_logic", "后期逻辑" if self.language == "zh" else "Editing Logic"),
            ("final_recommendation", "最终建议" if self.language == "zh" else "Recommendation"),
        ]
        rows = []
        for key, label in field_order:
            value = str(review.get(key) or "").strip()
            if value:
                rows.append(f"<h4>{self._escape(label)}</h4><p>{self._escape(value)}</p>")
        if not rows:
            return ""
        title = "专业深评" if self.language == "zh" else "Professional Review"
        return f'<div class="professional-review"><h3>{self._escape(title)}</h3>{"".join(rows)}</div>'

    def _format_crop_box_detail_html(self, record: dict[str, Any]) -> str:
        crop_box = _record_crop_box(record)
        if not crop_box:
            return ""
        reason = self._escape(_record_crop_reason(record))
        left = crop_box["x"] * 100
        top = crop_box["y"] * 100
        right = (crop_box["x"] + crop_box["width"]) * 100
        bottom = (crop_box["y"] + crop_box["height"]) * 100
        if self.language == "zh":
            label = "预览裁切框"
            position = f"左 {left:.0f}% / 上 {top:.0f}% / 右 {right:.0f}% / 下 {bottom:.0f}%"
            note = "双击照片打开大图预览可直接看到裁切框。"
        else:
            label = "Preview crop box"
            position = f"left {left:.0f}% / top {top:.0f}% / right {right:.0f}% / bottom {bottom:.0f}%"
            note = "Double-click the photo to see the crop overlay in the large preview."
        reason_html = f"<br>{reason}" if reason else ""
        return f'<p class="crop-note"><b>{label}:</b> {self._escape(position)}{reason_html}<br><span>{self._escape(note)}</span></p>'

    def _format_file_metadata_rows(self, record: dict[str, Any]) -> str:
        rows: list[tuple[str, Any]] = []
        if record.get("pair_status"):
            pair_label = {
                "raw_jpeg_pair": "RAW+JPG",
                "raw_only": "RAW only",
                "jpeg_only": "JPG only",
                "single": "single",
            }.get(str(record.get("pair_status")), str(record.get("pair_status")))
            rows.append(("配对" if self.language == "zh" else "Pair", pair_label))
        if record.get("paired_raw_path"):
            rows.append(("RAW", Path(str(record.get("paired_raw_path"))).name))
        if record.get("paired_jpeg_path"):
            rows.append(("JPG", Path(str(record.get("paired_jpeg_path"))).name))
        exif = record.get("exif") if isinstance(record.get("exif"), dict) else {}
        exif_labels = {
            "camera_make": "品牌" if self.language == "zh" else "Make",
            "camera_model": "机身" if self.language == "zh" else "Camera",
            "lens": "镜头" if self.language == "zh" else "Lens",
            "shutter_speed": "快门" if self.language == "zh" else "Shutter",
            "aperture": "光圈" if self.language == "zh" else "Aperture",
            "iso": "ISO",
            "focal_length": "焦距" if self.language == "zh" else "Focal",
            "date_time_original": "时间" if self.language == "zh" else "Time",
            "date_time": "时间" if self.language == "zh" else "Time",
            "raw_preview_source": "RAW预览" if self.language == "zh" else "RAW Preview",
        }
        seen: set[str] = set()
        for key in ("camera_make", "camera_model", "lens", "shutter_speed", "aperture", "iso", "focal_length", "date_time_original", "date_time", "raw_preview_source"):
            if key in seen or not exif.get(key):
                continue
            rows.append((exif_labels.get(key, key), exif.get(key)))
            seen.add(key)
        return "".join(f"<tr><td>{self._escape(str(label))}</td><td>{self._escape(str(value))}</td></tr>" for label, value in rows)

    def _generate_selected_advice(self) -> None:
        if not self.records:
            QMessageBox.information(self, self._t("no_records"), self._t("run_first"))
            return

        records_for_advice = self.records
        selected_indexes = self._selected_record_indexes()
        if selected_indexes:
            selected_ranks = []
            for index in selected_indexes:
                record = index.data(Qt.ItemDataRole.UserRole)
                if isinstance(record, dict):
                    rank = self._rank_for_advice(record)
                    if rank is not None:
                        selected_ranks.append(rank)
        else:
            records_for_advice = self._filtered_records()
            if not records_for_advice:
                QMessageBox.information(self, self._t("no_records"), self._t("empty_filtered"))
                return
            selected_ranks = self._default_advice_ranks(records_for_advice)

        if not selected_ranks:
            QMessageBox.information(self, self._t("no_selection"), self._t("select_first"))
            return
        payload = build_selected_editing_advice(records_for_advice, selected_ranks=selected_ranks, language=self.language)
        self._merge_advice_payload_to_records(payload)
        json_path = self.output_dir / "selected_editing_advice.json"
        md_path = self.output_dir / "selected_editing_advice.md"
        write_json_report(json_path, payload)
        write_markdown_report(md_path, render_selected_editing_advice_markdown(payload))
        self.detail_text.setHtml(self._format_advice_html(payload))
        self.status_label.setText(str(md_path))
        self._update_workflow("edit")
        self._sync_crop_preview_button()
        self._fade_in(self.detail_text)

    def _merge_advice_payload_to_records(self, payload: dict[str, Any]) -> None:
        items = payload.get("selected_editing_advice", [])
        if not isinstance(items, list):
            return
        by_rank = {self._rank_for_advice(record): record for record in self.records if self._rank_for_advice(record) is not None}
        for item in items:
            if not isinstance(item, dict):
                continue
            rank = self._rank_for_advice(item)
            record = by_rank.get(rank)
            if record is None:
                continue
            crop_plan = item.get("crop_plan")
            if isinstance(crop_plan, dict):
                record["crop_plan"] = crop_plan
                editing_plan = record.get("editing_plan")
                if not isinstance(editing_plan, dict):
                    editing_plan = {}
                    record["editing_plan"] = editing_plan
                editing_plan["crop_plan"] = crop_plan
            if item.get("specific_lightroom_parameters"):
                record["specific_edit_parameters"] = item.get("specific_lightroom_parameters")

    def _mark_selected(self, label: str) -> None:
        selected_indexes = self._selected_record_indexes()
        if not selected_indexes:
            QMessageBox.information(self, self._t("no_selection"), self._t("select_first"))
            return
        label_value = normalized_user_label(label) or None
        changed = 0
        changed_rows: list[int] = []
        changed_keys: set[str] = set()
        for index in selected_indexes:
            display_record = index.data(Qt.ItemDataRole.UserRole)
            if not isinstance(display_record, dict) or not display_record.get("path"):
                continue
            record = self._canonical_record(display_record)
            record["user_label"] = label_value or ""
            display_record["user_label"] = label_value or ""
            apply_user_feedback_fields(record)
            apply_user_feedback_fields(display_record)
            changed_keys.add(self._record_key(record))
            self.state_db.set_user_label(
                path=record["path"],
                label=label_value,
                run_id=self.current_run_id or None,
                rank=int(record.get("rank", 0) or 0),
                score=float(record.get("final_selection_score", 0) or 0),
                category=str(record.get("category", "")),
            )
            changed += 1
            changed_rows.append(index.row())
        self._write_current_reports()
        active_label_filter = self.label_filter.currentData() if hasattr(self, "label_filter") else "all"
        if active_label_filter and active_label_filter != "all":
            self._populate_records()
            self._restore_selection_by_keys(changed_keys)
        elif self.photo_model is not None:
            for row in changed_rows:
                self.photo_model.refresh_row(row)
        self._show_selected_detail()
        self._update_dashboard()
        self.status_label.setText(f"{changed} -> {self._t(label_value) if label_value else self._t('unmark')}")

    def _mark_keyboard_selection(self, label: str) -> None:
        if self.photo_model is not None and not self._selected_record_indexes() and self.photo_model.records:
            index = self.photo_list.currentIndex()
            if not index.isValid() or not index.data(Qt.ItemDataRole.UserRole):
                index = self.photo_model.index(0, 0)
            self.photo_list.selectionModel().select(
                index,
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
            )
            self.photo_list.setCurrentIndex(index)
        self._mark_selected(label)

    def _toggle_keyboard_mark(self) -> None:
        selected = self._selected_record_indexes()
        if not selected:
            self._mark_keyboard_selection("keep")
            return
        record = selected[0].data(Qt.ItemDataRole.UserRole)
        current_label = normalized_user_label(record.get("user_label", "")) if isinstance(record, dict) else ""
        self._mark_keyboard_selection("" if current_label else "keep")

    def _select_all_visible_records(self) -> None:
        if self.photo_model is None or self.photo_list.selectionModel() is None or not self.photo_model.records:
            return
        selection_model = self.photo_list.selectionModel()
        selection_model.clearSelection()
        for row in range(self.photo_model.rowCount()):
            selection_model.select(
                self.photo_model.index(row, 0),
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
            )
        first = self.photo_model.index(0, 0)
        if first.isValid():
            selection_model.setCurrentIndex(first, QItemSelectionModel.SelectionFlag.NoUpdate)
        self._show_selected_detail()

    def _invert_visible_selection(self) -> None:
        if self.photo_model is None or self.photo_list.selectionModel() is None or not self.photo_model.records:
            return
        selection_model = self.photo_list.selectionModel()
        first_selected: QModelIndex | None = None
        for row in range(self.photo_model.rowCount()):
            index = self.photo_model.index(row, 0)
            command = QItemSelectionModel.SelectionFlag.Deselect if selection_model.isSelected(index) else QItemSelectionModel.SelectionFlag.Select
            selection_model.select(index, command | QItemSelectionModel.SelectionFlag.Rows)
            if command == QItemSelectionModel.SelectionFlag.Select and first_selected is None:
                first_selected = index
        if first_selected is not None:
            selection_model.setCurrentIndex(first_selected, QItemSelectionModel.SelectionFlag.NoUpdate)
        self._show_selected_detail()

    def _shortcut_event_code(self, event: Any) -> int:
        modifier_mask = (
            Qt.KeyboardModifier.ControlModifier.value
            | Qt.KeyboardModifier.ShiftModifier.value
            | Qt.KeyboardModifier.AltModifier.value
        )
        return int(event.key()) | (event.modifiers().value & modifier_mask)

    def _shortcut_action_for_code(self, code: int) -> str | None:
        for action in SHORTCUT_ACTIONS:
            if int(self.shortcut_keys.get(action, DEFAULT_SHORTCUT_KEYS[action])) == int(code):
                return action
        return None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if event.type() == QEvent.Type.KeyPress and isinstance(watched, QWidget) and (watched is self or self.isAncestorOf(watched)) and self._handle_shortcut_event(event):
            return True
        return super().eventFilter(watched, event)

    def _handle_shortcut_event(self, event: Any) -> bool:
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QTextEdit, QComboBox, QSpinBox, QCheckBox)):
            return False
        action = self._shortcut_action_for_code(self._shortcut_event_code(event))
        if action == "keep":
            self._mark_keyboard_selection("keep")
            event.accept()
            return True
        if action == "reject":
            self._mark_keyboard_selection("reject")
            event.accept()
            return True
        if action == "toggle_mark":
            self._toggle_keyboard_mark()
            event.accept()
            return True
        if action == "maybe":
            self._mark_keyboard_selection("maybe")
            event.accept()
            return True
        if action == "select_all":
            self._select_all_visible_records()
            event.accept()
            return True
        if action == "invert_selection":
            self._invert_visible_selection()
            event.accept()
            return True
        return False

    def keyPressEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        if self._handle_shortcut_event(event):
            return
        super().keyPressEvent(event)

    def _cancel_analysis(self, *, close_after_stop: bool = False) -> None:
        if close_after_stop:
            self.pending_close = True
        else:
            self.pending_close = False
            self.allow_close = False
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "STOP_LUMASIFT").write_text("stop", encoding="utf-8")
        if self.qwen_queue_state.get("enabled"):
            self.qwen_queue_state["cancelling"] = True
            self._render_qwen_queue_state()
        self.status_label.setText(self._t("closing") if self.pending_close else self._t("cancel"))
        self.cancel_button.setEnabled(False)
        self.main_cancel_button.setEnabled(False)

    def _toggle_key_visibility(self, enabled: bool) -> None:
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal if enabled else QLineEdit.EchoMode.Password)

    def _api_key_text_edited(self, text: str) -> None:
        if text.strip():
            self._set_qwen_mode()
            self.status_label.setText(self._t("qwen_key_promoted"))
        self._render_qwen_queue_state()

    def _set_qwen_mode(self) -> None:
        mode_index = self.mode_combo.findData("qwen_vision")
        if mode_index >= 0 and self.mode_combo.currentIndex() != mode_index:
            self.mode_combo.setCurrentIndex(mode_index)
        else:
            self._sync_mode_controls()

    def _has_configured_qwen_keys(self) -> bool:
        if hasattr(self, "api_key_edit") and self.api_key_edit.text().strip():
            return True
        try:
            return bool(Settings.from_env().vision_api_keys)
        except Exception:  # noqa: BLE001 - this is only a UI hint.
            return False

    def _set_attention(self, widget: QWidget | None, enabled: bool) -> None:
        if widget is None:
            return
        widget.setProperty("attention", "true" if enabled else "false")
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

    def _refresh_setup_attention(self) -> None:
        if not hasattr(self, "input_edit"):
            return
        input_missing = not self.input_edit.text().strip() or not Path(self.input_edit.text().strip()).exists()
        qwen_enabled = hasattr(self, "mode_combo") and (self.mode_combo.currentData() or self.mode_combo.currentText()) == "qwen_vision"
        llm_missing_key = qwen_enabled and not self._has_configured_qwen_keys()
        self._set_attention(self.input_edit, input_missing)
        self._set_attention(self.output_edit, False)
        self._set_attention(self.api_key_edit if hasattr(self, "api_key_edit") else None, llm_missing_key)
        if hasattr(self, "cache_note"):
            hints: list[str] = []
            if input_missing:
                hints.append(self._t("input_missing_hint"))
            if llm_missing_key:
                hints.append(self._t("llm_setup_missing_hint"))
            if hints:
                self.cache_note.setText(" ".join(hints))
                self._set_attention(self.cache_note, True)
            else:
                self.cache_note.setText(self._t("cache_note") if qwen_enabled else self._t("local_mode_hint"))
                self._set_attention(self.cache_note, False)

    def _sync_mode_controls(self) -> None:
        qwen_enabled = (self.mode_combo.currentData() or self.mode_combo.currentText()) == "qwen_vision"
        self.top_n_spin.setEnabled(qwen_enabled)
        self.api_key_edit.setEnabled(True)
        if hasattr(self, "vision_base_url_edit"):
            self.vision_base_url_edit.setEnabled(qwen_enabled)
        if hasattr(self, "vision_model_edit"):
            self.vision_model_edit.setEnabled(qwen_enabled)
        self.show_key_checkbox.setEnabled(True)
        self.save_keys_checkbox.setEnabled(True)
        self._refresh_setup_attention()
        self._update_workflow("qwen" if qwen_enabled else "import")
        self._render_qwen_queue_state()

    def _load_shortcuts(self) -> None:
        try:
            version = int(self.settings_store.value("shortcuts_version", 0))
        except (TypeError, ValueError):
            version = 0
        if version < 2:
            self.shortcut_keys = dict(DEFAULT_SHORTCUT_KEYS)
            self._save_shortcuts()
            return
        loaded: dict[str, int] = {}
        used: set[int] = set()
        for action in SHORTCUT_ACTIONS:
            default = DEFAULT_SHORTCUT_KEYS[action]
            try:
                key_code = int(self.settings_store.value(f"shortcut_{action}", default))
            except (TypeError, ValueError):
                key_code = default
            allowed = {code for _label, code in SHORTCUT_KEY_CHOICES}
            if key_code not in allowed or key_code in used:
                key_code = default
            if key_code in used:
                key_code = next(code for _label, code in SHORTCUT_KEY_CHOICES if code not in used)
            loaded[action] = key_code
            used.add(key_code)
        self.shortcut_keys = loaded
        self._sync_shortcut_combos()

    def _save_shortcuts(self) -> None:
        self.settings_store.setValue("shortcuts_version", 3)
        for action, key_code in self.shortcut_keys.items():
            self.settings_store.setValue(f"shortcut_{action}", int(key_code))
        self._sync_shortcut_combos()

    def _sync_shortcut_combos(self) -> None:
        for action, combo in getattr(self, "shortcut_combos", {}).items():
            combo.blockSignals(True)
            index = combo.findData(int(self.shortcut_keys.get(action, DEFAULT_SHORTCUT_KEYS[action])))
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)

    def _shortcut_combo_changed(self, action: str) -> None:
        combo = self.shortcut_combos.get(action)
        if combo is None:
            return
        new_key = int(combo.currentData())
        old_key = int(self.shortcut_keys.get(action, DEFAULT_SHORTCUT_KEYS[action]))
        for other_action, other_key in list(self.shortcut_keys.items()):
            if other_action != action and int(other_key) == new_key:
                self.shortcut_keys[other_action] = old_key
        self.shortcut_keys[action] = new_key
        self._save_shortcuts()
        self.status_label.setText(self._t("shortcuts_saved"))

    def _reset_shortcuts_to_defaults(self) -> None:
        self.shortcut_keys = dict(DEFAULT_SHORTCUT_KEYS)
        self._save_shortcuts()
        self.status_label.setText(self._t("shortcuts_reset_done"))

    def _load_preferences(self) -> None:
        stored_theme = str(self.settings_store.value("theme", self.theme))
        self.theme = stored_theme if stored_theme in THEME_VALUES else "dark"
        if hasattr(self, "theme_combo"):
            self.theme_combo.blockSignals(True)
            theme_index = self.theme_combo.findData(self.theme)
            self.theme_combo.setCurrentIndex(theme_index if theme_index >= 0 else 0)
            self.theme_combo.blockSignals(False)
        self.input_edit.setText(str(self.settings_store.value("input_dir", "D:/DCIM")))
        self.output_edit.setText(str(self.settings_store.value("output_dir", "./outputs/gui")))
        self.output_dir = Path(self.output_edit.text())
        self.limit_spin.setValue(int(self.settings_store.value("limit", 50)))
        self.top_n_spin.setValue(int(self.settings_store.value("top_n", 5)))
        self.selected_top_spin.setValue(int(self.settings_store.value("selected_top", 10)))
        self.display_limit_spin.setValue(int(self.settings_store.value("display_limit", 300)))
        stored_vision_model = _clean_vision_model_override(self.settings_store.value("vision_model", self.detected_vision_model or "qwen3.6-plus"))
        self.detected_vision_model = stored_vision_model or "qwen3.6-plus"
        if hasattr(self, "vision_base_url_edit"):
            stored_base_url = self.settings_store.value("vision_base_url", "")
            self.vision_base_url_edit.setText(_vision_base_url_override(stored_base_url))
        if hasattr(self, "vision_model_edit"):
            self.vision_model_edit.setText("" if stored_vision_model == "qwen3.6-plus" else stored_vision_model)
        mode = str(self.settings_store.value("mode", "local_only"))
        mode_index = self.mode_combo.findData(mode if mode in {"local_only", "qwen_vision"} else "local_only")
        self.mode_combo.setCurrentIndex(mode_index if mode_index >= 0 else 0)
        saved_keys = str(self.settings_store.value("api_keys", ""))
        self.api_key_edit.setText(saved_keys)
        self.save_keys_checkbox.setChecked(bool(saved_keys))
        self._load_shortcuts()
        self._sync_mode_controls()

    def _save_preferences(self) -> None:
        self.settings_store.setValue("input_dir", self.input_edit.text())
        self.settings_store.setValue("output_dir", self.output_edit.text())
        self.settings_store.setValue("limit", self.limit_spin.value())
        self.settings_store.setValue("top_n", self.top_n_spin.value())
        self.settings_store.setValue("selected_top", self.selected_top_spin.value())
        self.settings_store.setValue("display_limit", self.display_limit_spin.value())
        self.settings_store.setValue("mode", self.mode_combo.currentData() or "local_only")
        self.settings_store.setValue("theme", self.theme)
        if hasattr(self, "vision_base_url_edit"):
            self.settings_store.setValue("vision_base_url", _clean_vision_base_url(self.vision_base_url_edit.text()))
        model_override = _clean_vision_model_override(self.vision_model_edit.text()) if hasattr(self, "vision_model_edit") else ""
        if model_override:
            self.detected_vision_model = model_override
        self.settings_store.setValue("vision_model", self.detected_vision_model or "qwen3.6-plus")
        if self.save_keys_checkbox.isChecked():
            self.settings_store.setValue("api_keys", self.api_key_edit.text())
        else:
            self.settings_store.remove("api_keys")
        self._save_shortcuts()

    def _merge_user_labels(self) -> None:
        labels = self.state_db.load_labels(str(record.get("path", "")) for record in self.records if record.get("path"))
        for record in self.records:
            path = str(record.get("path", ""))
            normalized = str(Path(path).expanduser().resolve()) if path else ""
            if normalized in labels:
                record["user_label"] = labels[normalized]
            apply_user_feedback_fields(record)

    def _write_current_reports(self) -> None:
        if not self.records:
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        write_csv_report(self.output_dir / "report.csv", self.records)
        write_json_report(
            self.output_dir / "report.json",
            {
                "run_id": self.current_run_id,
                "ai_mode": str(self.mode_combo.currentData() or "local_only") if hasattr(self, "mode_combo") else "",
                "input_dir": self.input_edit.text() if hasattr(self, "input_edit") else "",
                "records": self.records,
                "user_label_source": str(self.state_db.path),
            },
        )
        write_json_report(self.output_dir / "user_labels.json", {"records": self.state_db.export_labeled_records()})

    def _selected_record_indexes(self) -> list[QModelIndex]:
        if not hasattr(self, "photo_list") or self.photo_list.selectionModel() is None:
            return []
        indexes = self.photo_list.selectionModel().selectedIndexes()
        return [index for index in indexes if index.isValid() and index.data(Qt.ItemDataRole.UserRole)]

    def _rank_for_advice(self, record: dict[str, Any]) -> int | None:
        try:
            rank = int(record.get("rank", 0) or 0)
        except (TypeError, ValueError):
            return None
        return rank if rank > 0 else None

    def _has_qwen_review(self, record: dict[str, Any]) -> bool:
        return self._qwen_review_bucket(record) == "concrete"

    def _default_advice_ranks(self, pool: list[dict[str, Any]] | None = None) -> list[int]:
        candidates = list(pool if pool is not None else self._filtered_records())
        if not candidates:
            candidates = list(self.records)
        limit = max(1, min(self.selected_top_spin.value(), len(candidates))) if candidates else 0
        if limit <= 0:
            return []

        reviewed = [record for record in candidates if self._has_qwen_review(record)]
        if reviewed:
            concrete = [record for record in reviewed if self._qwen_review_bucket(record) == "concrete"]
            partial = [record for record in reviewed if self._qwen_review_bucket(record) != "concrete"]
            ranked = [self._rank_for_advice(record) for record in (concrete + partial)[:limit]]
        else:
            ranked = [self._rank_for_advice(record) for record in candidates[:limit]]
        return [rank for rank in ranked if rank is not None]

    def _open_path(self, path: Path) -> None:
        try:
            if not path.exists():
                QMessageBox.information(self, self._t("no_results"), str(path))
                return
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, self._t("failed"), str(exc))

    def _apply_shadow(self, widget: QWidget, *, blur: int, y: int, alpha: int) -> None:
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(blur)
        shadow.setOffset(0, y)
        shadow.setColor(QColor(15, 23, 42, alpha))
        widget.setGraphicsEffect(shadow)

    def _fade_in(self, widget: QWidget, *, duration: int = 260) -> None:
        if isinstance(widget, QTextEdit):
            widget.setGraphicsEffect(None)
            return
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(duration)
        animation.setStartValue(0.35)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda: self._animations.remove(animation) if animation in self._animations else None)
        self._animations.append(animation)
        animation.start()

    def _update_workflow(self, active: str) -> None:
        order = ["import", "local", "qwen", "edit"]
        active_index = order.index(active) if active in order else 0
        for index, key in enumerate(order):
            step = self.workflow_steps.get(key)
            if step is None:
                continue
            if index < active_index:
                state = "done"
            elif index == active_index:
                state = "active"
            else:
                state = "idle"
            step.setProperty("state", state)
            step.style().unpolish(step)
            step.style().polish(step)
            state_label = self.workflow_state_labels.get(key)
            if state_label is not None:
                state_label.setText(self._t(f"workflow_{state}"))

    def _update_dashboard(self, summary: dict[str, Any] | None = None) -> None:
        scanned = summary.get("scanned", len(self.records)) if summary else len(self.records)
        selected = self._selected_record_indexes() if hasattr(self, "photo_list") else []
        mode = self._t("qwen") if hasattr(self, "mode_combo") and (self.mode_combo.currentData() or self.mode_combo.currentText()) == "qwen_vision" else self._t("local")
        if hasattr(self, "result_count_label") and self.records:
            self.result_count_label.setToolTip(f"{self._t('scanned')}: {scanned}  {self._t('shown')}: {len(self.visible_records)}  {self._t('selected')}: {len(selected)}  {self._t('mode')}: {mode}")

    def _empty_detail_html(self) -> str:
        return """
        <html><head>{style}</head><body>
        <div class="empty-state">
          <h2>{title}</h2>
          <p>{body}</p>
          <table>
            <tr><td>1</td><td>{step1}</td></tr>
            <tr><td>2</td><td>{step2}</td></tr>
            <tr><td>3</td><td>{step3}</td></tr>
          </table>
        </div>
        </body></html>
        """.format(
            style=self._detail_html_style(),
            title="从本地目录开始" if self.language == "zh" else "Start with a local folder",
            body="选目录、跑分析、再多选生成修图方案。" if self.language == "zh" else "Choose a folder, run analysis, then multi-select photos for editing plans.",
            step1="选择照片目录" if self.language == "zh" else "Choose a photo folder",
            step2="本地快速初筛" if self.language == "zh" else "Run local pre-score",
            step3="高价值候选再交给 LLM 深度分析" if self.language == "zh" else "Use LLM Deep Analysis for high-value candidates",
        )

    def _help_page_html(self) -> str:
        if self.language == "zh":
            return f"""
            <html><head>{self._detail_html_style()}</head><body>
            <div class="detail-shell">
              <div class="summary-card">
                <div class="manual-title">LumaSift 使用说明</div>
                <p class="manual-subtitle">面向街头、纪实、人文和旅行摄影的本地优先选片与修图潜力评估流程。</p>
                <table class="flow">
                  <tr>
                    <td>1 导入照片目录</td><td class="arrow">-&gt;</td>
                    <td>2 本地初筛</td><td class="arrow">-&gt;</td>
                    <td>3 LLM深度分析 Top-N</td><td class="arrow">-&gt;</td>
                    <td>4 人工标记与筛选</td><td class="arrow">-&gt;</td>
                    <td>5 生成修图方案</td>
                  </tr>
                </table>
                <p><span class="warn">核心原则：</span>本地模型先做便宜、快速、隐私友好的技术与结构预筛；真正涉及人物关系、决定性瞬间、故事价值和可编辑方向的判断，优先看 LLM深度分析或人工看图。</p>
              </div>

              <div class="advice-card">
                <h2>首次使用：从一组照片跑到可交付结果</h2>
                <table>
                  <tr><td><b>1. 进入设置</b></td><td>点击顶部 <span class="kbd">设置</span>，选择照片目录和输出目录。照片目录可以是 JPG、PNG、常见 RAW 文件混合目录；RAW 原片不会上传。</td></tr>
                  <tr><td><b>2. 选择模式</b></td><td><span class="kbd">本地</span> 只做本机初筛；<span class="kbd">LLM深度分析</span> 会先本地筛，再把 Top-N 压缩预览交给支持图像的 LLM。要判断故事、人文和瞬间，建议使用深度分析模式。</td></tr>
                  <tr><td><b>3. 设置数量</b></td><td><span class="kbd">扫描</span> 控制最多处理多少张；<span class="kbd">深评 Top-N</span> 控制深评候选数量；<span class="kbd">修图 Top-N</span> 控制没手动选图时默认生成多少张修图方案。</td></tr>
                  <tr><td><b>4. 填 key 并检查</b></td><td>填入 OpenAI-compatible / NewCoin API key 后点 <span class="kbd">检查</span>。界面会检测是否存在合适的图像 LLM，显示选中的模型和剩余 token/额度。密钥只应保存在本机设置或环境变量，不要写入项目文件。</td></tr>
                  <tr><td><b>5. 开始分析</b></td><td>回到 <span class="kbd">工作流</span>，点 <span class="kbd">开始分析</span>。分析中可以点 <span class="kbd">取消</span> 请求停止，已完成结果会保留。</td></tr>
                </table>
              </div>

              <div class="advice-card">
                <h2>界面区域怎么读</h2>
                <table class="mini-grid">
                  <tr><td><b>顶部导航</b><br>工作流、设置、快捷键、帮助。筛片模式下顶部仍可见，便于返回设置或调整快捷键。</td><td><b>流程条</b><br>导入、初筛、深评、修图四步。点击步骤可快速展开对应配置或回到主评审视图。</td></tr>
                  <tr><td><b>选片板</b><br>左侧照片网格显示排名、分数、人工标记、时间/相似分组信息。双击照片可打开大图预览。</td><td><b>评审面板</b><br>右侧显示故事判断、可见证据、人物关系、瞬间判断、风险、裁切和修图参数。</td></tr>
                  <tr><td><b>LLM深度分析状态条</b><br>显示排队、运行、完成、缓存、失败、重试和取消数量。鼠标悬停可看失败原因。</td><td><b>输出入口</b><br>底部图标按钮可打开输出目录、联系表和生成修图方案。</td></tr>
                </table>
              </div>

              <div class="advice-card">
                <h2>筛选和人工标记</h2>
                <ul>
                  <li><b>搜索框：</b>按文件名、路径、分类、风格和标记搜索。</li>
                  <li><b>分类筛选：</b>查看作品候选、强修图候选、故事候选、技术弱但有趣、普通记录、淘汰候选等。</li>
                  <li><b>标记筛选：</b>查看保留、待定、淘汰、未标记。使用右侧三个图标按钮给选中的多张照片批量标记。</li>
                  <li><b>分组筛选：</b>只看组最佳、成组照片、时间组、相似组或单张。组内最佳只是系统建议，仍应结合人的内容判断。</li>
                  <li><b>深评状态筛选：</b>查看已深评、完整证据、未深评、失败/重试、已跳过。做最终修图方案前，建议先切到 <span class="kbd">已深评</span> 或 <span class="kbd">完整证据</span>。</li>
                  <li><b>排序：</b>高分优先、标记优先、低分优先、排名、文件名。人工标记会影响“标记优先”排序。</li>
                </ul>
              </div>

              <div class="advice-card">
                <h2>LLM深度分析怎么工作</h2>
                <table>
                  <tr><td><b>上传内容</b></td><td>只上传 Top-N 候选的压缩 JPEG 预览，不上传 RAW 原片。预览用于视觉理解和修图建议。</td></tr>
                  <tr><td><b>缓存</b></td><td>同一张预览和同一提示版本命中缓存时不会重复扣费；状态条会显示缓存数量。</td></tr>
                  <tr><td><b>失败与重试</b></td><td>网络、中转站或模型返回截断时会重试。最终失败会保留本地初筛结果，并在深评状态中显示失败。</td></tr>
                  <tr><td><b>未深评</b></td><td>Top-N 之外、被人工淘汰、或分组非最佳的照片可能标记为未深评/跳过。这类照片的修图建议会更保守，不会伪装成完整视觉判断。</td></tr>
                  <tr><td><b>判断可信度</b></td><td>“完整证据”表示模型返回了较具体的可见证据、人物关系、瞬间和修图计划；“已深评”表示有视觉结果但证据可能较弱。</td></tr>
                </table>
              </div>

              <div class="advice-card">
                <h2>生成修图方案</h2>
                <ul>
                  <li>手动多选照片后点右下角修图方案按钮，会严格按你选中的照片生成。</li>
                  <li>如果没有手动选择，系统会在当前筛选范围内优先选择已完成 LLM深度分析的照片，再按修图 Top-N 数量生成。</li>
                  <li>建议先用 <span class="kbd">深评状态 = 已深评</span> 或 <span class="kbd">完整证据</span> 过滤，再生成最终方案。</li>
                  <li>输出会写入 <span class="kbd">selected_editing_advice.md</span> 和 <span class="kbd">selected_editing_advice.json</span>。Markdown 适合阅读，JSON 适合后续自动化处理。</li>
                  <li>未深评照片只给保守技术草稿；高级 HSL、色彩分级、局部遮罩等细节只在视觉证据足够时输出。</li>
                </ul>
              </div>

              <div class="advice-card">
                <h2>输出文件</h2>
                <table>
                  <tr><td><b>report.csv</b></td><td>表格报告，适合快速排序、筛选、人工复盘。</td></tr>
                  <tr><td><b>report.json</b></td><td>完整结构化结果，包含本地分数、LLM深度分析、时间/相似分组、标记和错误信息。</td></tr>
                  <tr><td><b>selected_editing_advice.md / .json</b></td><td>当前选择或默认 Top-N 的修图建议。</td></tr>
                  <tr><td><b>contact sheet</b></td><td>联系表图像，用于快速浏览候选照片。</td></tr>
                  <tr><td><b>previews</b></td><td>本地生成的压缩预览和缩略图缓存，可重新生成，不应当成原片备份。</td></tr>
                </table>
              </div>

              <div class="advice-card">
                <h2>常见问题排查</h2>
                <ul>
                  <li><b>提示 LLM深度分析失败：</b>先点“检查”确认 key、token/额度和模型可用；再看状态条悬停提示。若是中转站超时，降低深评 Top-N 后重跑通常更稳。</li>
                  <li><b>生成的建议像草稿：</b>检查深评状态。如果照片未深评或证据不足，系统会故意保守，避免编造人物关系和修图细节。</li>
                  <li><b>好照片被本地低分：</b>本地初筛只看技术和结构代理。街头摄影里轻微虚焦、噪点、高反差不应自动淘汰；把这类照片标为“待定”或增加深评 Top-N。</li>
                  <li><b>分组只显示一张：</b>切换“分组”筛选为“成组”或“时间组”，可查看同组其它帧并人工比较决定性瞬间。</li>
                  <li><b>想复盘结果：</b>打开输出目录里的 <span class="kbd">report.json</span>、<span class="kbd">report.csv</span> 或联系表；应用内不再提供历史页。</li>
                </ul>
              </div>
            </div>
            </body></html>
            """
        else:
            return f"""
            <html><head>{self._detail_html_style()}</head><body>
            <div class="detail-shell">
              <div class="summary-card">
                <div class="manual-title">LumaSift User Guide</div>
                <p class="manual-subtitle">A local-first curation and editing-potential workflow for street, documentary, humanistic, and travel photography.</p>
                <table class="flow">
                  <tr>
                    <td>1 Import folder</td><td class="arrow">-&gt;</td>
                    <td>2 Local pre-score</td><td class="arrow">-&gt;</td>
                    <td>3 LLM Deep Analysis Top-N</td><td class="arrow">-&gt;</td>
                    <td>4 Mark and filter</td><td class="arrow">-&gt;</td>
                    <td>5 Generate edit plans</td>
                  </tr>
                </table>
                <p><span class="warn">Principle:</span> local analysis is fast, private, and cheap; story, human relationship, decisive moment, and concrete editing direction should come from LLM Deep Analysis or human inspection.</p>
              </div>

              <div class="advice-card">
                <h2>First Run</h2>
                <table>
                  <tr><td><b>1. Open Settings</b></td><td>Choose the photo folder and output folder. JPG, PNG, and common RAW formats can be mixed. RAW files are not uploaded.</td></tr>
                  <tr><td><b>2. Pick a mode</b></td><td><span class="kbd">Local</span> runs only on-device pre-scoring. <span class="kbd">LLM Deep Analysis</span> runs local pre-score first, then sends Top-N compressed previews to a vision-capable LLM.</td></tr>
                  <tr><td><b>3. Set counts</b></td><td>Scan limit controls how many files are processed. Deep Top-N controls deep-review cost. Advice Top-N controls the default edit-plan count when nothing is manually selected.</td></tr>
                  <tr><td><b>4. Check the key</b></td><td>Enter the API key and click <span class="kbd">Check</span> to verify quota and the active vision model. Keep keys in local settings or environment variables only.</td></tr>
                  <tr><td><b>5. Analyze</b></td><td>Return to Workflow and click <span class="kbd">Analyze</span>. Cancel requests a stop; completed records remain available.</td></tr>
                </table>
              </div>

              <div class="advice-card">
                <h2>Reading the App</h2>
                <table class="mini-grid">
                  <tr><td><b>Top navigation</b><br>Workflow, Settings, Shortcuts, and Help remain reachable during review.</td><td><b>Workflow strip</b><br>Import, pre-score, deep review, and edit-plan stages.</td></tr>
                  <tr><td><b>Review board</b><br>Left grid with rank, score, label, and time/similar group badges. Double-click opens the large preview.</td><td><b>Review panel</b><br>Story read, evidence, relationships, moment, risks, crop, and parameters.</td></tr>
                  <tr><td><b>LLM Deep Analysis status</b><br>Queued, running, done, cache, failed, retry, and cancelled counts.</td><td><b>Output actions</b><br>Open output, contact sheet, and selected-photo editing plan.</td></tr>
                </table>
              </div>

              <div class="advice-card">
                <h2>Filtering and Marking</h2>
                <ul>
                  <li>Search by filename, path, category, style, or label.</li>
                  <li>Filter by category, user label, time/similar group role, pair status, and LLM Deep Analysis status.</li>
                  <li>Before final edit-plan generation, prefer <span class="kbd">LLM-read</span> or <span class="kbd">Concrete read</span>.</li>
                  <li>Use the keep, maybe, and reject buttons to batch-mark selected photos.</li>
                </ul>
              </div>

              <div class="advice-card">
                <h2>LLM Deep Analysis</h2>
                <table>
                  <tr><td><b>Uploads</b></td><td>Only Top-N compressed JPEG previews are uploaded. RAW files stay local.</td></tr>
                  <tr><td><b>Cache</b></td><td>Identical preview and prompt-version hits avoid repeated cost.</td></tr>
                  <tr><td><b>Failures</b></td><td>Network, relay, or truncated model output failures are retried. Final failures keep local pre-score records.</td></tr>
                  <tr><td><b>Not reviewed</b></td><td>Outside Top-N, rejected, or grouped non-best frames may be marked not reviewed or skipped.</td></tr>
                  <tr><td><b>Confidence</b></td><td>Concrete read means specific visible evidence and an editing plan are present; LLM-read means visual output exists but may be weaker.</td></tr>
                </table>
              </div>

              <div class="advice-card">
                <h2>Edit Plans and Outputs</h2>
                <ul>
                  <li>Manual selection is always respected.</li>
                  <li>With no manual selection, the app defaults to LLM-read records within the active filter, then Advice Top-N.</li>
                  <li>Advice is written to <span class="kbd">selected_editing_advice.md</span> and <span class="kbd">selected_editing_advice.json</span>.</li>
                  <li>Unreviewed photos receive conservative technical drafts; advanced color and mask detail requires enough visual evidence.</li>
                  <li>Main reports are <span class="kbd">report.csv</span>, <span class="kbd">report.json</span>, contact sheets, and preview caches.</li>
                </ul>
              </div>
            </div>
            </body></html>
            """

    def _escape(self, value: str) -> str:
        return html.escape(value, quote=True)

    def _dedupe_display_strings(self, values: list[Any]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value).strip()
            normalized = " ".join(text.split())
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(text)
        return result

    def _html_list(self, values: list[Any], fallback: str) -> str:
        items = [str(item) for item in values if str(item).strip()]
        if not items:
            if not fallback:
                return ""
            items = [fallback]
        return "<ul>" + "".join(f"<li>{self._escape(item)}</li>" for item in items) + "</ul>"

    def _score_bar(self, label: str, value: Any) -> str:
        try:
            score = max(0.0, min(100.0, float(value or 0)))
        except (TypeError, ValueError):
            score = 0.0
        return (
            "<div class='score-row'>"
            f"<span>{self._escape(label)}</span><b>{score:.0f}</b>"
            f"<div class='bar'><div style='width:{score:.0f}%;'></div></div>"
            "</div>"
        )

    def _format_advice_markdown_legacy_html(self, payload: dict[str, Any]) -> str:
        markdown = render_selected_editing_advice_markdown(payload)
        escaped = self._escape(markdown)
        count = int(payload.get("selected_count", 0) or 0)
        title = f"{count} 张照片的修图方案" if self.language == "zh" else f"Editing plan for {count} selected photos"
        note = "已写入 selected_editing_advice.md / .json" if self.language == "zh" else "Written to selected_editing_advice.md and selected_editing_advice.json."
        return f"""
        <html><head>{self._detail_html_style()}</head><body>
        <h2>{title}</h2>
        <p class="meta">{note}</p>
        <pre>{escaped}</pre>
        </body></html>
        """

    def _format_advice_html(self, payload: dict[str, Any]) -> str:
        items = payload.get("selected_editing_advice", []) or []
        count = int(payload.get("selected_count", 0) or 0)
        title = f"{count} 张照片的修图方案" if self.language == "zh" else f"Editing plan for {count} selected photos"
        note = "已写入 selected_editing_advice.md / .json" if self.language == "zh" else "Written to selected_editing_advice.md and selected_editing_advice.json."
        blocks = "".join(self._format_advice_item_html(item) for item in items)
        return f"""
        <html><head>{self._detail_html_style()}</head><body>
        <div class="detail-shell">
          <div class="summary-card">
            <span class="rank">{self._escape(str(count))}</span>
            <h2>{title}</h2>
            <p class="meta">{note}</p>
          </div>
          {blocks}
        </div>
        </body></html>
        """

    def _format_advice_item_html(self, item: dict[str, Any]) -> str:
        rank = self._escape(str(item.get("rank", "?")))
        filename = self._escape(str(item.get("filename", "")))
        score = float(item.get("final_selection_score", 0) or 0)
        style = self._escape(str(item.get("recommended_style_label") or item.get("recommended_style", "")).replace("_", " "))
        category = self._escape(str(item.get("category_label") or item.get("category", "")).replace("_", " "))
        tone = item.get("tone_recommendation") if isinstance(item.get("tone_recommendation"), dict) else {}
        tone_text = self._escape(str(tone.get("label") or tone.get("recommendation", "")).replace("_", " "))
        tone_reason = self._escape(str(tone.get("rationale", "")))
        status = item.get("analysis_status") if isinstance(item.get("analysis_status"), dict) else {}
        status_text = self._escape(str(status.get("label", "")))
        status_note = self._escape(str(status.get("note", "")))
        blocked_reason = self._escape(str(item.get("blocked_reason", "") or ""))
        photo_reading = item.get("photo_reading") if isinstance(item.get("photo_reading"), dict) else {}
        read_summary = self._escape(str(photo_reading.get("summary", "") or ""))
        evidence = self._html_list(photo_reading.get("visible_evidence", [])[:6] if isinstance(photo_reading.get("visible_evidence"), list) else [], "")
        relationship = self._escape(str(photo_reading.get("subject_relationship", "") or ""))
        moment = self._escape(str(photo_reading.get("decisive_moment_read", "") or ""))
        why_frame = self._escape(str(photo_reading.get("why_this_frame", "") or ""))
        decision = item.get("content_decision") if isinstance(item.get("content_decision"), dict) else {}
        decision_note = self._escape(str(decision.get("editor_note", "") or ""))
        keep_reasons = self._html_list(decision.get("keep_reasons", [])[:5] if isinstance(decision.get("keep_reasons"), list) else [], "")
        risk_reasons = self._html_list(decision.get("risks", [])[:5] if isinstance(decision.get("risks"), list) else [], "")
        crop_plan = item.get("crop_plan") if isinstance(item.get("crop_plan"), dict) else {}
        crop_keep = self._html_list(crop_plan.get("keep", []) if isinstance(crop_plan.get("keep"), list) else [], "")
        crop_remove = self._html_list(crop_plan.get("remove_or_reduce", []) if isinstance(crop_plan.get("remove_or_reduce"), list) else [], "")
        crop_reason = self._escape(str(crop_plan.get("reason", "") or item.get("crop_strategy", "") or ""))
        crop_box_html = self._format_crop_box_detail_html(item)
        avoid_overediting = self._escape(str(item.get("avoid_overediting", "") or ""))
        local_masks = item.get("local_masks") if isinstance(item.get("local_masks"), list) else []
        labels = item.get("lightroom_parameter_labels", {})
        params = item.get("lightroom_parameters", {}) or {}
        advanced_html = self._format_advanced_parameters_html(
            item.get("advanced_lightroom_parameters"),
            item.get("advanced_lightroom_parameter_labels"),
            include_basic=False,
        )
        parameter_order = [
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
        ]
        rows = ""
        if isinstance(params, dict):
            for key in parameter_order:
                label = labels.get(key, key.replace("_", " ").title()) if isinstance(labels, dict) else key
                rows += f"<tr><td>{self._escape(str(label))}</td><td><b>{self._escape(str(params.get(key, '')))}</b></td></tr>"
        local_adjustments = self._html_list(
            item.get("local_adjustments", [])[:8],
            "暂无局部调整建议" if self.language == "zh" else "No local adjustments.",
        )
        handling = item.get("grain_sharpness_motion_blur", {}) or {}
        handling_rows = ""
        if isinstance(handling, dict):
            handling_labels = {
                "grain": "颗粒" if self.language == "zh" else "Grain",
                "sharpness": "锐化" if self.language == "zh" else "Sharpness",
                "motion_blur": "运动模糊" if self.language == "zh" else "Motion blur",
            }
            for key, label in handling_labels.items():
                handling_rows += f"<tr><td>{label}</td><td>{self._escape(str(handling.get(key, '')))}</td></tr>"
        text = {
            "rank": "第" if self.language == "zh" else "Rank",
            "rank_suffix": " 张" if self.language == "zh" else "",
            "style": "风格" if self.language == "zh" else "Style",
            "tone": "色彩方向" if self.language == "zh" else "Tone",
            "direction": "总体方向" if self.language == "zh" else "Direction",
            "status": "分析状态" if self.language == "zh" else "Analysis",
            "read": "照片阅读" if self.language == "zh" else "Photo Read",
            "evidence": "可见证据" if self.language == "zh" else "Visible Evidence",
            "relationship": "关系" if self.language == "zh" else "Relationship",
            "moment": "瞬间" if self.language == "zh" else "Moment",
            "why_frame": "为什么是这张" if self.language == "zh" else "Why This Frame",
            "decision": "内容判断" if self.language == "zh" else "Content Decision",
            "crop_keep": "裁切保留" if self.language == "zh" else "Crop Keep",
            "crop_remove": "裁切压弱" if self.language == "zh" else "Crop Reduce",
            "masks": "局部蒙版" if self.language == "zh" else "Local Masks",
            "avoid": "别修掉" if self.language == "zh" else "Do Not Remove",
            "params": "Lightroom 参数" if self.language == "zh" else "Lightroom Parameters",
            "crop": "裁切" if self.language == "zh" else "Crop",
            "local": "局部调整" if self.language == "zh" else "Local Adjustments",
            "detail": "质感处理" if self.language == "zh" else "Texture Handling",
        }
        return f"""
        <div class="advice-card">
          <div class="advice-head">
            <table class="head-table"><tr>
              <td><span class="rank">{text["rank"]} {rank}{text["rank_suffix"]}</span><span class="pill">{category}</span><h2>{filename}</h2></td>
              <td class="score-cell">{score:.1f}</td>
            </tr></table>
            <p class="meta">{text["status"]}: {status_text} - {status_note}</p>
            <p class="meta">{text["style"]}: {style} | {text["tone"]}: {tone_text} - {tone_reason}</p>
          </div>
          {f'<h3>{text["status"]}</h3><p>{blocked_reason}</p>' if blocked_reason else ''}
          <h3>{text["read"]}</h3>
          <p>{read_summary}</p>
          {f'<h3>{text["evidence"]}</h3>{evidence}' if evidence else ''}
          {f'<h3>{text["relationship"]}</h3><p>{relationship}</p>' if relationship else ''}
          {f'<h3>{text["moment"]}</h3><p>{moment}</p>' if moment else ''}
          {f'<h3>{text["why_frame"]}</h3><p>{why_frame}</p>' if why_frame else ''}
          <h3>{text["decision"]}</h3>
          {f'<p>{decision_note}</p>' if decision_note else ''}
          {keep_reasons}
          {risk_reasons}
          <h3>{text["direction"]}</h3>
          <p>{self._escape(str(item.get("editing_intent") or item.get("editing_direction", "")))}</p>
          <h3>{text["params"]}</h3>
          <table class="param-table">{rows}</table>
          {advanced_html}
          <h3>{text["crop"]}</h3>
          <p>{crop_reason}</p>
          {crop_box_html}
          {f'<h3>{text["crop_keep"]}</h3>{crop_keep}' if crop_keep else ''}
          {f'<h3>{text["crop_remove"]}</h3>{crop_remove}' if crop_remove else ''}
          <h3>{text["local"]}</h3>
          {local_adjustments}
          {self._format_local_masks_html(local_masks, text["masks"])}
          {f'<h3>{text["avoid"]}</h3><p>{avoid_overediting}</p>' if avoid_overediting else ''}
          <h3>{text["detail"]}</h3>
          <table>{handling_rows}</table>
        </div>
        """

    def _format_local_masks_html(self, local_masks: list[Any], title: str) -> str:
        if not local_masks:
            return ""
        rows = ""
        for mask in local_masks[:6]:
            if not isinstance(mask, dict):
                continue
            target = self._escape(str(mask.get("target", "")))
            operation = self._escape(str(mask.get("operation", "")))
            reason = self._escape(str(mask.get("reason", "")))
            rows += f"<tr><td>{target}</td><td>{operation}<br>{reason}</td></tr>"
        if not rows:
            return ""
        return f"<h3>{title}</h3><table>{rows}</table>"

    def _format_advanced_parameters_html(self, sections: Any, labels: Any, *, include_basic: bool = True) -> str:
        if not isinstance(sections, dict):
            return ""
        label_map = labels if isinstance(labels, dict) else {}
        section_labels = label_map.get("sections") if isinstance(label_map.get("sections"), dict) else {}
        key_labels = label_map.get("keys") if isinstance(label_map.get("keys"), dict) else {}
        blocks: list[str] = []
        for section_key in ADVANCED_LIGHTROOM_SECTION_ORDER:
            if section_key == "basic" and not include_basic:
                continue
            value = sections.get(section_key)
            if not isinstance(value, dict) or not value:
                continue
            title = str(section_labels.get(section_key) or self._lightroom_detail_label(section_key))
            rows = self._format_parameter_rows(value, key_labels=key_labels)
            if rows:
                blocks.append(f"<h3>{self._escape(title)}</h3><table class=\"param-table\">{rows}</table>")
        return "".join(blocks)

    def _format_parameter_rows(self, values: dict[str, Any], *, key_labels: dict[str, Any]) -> str:
        rows: list[str] = []
        for key, value in values.items():
            label = str(key_labels.get(key) or self._lightroom_detail_label(str(key)))
            if isinstance(value, dict):
                nested_parts = []
                for nested_key, nested_value in value.items():
                    nested_label = str(key_labels.get(nested_key) or self._lightroom_detail_label(str(nested_key)))
                    nested_parts.append(f"{self._escape(nested_label)} {self._escape(self._localized_parameter_value(nested_value, key_labels))}")
                display = " / ".join(nested_parts)
            else:
                display = self._escape(self._localized_parameter_value(value, key_labels))
            rows.append(f"<tr><td>{self._escape(label)}</td><td>{display}</td></tr>")
        return "".join(rows)

    def _localized_parameter_value(self, value: Any, key_labels: dict[str, Any]) -> str:
        text = str(value)
        return str(key_labels.get(text, text))

    def _lightroom_detail_label(self, key: str) -> str:
        normalized = key.strip()
        if self.language != "zh":
            return normalized.replace("_", " ").title()
        return {
            "basic": "基础",
            "tone_curve": "曲线",
            "hsl_color_mixer": "HSL / 颜色混合",
            "color_grading": "色彩分级",
            "calibration": "校准",
            "detail": "细节",
            "noise_reduction": "降噪",
            "lens_corrections": "镜头校正",
            "effects_grain_vignette": "效果 / 颗粒 / 暗角",
            "exposure": "曝光",
            "contrast": "对比度",
            "highlights": "高光",
            "shadows": "阴影",
            "whites": "白色色阶",
            "blacks": "黑色色阶",
            "texture": "纹理",
            "clarity": "清晰度",
            "dehaze": "去朦胧",
            "vibrance": "自然饱和度",
            "saturation": "饱和度",
            "temperature": "色温",
            "tint": "色调",
            "point_curve": "点曲线",
            "lights": "亮调",
            "darks": "暗调",
            "red": "红色",
            "orange": "橙色",
            "yellow": "黄色",
            "green": "绿色",
            "aqua": "青色",
            "blue": "蓝色",
            "purple": "紫色",
            "magenta": "洋红",
            "hue": "色相",
            "luminance": "明亮度",
            "midtones": "中间调",
            "blending": "混合",
            "balance": "平衡",
            "shadow_tint": "阴影色调",
            "red_primary_hue": "红原色色相",
            "red_primary_saturation": "红原色饱和度",
            "green_primary_hue": "绿原色色相",
            "green_primary_saturation": "绿原色饱和度",
            "blue_primary_hue": "蓝原色色相",
            "blue_primary_saturation": "蓝原色饱和度",
            "sharpening_amount": "锐化数量",
            "radius": "半径",
            "masking": "蒙版",
            "color": "颜色",
            "color_detail": "颜色细节",
            "remove_chromatic_aberration": "移除色差",
            "enable_profile_corrections": "启用配置文件校正",
            "manual_distortion": "手动扭曲",
            "manual_vignetting": "手动暗角",
            "grain_amount": "颗粒数量",
            "grain_size": "颗粒大小",
            "grain_roughness": "颗粒粗糙度",
            "post_crop_vignette": "裁剪后暗角",
            "vignette_midpoint": "暗角中点",
            "vignette_feather": "暗角羽化",
        }.get(normalized, normalized.replace("_", " "))

    def _detail_html_style(self) -> str:
        style = """
        <style>
        body { color: #dbe7f3; font-family: Microsoft YaHei UI, Microsoft YaHei, Segoe UI; font-size: 12px; background: #090d12; margin: 0; }
        h2 { margin: 0 0 4px 0; font-size: 19px; color: #f8fafc; }
        h3 { margin: 12px 0 6px 0; font-size: 12px; color: #00a6ff; text-transform: uppercase; letter-spacing: 0px; border-left: 5px solid #ffd400; padding-left: 7px; }
        h4 { margin: 8px 0 3px 0; font-size: 12px; color: #f8fafc; }
        p { line-height: 1.45; margin: 4px 0 8px 0; color: #c8d4e0; }
        ul { margin: 4px 0 8px 18px; padding: 0; }
        li { margin-bottom: 5px; }
        table { border-collapse: collapse; width: 100%; margin-top: 8px; }
        td { border-bottom: 1px solid #26313d; padding: 6px; vertical-align: top; color: #dbe7f3; }
        pre { white-space: pre-wrap; background: #0b0f14; border: 1px solid #26313d; border-radius: 8px; padding: 10px; color: #dbe7f3; }
        .summary-card { background: #101820; border: 1px solid #293646; border-left: 6px solid #ff3b30; border-radius: 8px; padding: 10px; margin-bottom: 10px; }
        .analysis-state { background: #101820; border: 1px solid #293646; border-left: 6px solid #ffd400; border-radius: 8px; padding: 9px 10px; margin: 8px 0 10px 0; }
        .analysis-state b { color: #f8fafc; font-size: 13px; }
        .analysis-state p { margin-bottom: 0; }
        .analysis-state.failed { border-left-color: #ff3b30; background: #15100f; }
        .analysis-state.local { border-left-color: #ffd400; }
        .analysis-state.weak { border-left-color: #ff9f1c; }
        .professional-review { background: #0d131a; border: 1px solid #293646; border-left: 6px solid #00a6ff; border-radius: 8px; padding: 10px; margin: 8px 0 12px 0; }
        .professional-review h3 { margin-top: 0; }
        .professional-review p { line-height: 1.55; }
        .advice-card { background: #0d131a; border: 1px solid #293646; border-left: 6px solid #00a6ff; border-radius: 8px; padding: 10px; margin: 8px 0 12px 0; }
        .crop-note { background: #0d131a; border: 1px solid #293646; border-left: 5px solid #ffd400; border-radius: 8px; padding: 8px; }
        .crop-note span { color: #93a4b8; }
        .advice-head h2 { margin-top: 5px; }
        .pill { display: inline-block; margin-left: 8px; padding: 2px 8px; border-radius: 8px; background: #17324a; color: #8fd3ff; font-weight: 800; }
        .rank { color: #ffd400; font-weight: 900; }
        .head-table { margin-top: 0; border: 0; }
        .head-table td { border: 0; padding: 0; }
        .score-cell { color: #f8fafc; font-size: 30px; font-weight: 900; text-align: right; width: 92px; }
        .score { color: #f8fafc; font-size: 28px; font-weight: 900; }
        .small-score { font-size: 24px; }
        .meta { color: #93a4b8; }
        .metrics { margin-top: 10px; }
        .metrics td { background: #0c1117; border: 1px solid #26313d; padding: 8px; text-align: center; width: 33%; }
        .metrics b { display: block; color: #ffd400; font-size: 18px; }
        .metrics span { color: #9fb0c2; font-size: 11px; }
        .score-row { margin: 8px 0 10px 0; }
        .score-row span { font-weight: 700; color: #c8d4e0; }
        .score-row b { color: #f8fafc; }
        .bar { margin-top: 4px; height: 8px; background: #26313d; border-radius: 4px; }
        .bar div { height: 8px; background: #00a6ff; border-radius: 4px; }
        .param-table td:nth-child(1) { width: 42%; color: #9fb0c2; }
        .param-table td:nth-child(2) { width: 58%; color: #f8fafc; }
        .manual-title { color: #f8fafc; font-size: 22px; font-weight: 900; margin: 0 0 6px 0; }
        .manual-subtitle { color: #9fb0c2; font-size: 12px; margin-bottom: 10px; }
        .flow { margin: 10px 0 14px 0; }
        .flow td { border: 1px solid #26313d; background: #101820; text-align: center; font-weight: 800; }
        .flow .arrow { width: 30px; color: #ffd400; background: #0b0f14; border: 0; }
        .mini-grid td { width: 50%; background: #0b0f14; border: 1px solid #26313d; }
        .kbd { background: #17212b; border: 1px solid #344457; border-radius: 4px; padding: 1px 5px; color: #f8fafc; font-weight: 800; }
        .warn { color: #ffd400; font-weight: 800; }
        </style>
        """
        if self.theme != "light":
            return style
        light_style = _light_theme_stylesheet(style)
        light_style = light_style.replace(
            ".summary-card { background: #ffffff; border: 1px solid #cbd5e1; border-left: 6px solid #ff3b30;",
            ".summary-card { background: #ffffff; border: 1px solid #cbd5e1; border-left: 6px solid #5e6ad2;",
        )
        return light_style

    def _apply_style(self) -> None:
        self.setProperty("theme", self.theme)
        if hasattr(self, "photo_list"):
            self.photo_list.setProperty("theme", self.theme)
        style = """
            QMainWindow, QWidget {
                background: #090d12;
                color: #dbe7f3;
                font-family: Microsoft YaHei UI, Microsoft YaHei, Segoe UI;
                font-size: 12px;
            }
            QLabel { background: transparent; }
            QLabel#title { font-size: 34px; font-weight: 900; color: #f8fafc; letter-spacing: 0px; }
            QLabel#navLogo { background: transparent; padding: 0px; }
            QLabel#subtitle { color: #9fb0c2; font-size: 13px; }
            QLabel#muted, QLabel#statCaption, QLabel#stepCaption { color: #93a4b8; }
            QLabel#muted[attention="true"] { color: #ffd400; font-weight: 900; }
            QLabel#actionStatus { color: #93a4b8; font-size: 11px; font-weight: 800; min-height: 16px; }
            QLabel#sectionTitle { font-size: 14px; font-weight: 900; color: #f8fafc; }
            QLabel#fieldLabel { color: #c8d4e0; font-weight: 800; }
            QLabel#miniLabel { color: #9fb0c2; font-weight: 800; }
            QLabel#qwenQueueLabel {
                color: #dbe7f3;
                background: #101820;
                border: 1px solid #26384a;
                border-left: 6px solid #ffd400;
                border-radius: 0px;
                padding: 6px 10px;
                font-weight: 700;
            }
            QFrame#qwenStatusPanel, QFrame#navPage {
                background: #090d12;
                border: none;
                border-radius: 0px;
            }
            QFrame#hero, QFrame#topNav, QFrame#controlCard, QFrame#toolbar, QFrame#reviewBar {
                background: #111820;
                border: 1px solid #26313d;
                border-radius: 0px;
            }
            QFrame#topNav {
                background: #1b1b1b;
                border: none;
                border-bottom: 1px solid #2f3640;
                min-height: 34px;
                max-height: 34px;
            }
            QFrame#detailPanel {
                background: #0d1218;
                border: 2px solid #26313d;
                border-left: 6px solid #ff3b30;
                border-radius: 0px;
            }
            QFrame#constructGuide { background: transparent; border: none; }
            QFrame#guideCyan { background: #00a6ff; border: none; }
            QFrame#guideYellow { background: #ffd400; border: none; }
            QFrame#guideRed { background: #ff3b30; border: none; }
            QFrame#actionBar {
                background: #0a0f15;
                border: 1px solid #26313d;
                border-radius: 0px;
            }
            QFrame#statCard {
                background: #101820;
                border: 1px solid #293646;
                border-radius: 0px;
                min-width: 92px;
            }
            QFrame#optionBar { background: transparent; border: none; }
            QFrame#advancedPanel {
                background: #0f141a;
                border: 1px solid #26313d;
                border-left: 6px solid #00a6ff;
                border-radius: 0px;
            }
            QFrame#miniControl {
                background: #151b22;
                border: 1px solid #293646;
                border-radius: 0px;
                min-width: 132px;
            }
            QLabel#statValue { font-size: 20px; font-weight: 900; color: #8fd3ff; }
            QFrame#workflow { background: transparent; }
            QFrame#stepCard {
                background: #151b22;
                border: 1px solid #26313d;
                border-radius: 0px;
            }
            QFrame#stepCard[state="active"] {
                background: #172232;
                border: 2px solid #ffd400;
            }
            QFrame#stepCard[state="done"] {
                background: #111820;
                border: 1px solid #334155;
                border-left: 5px solid #61d394;
            }
            QLabel#stepTitle { font-weight: 900; color: #f8fafc; }
            QLabel#stepState { color: #93a4b8; font-size: 11px; font-weight: 900; }
            QFrame#stepCard[state="active"] QLabel#stepState { color: #ffd400; }
            QFrame#stepCard[state="done"] QLabel#stepState { color: #61d394; }
            QLineEdit, QSpinBox, QComboBox, QTextEdit, QListView {
                background: #0c1117;
                border: 1px solid #2a3645;
                border-radius: 0px;
                padding: 7px;
                color: #dbe7f3;
                selection-background-color: #245d82;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
                border: 2px solid #ffd400;
            }
            QLineEdit[attention="true"], QComboBox[attention="true"] {
                border: 2px solid #ffd400;
                background: #15120a;
            }
            QSpinBox {
                font-size: 14px;
                font-weight: 900;
                padding: 0px 10px;
                min-height: 32px;
                max-height: 32px;
            }
            QComboBox#settingInput, QSpinBox#settingInput {
                min-height: 34px;
                max-height: 34px;
                padding: 0px 10px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 0px;
                border: none;
            }
            QPushButton {
                border: none;
                border-radius: 0px;
                padding: 9px 13px;
                font-weight: 800;
            }
            QPushButton#navButton {
                background: transparent;
                color: #a7a7a7;
                border: none;
                border-radius: 0px;
                padding: 7px 10px;
                font-weight: 500;
                min-height: 32px;
                max-height: 32px;
            }
            QPushButton#navButton:hover {
                color: #f8fafc;
                background: #242424;
                border-bottom: 2px solid #00a6ff;
            }
            QPushButton#navButton[active="true"] {
                color: #f8fafc;
                background: #20242a;
                border-bottom: 2px solid #ffd400;
            }
            QPushButton#primaryButton { background: #00a6ff; color: #061019; }
            QPushButton#primaryButton:hover { background: #45c0ff; }
            QPushButton#secondaryButton { background: #233044; color: #f8fafc; }
            QPushButton#secondaryButton:hover { background: #334155; }
            QPushButton#ghostButton { background: transparent; color: #ffd400; border: 1px solid #334155; }
            QPushButton#ghostButton:hover { background: #172232; }
            QPushButton#markKeepButton { background: #00a6ff; color: #061019; }
            QPushButton#markKeepButton:hover { background: #45c0ff; }
            QPushButton#markMaybeButton { background: #ffd400; color: #111827; }
            QPushButton#markMaybeButton:hover { background: #ffe45c; }
            QPushButton#markRejectButton { background: #ff3b30; color: #ffffff; }
            QPushButton#markRejectButton:hover { background: #ff625a; }
            QPushButton#markKeepButton, QPushButton#markMaybeButton, QPushButton#markRejectButton {
                font-size: 13px;
                font-weight: 900;
                padding: 6px 8px;
            }
            QPushButton:disabled { background: #26313d; color: #66778a; }
            QListView#photoGrid {
                background: #0c1117;
                border: 1px solid #26313d;
                border-radius: 0px;
                padding: 10px;
            }
            QListView#photoGrid::item {
                background: #151b22;
                border: 1px solid #293646;
                border-radius: 8px;
                padding: 8px;
                color: #dbe7f3;
            }
            QListView#photoGrid::item:hover {
                border: 1px solid #8fd3ff;
                background: #172232;
            }
            QListView#photoGrid::item:selected {
                border: 2px solid #2ea8ff;
                background: #172232;
            }
            QLabel#resultCount {
                background: #172232;
                color: #8fd3ff;
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: 800;
            }
            QTextEdit#detailText {
                background: #090d12;
                border: 1px solid #26313d;
                border-radius: 8px;
                padding: 8px;
                color: #dbe7f3;
            }
            QProgressBar {
                border: 1px solid #2a3645;
                border-radius: 6px;
                text-align: center;
                background: #0c1117;
                color: #dbe7f3;
                height: 18px;
                font-weight: 700;
            }
            QProgressBar::chunk { background: #00a6ff; border-radius: 5px; }
            """
        if self.theme == "light":
            style = (
                _light_theme_stylesheet(style)
                + """
                QFrame#topNav {
                    background: #ffffff;
                    border: none;
                    border-bottom: 1px solid #e6e8ee;
                }
                QPushButton#navButton {
                    color: #6b7280;
                    background: transparent;
                }
                QPushButton#navButton:hover {
                    color: #111827;
                    background: #f3f4f6;
                    border-bottom: 2px solid #5e6ad2;
                }
                QPushButton#navButton[active="true"] {
                    color: #111827;
                    background: #eef2ff;
                    border-bottom: 2px solid #5e6ad2;
                }
                QFrame#actionBar { background: #ffffff; border: 1px solid #e6e8ee; }
                QFrame#detailPanel { border-left: 6px solid #5e6ad2; }
                QFrame#guideCyan, QFrame#guideYellow { background: #5e6ad2; }
                QLabel#qwenQueueLabel { border-left: 6px solid #5e6ad2; }
                QPushButton#markMaybeButton { background: #8b5cf6; color: #ffffff; }
                QPushButton#markMaybeButton:hover { background: #7c3aed; color: #ffffff; }
                """
            )
        self.setStyleSheet(style)

    def closeEvent(self, event: Any) -> None:
        if self.allow_close:
            app = QApplication.instance()
            if app is not None:
                app.removeEventFilter(self)
            super().closeEvent(event)
            return
        if self._background_tasks_running():
            event.ignore()
            self.pending_close = True
            self.status_label.setText(self._t("closing"))
            self._request_background_stop()
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)

    def _background_tasks_running(self) -> bool:
        analysis_running = self.worker_thread is not None and self.worker_thread.isRunning()
        thumbnail_running = self.thumbnail_thread is not None and self.thumbnail_thread.isRunning()
        selected_review_running = self.selected_review_thread is not None and self.selected_review_thread.isRunning()
        return bool(analysis_running or thumbnail_running or selected_review_running)

    def _request_background_stop(self) -> None:
        self._cancel_analysis(close_after_stop=True)
        if self.thumbnail_worker is not None:
            self.thumbnail_worker.stop()
        if self.thumbnail_thread is not None and self.thumbnail_thread.isRunning():
            self.thumbnail_thread.quit()
        if not self._background_tasks_running():
            self._finish_pending_close_if_ready()

    def _finish_pending_close_if_ready(self) -> None:
        if self.pending_close and not self._background_tasks_running():
            self.allow_close = True
            QTimer.singleShot(0, self.close)


def main() -> int:
    install_crash_logging()
    configure_windows_app_identity()
    app = QApplication(sys.argv)
    apply_application_font(app)
    app.setOrganizationName("LumaSift")
    app.setApplicationName("LumaSift")
    app.setApplicationDisplayName("LumaSift")
    app.setDesktopFileName("LumaSift")
    app.setWindowIcon(lumasift_app_icon())
    window = LumaSiftWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

