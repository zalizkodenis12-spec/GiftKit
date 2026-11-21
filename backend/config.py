"""Application configuration with .env loading and runtime DB overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

IS_VERCEL: bool = bool(
    os.environ.get("VERCEL")
    or os.environ.get("VERCEL_ENV")
    or os.environ.get("VERCEL_REGION")
    or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
)


class Settings(BaseSettings):
    """Base configuration loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "TON Gift Terminal Pro"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DATABASE_PATH: str = "data/terminal.db"

    # Risk & Trading
    DRY_RUN: bool = True
    DAILY_LIMIT_TON: float = 250.0
    MAX_SINGLE_BUY_TON: float = 80.0
    STOP_LOSS_PERCENT: float = 15.0
    WALLET_ADDRESS: str = ""

    # Telegram Bot & Mini App
    TG_BOT_TOKEN: str = ""
    TG_ADMIN_CHAT_ID: str = ""
    WEBAPP_URL: str = "https://t.me"

    # Official Telegram MTProto Client API (for automated MRKT & Tonnel initData refresh)
    TG_API_ID: int = 0
    TG_API_HASH: str = ""
    TG_SESSION_STRING: str = ""

    # External Marketplace Credentials (optional for enhanced live access)
    GETGEMS_API_KEY: str = ""
    PORTALS_INIT_DATA: str = ""
    MRKT_INIT_DATA: str = ""
    TONNEL_INIT_DATA: str = ""

    # Optional AI Vision LLM Keys (Gemini 2.0 Flash / OpenAI GPT-4o-mini)
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # Engine intervals (seconds)
    SNIPER_POLL_INTERVAL: int = Field(default=18, ge=5)
    UNDERCUT_POLL_INTERVAL: int = Field(default=25, ge=5)
    SNAPSHOT_INTERVAL: int = Field(default=300, ge=30)

    def resolved_db_path(self) -> Path:
        if IS_VERCEL:
            path = Path("/tmp/giftkit.db")
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        path = Path(self.DATABASE_PATH)
        if not path.is_absolute():
            # Resolve relative to project root (parent of backend/)
            project_root = Path(__file__).resolve().parent.parent
            path = project_root / path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        except OSError:
            fallback = Path("/tmp/giftkit.db")
            fallback.parent.mkdir(parents=True, exist_ok=True)
            return fallback


# Runtime settings store that merges .env defaults with SQLite overrides
SETTINGS_KEYS: dict[str, tuple[str, type]] = {
    "dry_run": ("DRY_RUN", bool),
    "daily_limit_ton": ("DAILY_LIMIT_TON", float),
    "max_single_buy_ton": ("MAX_SINGLE_BUY_TON", float),
    "stop_loss_percent": ("STOP_LOSS_PERCENT", float),
    "wallet_address": ("WALLET_ADDRESS", str),
    "tg_bot_token": ("TG_BOT_TOKEN", str),
    "tg_admin_chat_id": ("TG_ADMIN_CHAT_ID", str),
    "webapp_url": ("WEBAPP_URL", str),
    "tg_api_id": ("TG_API_ID", int),
    "tg_api_hash": ("TG_API_HASH", str),
    "tg_session_string": ("TG_SESSION_STRING", str),
    "getgems_api_key": ("GETGEMS_API_KEY", str),
    "portals_init_data": ("PORTALS_INIT_DATA", str),
    "mrkt_init_data": ("MRKT_INIT_DATA", str),
    "tonnel_init_data": ("TONNEL_INIT_DATA", str),
    "gemini_api_key": ("GEMINI_API_KEY", str),
    "openai_api_key": ("OPENAI_API_KEY", str),
}

SECRET_KEYS = {
    "tg_bot_token",
    "tg_api_hash",
    "tg_session_string",
    "getgems_api_key",
    "portals_init_data",
    "mrkt_init_data",
    "tonnel_init_data",
    "gemini_api_key",
    "openai_api_key",
}


def mask_secret(value: str) -> str:
    """Return completely opaque masked representation — zero characters ever exposed."""
    if not value:
        return ""
    return "••••••••"


class RuntimeConfig:
    """Thread/async-safe runtime configuration overlay on top of env Settings."""

    def __init__(self, base: Settings) -> None:
        self.base = base
        self._overrides: dict[str, Any] = {}

    def apply_overrides(self, overrides: dict[str, Any]) -> None:
        for key, raw_val in overrides.items():
            if key not in SETTINGS_KEYS:
                continue
            _, expected_type = SETTINGS_KEYS[key]
            coerced = self._coerce(raw_val, expected_type)
            # Never overwrite an existing .env secret with an empty or masked value from DB/UI
            if key in SECRET_KEYS and (coerced == "" or "•" in str(coerced)):
                continue
            self._overrides[key] = coerced

    @staticmethod
    def _coerce(value: Any, target_type: type) -> Any:
        if target_type is bool:
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {"1", "true", "yes", "on"}
        if target_type is int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
        if target_type is float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0
        return "" if value is None else str(value).strip()

    def get(self, key: str) -> Any:
        if key in self._overrides:
            return self._overrides[key]
        env_attr, _ = SETTINGS_KEYS[key]
        return getattr(self.base, env_attr)

    def as_public_dict(self, bot_connected: bool = False, live_markets: list[str] | None = None) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for key in SETTINGS_KEYS:
            val = self.get(key)
            if key in SECRET_KEYS:
                data[key] = mask_secret(str(val))
                data[f"has_{key}"] = bool(val)
            else:
                data[key] = val
        data["bot_connected"] = bot_connected
        data["live_markets"] = live_markets or ["portals"]
        return data

    # Convenience properties
    @property
    def dry_run(self) -> bool:
        return bool(self.get("dry_run"))

    @property
    def daily_limit_ton(self) -> float:
        return float(self.get("daily_limit_ton"))

    @property
    def max_single_buy_ton(self) -> float:
        return float(self.get("max_single_buy_ton"))

    @property
    def stop_loss_percent(self) -> float:
        return float(self.get("stop_loss_percent"))

    @property
    def wallet_address(self) -> str:
        return str(self.get("wallet_address"))

    @property
    def tg_bot_token(self) -> str:
        return str(self.get("tg_bot_token"))

    @property
    def tg_admin_chat_id(self) -> str:
        return str(self.get("tg_admin_chat_id"))

    @property
    def webapp_url(self) -> str:
        return str(self.get("webapp_url")) or "https://t.me"

    @property
    def tg_api_id(self) -> int:
        try:
            return int(self.get("tg_api_id") or 0)
        except (TypeError, ValueError):
            return 0

    @property
    def tg_api_hash(self) -> str:
        return str(self.get("tg_api_hash") or "")

    @property
    def tg_session_string(self) -> str:
        return str(self.get("tg_session_string") or "")

    @property
    def getgems_api_key(self) -> str:
        return str(self.get("getgems_api_key"))

    @property
    def portals_init_data(self) -> str:
        return str(self.get("portals_init_data"))

    @property
    def mrkt_init_data(self) -> str:
        return str(self.get("mrkt_init_data"))

    @property
    def tonnel_init_data(self) -> str:
        return str(self.get("tonnel_init_data"))

    @property
    def gemini_api_key(self) -> str:
        return str(self.get("gemini_api_key"))

    @property
    def openai_api_key(self) -> str:
        return str(self.get("openai_api_key"))


base_settings = Settings()
runtime_config = RuntimeConfig(base_settings)
