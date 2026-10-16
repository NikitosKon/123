"""Application configuration via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = ""
    database_url: str = "postgresql+asyncpg://user:password@postgres:5432/gifts"
    redis_url: str = "redis://redis:6379/0"
    admin_ids: str = ""
    port: int = Field(default=8080, ge=1, le=65535)

    poll_interval_seconds: int = 15
    default_min_profit_ton: float = 0.2
    default_min_roi: float = 10.0
    max_listing_age_seconds: int = 120
    ton_price_provider: str = ""
    ton_usd_rate_cache_seconds: int = 60

    enable_telegram_native: bool = False
    enable_fragment: bool = False
    enable_getgems: bool = False
    enable_portals: bool = False
    enable_tonnel: bool = False
    enable_mrkt: bool = False
    enable_thermos: bool = False

    portals_auth_data: str = ""
    tonnel_auth_data: str = ""
    thermos_api_token: str = ""
    tonapi_key: str = ""

    default_slippage_reserve_ton: float = 0.05
    network_fee_ton: float = 0.05
    telegram_transfer_fee_ton: float = 0.03

    card_font_path: str = "assets/fonts/Inter-Regular.ttf"
    card_font_bold_path: str = "assets/fonts/Inter-Bold.ttf"
    card_cache_dir: str = ".cache/cards"
    image_cache_dir: str = ".cache/images"

    http_timeout_seconds: float = 20.0
    http_max_retries: int = 3

    @property
    def admin_id_list(self) -> list[int]:
        return [int(x) for x in self.admin_ids.split(",") if x.strip().isdigit()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
