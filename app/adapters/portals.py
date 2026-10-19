"""Portals adapter — https://portals-market.com (Telegram mini-app).

Публичного неавторизованного API нет: чтение листингов требует authData
(initData из mini-app). Адаптер реализован; без PORTALS_AUTH_DATA — not_configured.
Fee ~6–7%.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import httpx

from app.adapters.base import MarketplaceAdapter, to_decimal
from app.domain.enums import Currency, Marketplace, SourceStatus
from app.domain.models import NormalizedListing
from app.domain.traits import trait_text

log = logging.getLogger(__name__)

API = "https://portals-market.com/api"


class PortalsAdapter(MarketplaceAdapter):
    marketplace = Marketplace.PORTALS

    def __init__(self, auth_data: str = "", enabled: bool = False) -> None:
        super().__init__()
        self.auth_data = auth_data
        if not enabled:
            self.status = SourceStatus.DISABLED
            self.disabled_reason = "disabled via ENABLE_PORTALS=false"
        elif not auth_data:
            self.status = SourceStatus.NOT_CONFIGURED
            self.disabled_reason = (
                "Portals требует authData из mini-app (initData). "
                "Задайте PORTALS_AUTH_DATA в .env"
            )
        else:
            self.status = SourceStatus.LIVE

    def _headers(self) -> dict[str, str]:
        return {"authorization": f"tma {self.auth_data}", "content-type": "application/json"}

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(f"{API}{path}", headers=self._headers(), params=params)
            r.raise_for_status()
            self._mark_ok((time.perf_counter() - started) * 1000)
            return r.json()
        except Exception as exc:  # noqa: BLE001
            self._mark_error(exc)
            raise

    async def health_check(self) -> SourceStatus:
        if self.status in (SourceStatus.DISABLED, SourceStatus.NOT_CONFIGURED):
            return self.status
        try:
            await self._get("/nfts/search", {"limit": 1, "offset": 0})
        except Exception as exc:  # noqa: BLE001 — health endpoint не должен падать
            log.debug("Portals health check failed: %s", exc)
        return self.status

    async def fetch_new_listings(self, since: datetime | None = None) -> list[NormalizedListing]:
        if self.status != SourceStatus.LIVE:
            return []
        data = await self._get(
            "/nfts/search", {"limit": 30, "offset": 0, "sort_by": "listed_at desc"}
        )
        return [x for x in (self.normalize_listing(i) for i in data.get("results", [])) if x]

    async def fetch_active_listings(
        self, gift_name: str | None = None, limit: int = 30
    ) -> list[NormalizedListing]:
        if self.status != SourceStatus.LIVE:
            return []
        params: dict[str, Any] = {"limit": min(limit, 50), "offset": 0, "sort_by": "price asc"}
        if gift_name:
            params["collections"] = gift_name
        data = await self._get("/nfts/search", params)
        return [x for x in (self.normalize_listing(i) for i in data.get("results", [])) if x]

    async def fetch_listing_details(self, listing_id: str) -> NormalizedListing | None:
        if self.status != SourceStatus.LIVE:
            return None
        data = await self._get(f"/nfts/{listing_id}")
        return self.normalize_listing(data)

    def normalize_listing(self, raw: dict[str, Any]) -> NormalizedListing | None:
        if not isinstance(raw, dict):
            return None
        price = to_decimal(raw.get("price"))
        if price is None:
            return None
        raw_attributes = raw.get("attributes") or []
        if isinstance(raw_attributes, dict):
            attrs = {str(key).casefold(): value for key, value in raw_attributes.items()}
        else:
            attrs = {
                str(a.get("type") or a.get("trait_type") or a.get("traitType") or "").casefold(): a.get("value")
                for a in raw_attributes
                if isinstance(a, dict)
            }

        collection = raw.get("collection")
        if isinstance(collection, dict):
            collection = collection.get("name") or collection.get("title")
        name_candidates = [collection, raw.get("gift_name"), raw.get("name"), raw.get("title")]
        name_value = next((value for value in name_candidates if value), "")
        name_text = str(name_value).strip()
        name_match = re.match(r"^(?P<gift>.+?)\s*#\s*(?P<number>\d+)\s*$", name_text)
        gift_name = (name_match.group("gift") if name_match else name_text).strip()
        number_value = next(
            (raw.get(key) for key in ("num", "gift_num", "number", "gift_number", "giftNumber") if raw.get(key) is not None),
            None,
        )
        gift_num = self._parse_gift_number(number_value)
        if gift_num is None:
            for candidate in name_candidates:
                candidate_match = re.search(r"#\s*(\d+)\s*$", str(candidate or ""))
                if candidate_match:
                    gift_num = int(candidate_match.group(1))
                    break
        if not gift_name:
            return None

        listing_id = str(raw.get("id") or raw.get("nft_id") or raw.get("address") or "")
        if not listing_id:
            return None
        status = str(raw.get("status") or "listed").casefold()
        listing = NormalizedListing(
            marketplace=self.marketplace,
            listing_id=listing_id,
            gift_name=gift_name,
            gift_num=gift_num,
            model=trait_text(attrs.get("model") or ""),
            backdrop=attrs.get("backdrop") or "",
            symbol=trait_text(attrs.get("symbol") or ""),
            image_url=str(raw.get("photo_url") or ""),
            animation_url=str(raw.get("animation_url") or ""),
            price=price,
            currency=Currency.TON,
            marketplace_fee_pct=Decimal("6.5"),
            transferable=True,
            is_active=status in {"listed", "forsale", "for_sale", "on_sale", "active"},
            raw=raw,
        )
        listing.url = self.build_listing_url(listing)
        return listing

    @staticmethod
    def _parse_gift_number(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, float) and value.is_integer() and value > 0:
            return int(value)
        if isinstance(value, str) and value.strip().isdigit() and int(value.strip()) > 0:
            return int(value.strip())
        return None

    def get_marketplace_fee(self) -> Decimal:
        return Decimal("0.065")

    def build_listing_url(self, listing: NormalizedListing) -> str:
        return f"https://t.me/portals/market?startapp=gift_{quote(listing.listing_id, safe='')}"
