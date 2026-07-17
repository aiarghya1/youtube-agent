"""Load settings from .env and config.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    youtube_api_key: str
    gmail_address: str
    gmail_app_password: str
    report_to: str
    anthropic_api_key: str

    default_niches: list[str] = field(default_factory=list)
    region_code: str = "IN"
    relevance_language: str = "hi"
    top_n_creators: int = 20
    videos_per_creator: int = 25
    short_max_seconds: int = 60
    rank_by: str = "subscribers"

    @property
    def use_llm(self) -> bool:
        return bool(self.anthropic_api_key)


def load_settings(config_path: Path | None = None) -> Settings:
    load_dotenv(ROOT / ".env")

    cfg_path = config_path or (ROOT / "config.yaml")
    cfg: dict = {}
    if cfg_path.exists():
        cfg = yaml.safe_load(cfg_path.read_text()) or {}

    gmail = os.getenv("GMAIL_ADDRESS", "").strip()
    report_to = os.getenv("REPORT_TO", "").strip() or gmail

    return Settings(
        youtube_api_key=os.getenv("YOUTUBE_API_KEY", "").strip(),
        gmail_address=gmail,
        gmail_app_password=os.getenv("GMAIL_APP_PASSWORD", "").strip(),
        report_to=report_to,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        default_niches=cfg.get("default_niches", []),
        region_code=cfg.get("region_code", "IN"),
        relevance_language=cfg.get("relevance_language", "hi"),
        top_n_creators=int(cfg.get("top_n_creators", 20)),
        videos_per_creator=int(cfg.get("videos_per_creator", 25)),
        short_max_seconds=int(cfg.get("short_max_seconds", 60)),
        rank_by=cfg.get("rank_by", "subscribers"),
    )


def validate_for_run(settings: Settings) -> list[str]:
    """Return a list of human-readable problems that would block a run."""
    problems = []
    if not settings.youtube_api_key:
        problems.append("YOUTUBE_API_KEY is not set (see README).")
    return problems


def validate_for_email(settings: Settings) -> list[str]:
    problems = []
    if not settings.gmail_address:
        problems.append("GMAIL_ADDRESS is not set.")
    if not settings.gmail_app_password:
        problems.append("GMAIL_APP_PASSWORD is not set (see README).")
    return problems
