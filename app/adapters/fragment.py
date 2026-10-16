"""Fragment adapter.

Публичного API листингов у Fragment нет (SPA + Telegram login + KYC).
Легально доступен NFT-metadata CDN для заминченных подарков:
    https://nft.fragment.com/gift/{slug}-{num}.json  -> metadata, image(.webp), lottie
Адаптер используется как источник метаданных/изображений, не листингов.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

from app.adapters.base import MarketplaceAdapter, to_decimal, utcnow
from app.domain.enums import Marketplace, SourceStatus
from app.domain.models import NormalizedListing

CDN = "https://nft.fragment.com/gift"


def slugify(gift_name: str) -> str:
    return gift_name.lower().replace("'", "").replace(" ", "")


class FragmentAdapter(MarketplaceAdapter):
    marketplace = Marketplace.FRAGMENT

    def __init__(self, enabled: bool = False) -> None:
        super().__init__()
        self.status = SourceStatus.DEGRADED if enabled else SourceStatus.DISABLED
        self.disabled_reason = (
            "Fragment не предоставляет публичный API листингов подарков. "
            "Используется только NFT-metadata CDN (изображения/атрибуты)."
        )

    async def health_check(self) -> SourceStatus:
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(f"{CDN}/plushpepe-1.json")
            if r.status_code == 200:
                self.last_ok_at = utcnow()
                return self.status
            return self._mark_error(f"CDN status {r.status_code}")
        except Exception as exc:  # noqa: BLE001
            return self._mark_error(exc)

    async def fetch_metadata(self, gift_name: str, num: int) -> dict[str, Any] | None:
        """Метаданные заминченного NFT-подарка (None, если не заминчен)."""
        url = f"{CDN}/{slugify(gift_name)}-{num}.json"
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url)
        if r.status_code != 200:
            return None
        return r.json()

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
        return Decimal("0.05")  # ~5% на продажах Fragment

    def build_listing_url(self, listing: NormalizedListing) -> str:
        if listing.gift_num:
            return f"https://t.me/nft/{slugify(listing.gift_name).title()}-{listing.gift_num}"
        return "https://fragment.com/gifts"


class FragmentMetadataService:
    """Отдельный лёгкий клиент CDN для изображений (используется в services/images)."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=20)

    async def metadata(self, gift_name: str, num: int) -> dict[str, Any] | None:
        r = await self._client.get(f"{CDN}/{slugify(gift_name)}-{num}.json")
        return r.json() if r.status_code == 200 else None

    async def image_url(self, gift_name: str, num: int) -> str | None:
        meta = await self.metadata(gift_name, num)
        return meta.get("image") if meta else None

    def price_hint(self, v: Any) -> Decimal | None:
        return to_decimal(v)
