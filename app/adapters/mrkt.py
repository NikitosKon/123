"""MRKT adapter — @mrkt Telegram-бот, сайт mrkt.land.

Стабильного документированного публичного API для чтения листингов нет.
Адаптер — честная заглушка в статусе disabled. Включить при появлении
официального публичного API.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from app.adapters.base import MarketplaceAdapter
from app.domain.enums import Marketplace, SourceStatus
from app.domain.models import NormalizedListing


class MrktAdapter(MarketplaceAdapter):
    marketplace = Marketplace.MRKT

    def __init__(self, enabled: bool = False) -> None:  # noqa: ARG002
        super().__init__()
        self.status = SourceStatus.DISABLED
        self.disabled_reason = (
            "MRKT работает только через Telegram-бота @mrkt; публичного "
            "документированного API листингов нет. Автоматическое чтение "
            "невозможно без нарушения ToS — адаптер отключён."
        )

    async def health_check(self) -> SourceStatus:
        return self.status

    async def fetch_new_listings(self, since: datetime | None = None) -> list[NormalizedListing]:
        return []

    async def fetch_listing_details(self, listing_id: str) -> NormalizedListing | None:
        return None

    async def fetch_active_listings(
        self, gift_name: str | None = None, limit: int = 30
    ) -> list[NormalizedListing]:
        return []

    def normalize_listing(self, raw: dict[str, Any]) -> NormalizedListing | None:
        return None

    def get_marketplace_fee(self) -> Decimal:
        return Decimal("0")  # заявленные 0% fee

    def build_listing_url(self, listing: NormalizedListing) -> str:
        return "https://t.me/mrkt"
