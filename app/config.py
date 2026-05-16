"""Application configuration loaded from environment / .env via pydantic-settings.

Exposes a singleton `settings` instance. Import as:

    from app.config import settings

Required env variables (see .env.example):
- BOT_TOKEN           — Telegram bot API token.
- ADMIN_IDS           — CSV of Telegram user IDs treated as administrators.
- XUI_BASE_URL        — Base URL of the 3x-ui panel (scheme+host+port, no trailing slash).
- XUI_USERNAME        — Login for the 3x-ui panel.
- XUI_PASSWORD        — Password for the 3x-ui panel.
- XUI_INBOUND_ID      — ID of the inbound where clients will be provisioned.
- XUI_SERVER_HOST     — Public host used inside generated vless:// links.
- XUI_SUB_BASE_URL    — Base URL serving subscription pages (e.g. https://.../sub).

Optional (with defaults):
- DB_PATH             — SQLite DB path. Default: ./data/bot.db
- LOG_LEVEL           — Loguru level. Default: INFO
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings sourced from .env / environment."""

    # Telegram
    BOT_TOKEN: str = Field(..., description="Telegram bot API token")
    # ``NoDecode`` disables pydantic-settings' default JSON decoding for
    # complex types so a plain CSV string ("1,2,3") reaches our field
    # validator below as-is instead of being rejected by ``json.loads``.
    ADMIN_IDS: Annotated[list[int], NoDecode] = Field(
        default_factory=list,
        description="List of admin Telegram user IDs (parsed from CSV string).",
    )

    # Storage
    DB_PATH: str = Field(
        default="./data/bot.db",
        description="Filesystem path to SQLite database.",
    )

    # 3x-ui panel
    XUI_BASE_URL: str = Field(..., description="3x-ui panel base URL (no trailing slash).")
    XUI_USERNAME: str = Field(..., description="3x-ui panel login.")
    XUI_PASSWORD: str = Field(..., description="3x-ui panel password.")
    XUI_INBOUND_ID: int = Field(..., description="ID of the inbound used for new clients.")
    XUI_SERVER_HOST: str = Field(..., description="Public host used in vless:// links.")
    XUI_SUB_BASE_URL: str = Field(..., description="Base URL serving subscription pages.")
    XUI_VERIFY_SSL: bool = Field(
        default=True,
        description="Verify TLS certificate of the 3x-ui panel. Set false for self-signed.",
    )

    # Observability
    LOG_LEVEL: str = Field(default="INFO", description="Loguru log level.")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def _parse_admin_ids(cls, value: Any) -> Any:
        """Allow ADMIN_IDS to be a CSV string like "1,2,3" or a real list/JSON array.

        Empty string yields an empty list. Whitespace around items is ignored.
        """
        if value is None or value == "":
            return []
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                parsed = json.loads(stripped)
                if not isinstance(parsed, list):
                    raise ValueError("ADMIN_IDS JSON must be an array")
                return [int(x) for x in parsed]
            return [int(part.strip()) for part in stripped.split(",") if part.strip()]
        return value


settings = Settings()  # type: ignore[call-arg]
