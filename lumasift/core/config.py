from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _split_keys(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class ScoreWeights:
    storytelling: float = 0.22
    human_documentary_value: float = 0.18
    decisive_moment: float = 0.16
    emotional_impact: float = 0.14
    visual_tension: float = 0.12
    editing_potential: float = 0.12
    technical_quality: float = 0.06


@dataclass
class Settings:
    input_dir: Path = Path("./sample_photos")
    output_dir: Path = Path("./outputs")
    ai_mode: str = "local_only"
    top_n_api_analysis: int = 20
    limit: int | None = None
    resume: bool = False
    selected_ranks: str | None = None
    selected_paths: str | None = None
    supported_extensions: tuple[str, ...] = (".arw", ".ARW", ".png", ".PNG", ".jpg", ".JPG", ".jpeg", ".JPEG")
    vision_api_base_url: str = "https://api.newcoin.top/v1"
    vision_model: str = "qwen3.6-plus"
    vision_api_keys: list[str] = field(default_factory=list)
    vision_max_tokens: int = 8192
    request_timeout_seconds: int = 90
    qwen_include_rejected: bool = False
    qwen_group_winners_only: bool = True
    weights: ScoreWeights = field(default_factory=ScoreWeights)

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            input_dir=Path(os.getenv("LUMASIFT_INPUT_DIR", "./sample_photos")),
            output_dir=Path(os.getenv("LUMASIFT_OUTPUT_DIR", "./outputs")),
            ai_mode=os.getenv("LUMASIFT_AI_MODE", "local_only"),
            top_n_api_analysis=int(os.getenv("LUMASIFT_TOP_N_API_ANALYSIS", "20")),
            limit=_optional_int(os.getenv("LUMASIFT_LIMIT")),
            selected_ranks=os.getenv("LUMASIFT_SELECTED_RANKS"),
            selected_paths=os.getenv("LUMASIFT_SELECTED_PATHS"),
            vision_api_base_url=os.getenv("LUMASIFT_VISION_API_BASE_URL", "https://api.newcoin.top/v1"),
            vision_model=os.getenv("LUMASIFT_VISION_MODEL", "qwen3.6-plus"),
            vision_api_keys=_split_keys(os.getenv("LUMASIFT_VISION_API_KEYS")),
            vision_max_tokens=int(os.getenv("LUMASIFT_VISION_MAX_TOKENS", "8192")),
            qwen_include_rejected=_optional_bool(os.getenv("LUMASIFT_QWEN_INCLUDE_REJECTED")),
            qwen_group_winners_only=not _optional_bool(os.getenv("LUMASIFT_QWEN_INCLUDE_GROUP_NON_WINNERS")),
        )

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "runs").mkdir(parents=True, exist_ok=True)


def _optional_int(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    return int(value)


def _optional_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}
