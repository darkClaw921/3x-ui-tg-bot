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

    # Wallet
    # CSV of Stars amounts offered as one-tap top-up buttons on the «👛 Кошелёк»
    # screen, e.g. "50,100,250,500". Parsed from a CSV string the same way as
    # ``ADMIN_IDS`` (see ``_parse_csv_ints``). Empty → no preset buttons.
    WALLET_TOPUP_PRESETS: Annotated[list[int], NoDecode] = Field(
        default_factory=lambda: [50, 100, 250, 500],
        description="List of Stars top-up preset amounts (parsed from CSV string).",
    )

    # Growth — trial / referrals (Phase 3)
    # Length of the free trial subscription in days. ``0`` disables the trial
    # feature entirely (the «🎁 Пробный период» button is hidden and the router
    # rejects activation). Any positive value enables a one-per-user trial.
    TRIAL_DAYS: int = Field(
        default=0,
        ge=0,
        description="Free-trial length in days (0 = trial disabled).",
    )
    # Per-client traffic limit (GB) granted to a trial subscription, forwarded
    # to the 3x-ui panel as ``totalGB``. ``0`` means unlimited (xui semantics).
    TRIAL_TRAFFIC_GB: int = Field(
        default=0,
        ge=0,
        description="Trial subscription traffic limit in GB (0 = unlimited).",
    )
    # Stars credited to a referrer's wallet after the user they invited makes
    # their first payment. ``0`` disables the referral reward (referrals are
    # still tracked but no bonus is paid).
    REFERRAL_BONUS_STARS: int = Field(
        default=0,
        ge=0,
        description="Stars bonus credited to the referrer (0 = disabled).",
    )

    # Retention — auto-renewal / traffic alerts (Phase 4)
    # Master switch for the auto-renewal feature. When ``False`` the
    # «🔁 Подписка (автопродление)» button is hidden, the «⏹ Отменить
    # автопродление» control is not offered and the wallet-fallback
    # ``auto_renew_job`` short-circuits without charging anyone (native Star
    # subscriptions already in flight are still honoured by Telegram). When
    # ``True`` all three mechanisms (native Star subscriptions, the
    # «Продлить в 1 тап» reminder button and the wallet fallback) are active.
    AUTO_RENEW_ENABLED: bool = Field(
        default=True,
        description="Enable auto-renewal (native Star subs + wallet fallback).",
    )
    # Cumulative-traffic alert threshold as a percentage of the plan's
    # ``traffic_gb`` quota. When a subscription's ``up+down`` crosses this
    # share of its quota, ``traffic_snapshot_job`` sends a one-off alert
    # (deduplicated via ``subscription_notifications`` kind ``'traffic80'``).
    # ``0`` disables traffic alerts; plans with unlimited traffic
    # (``traffic_gb=0``) never alert regardless of this value.
    TRAFFIC_ALERT_PERCENT: int = Field(
        default=80,
        ge=0,
        le=100,
        description="Traffic-usage alert threshold (% of plan quota; 0 = off).",
    )
    # Plan length (days) that qualifies for a native Telegram Star
    # subscription. Telegram bills recurring Star subscriptions on a fixed
    # 30-day period (``billing.SUBSCRIPTION_PERIOD_SECONDS``), so only plans
    # whose ``days`` equals this value surface the «🔁 Подписка
    # (автопродление)» button on the confirm card.
    STAR_SUBSCRIPTION_PLAN_DAYS: int = Field(
        default=30,
        gt=0,
        description="Plan length (days) eligible for native Star subscriptions.",
    )

    # Support tickets (Phase 5)
    # Optional Telegram chat id to relay new support tickets / user follow-ups
    # to. When set (a group / channel id, typically negative), the bot forwards
    # every new ticket message there in addition to DM-ing each admin; when 0
    # (the default) only the ``ADMIN_IDS`` admins are notified by DM. Lets a
    # team triage tickets in a shared chat instead of individual DMs.
    SUPPORT_CHAT_ID: int = Field(
        default=0,
        description="Chat id to relay support tickets to (0 = DM admins only).",
    )

    # Localization
    DEFAULT_LANGUAGE: str = Field(
        default="ru",
        description=(
            "Fallback UI language for new users whose Telegram language_code "
            "is unknown/unsupported. One of app.i18n.SUPPORTED_LANGS."
        ),
    )

    # Observability
    LOG_LEVEL: str = Field(default="INFO", description="Loguru log level.")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("ADMIN_IDS", "WALLET_TOPUP_PRESETS", mode="before")
    @classmethod
    def _parse_csv_ints(cls, value: Any) -> Any:
        """Parse a CSV string like "1,2,3" (or a JSON array) into ``list[int]``.

        Shared by ``ADMIN_IDS`` and ``WALLET_TOPUP_PRESETS``. An empty / ``None``
        value yields an empty list; whitespace around items is ignored; a real
        ``list`` is returned untouched (so ``default_factory`` values pass
        through). A bracketed string is decoded as a JSON array.
        """
        if value is None or value == "":
            return []
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                parsed = json.loads(stripped)
                if not isinstance(parsed, list):
                    raise ValueError("value JSON must be an array")
                return [int(x) for x in parsed]
            return [int(part.strip()) for part in stripped.split(",") if part.strip()]
        return value


settings = Settings()  # type: ignore[call-arg]
