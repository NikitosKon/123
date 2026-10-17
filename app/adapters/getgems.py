"""Getgems adapter — публичный GraphQL API.

Endpoint: https://api.getgems.io/graphql
Чтение публичное; CloudFront может блокировать datacenter IP (403) → degraded.
Fee по Telegram gifts ~2%.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

from app.adapters.base import MarketplaceAdapter, parse_dt, to_decimal, utcnow
from app.domain.enums import Currency, Marketplace, SourceStatus
from app.domain.models import NormalizedListing

log = logging.getLogger(__name__)

GQL = "https://api.getgems.io/graphql"

LISTINGS_QUERY = """
query NftItems($collection: String!, $limit: Int!) {
  nftItemsOnSale(collectionAddress: $collection, first: $limit) {
    items {
      address
      name
      sale { price { tokenName amount } }
      attributes { traitType value }
    }
  }
}
"""


class GetgemsAdapter(MarketplaceAdapter):
    marketplace = Marketplace.GETGEMS

    def __init__(self, enabled: bool = False) -> None:
        super().__init__()
        self.status = SourceStatus.LIVE if enabled else SourceStatus.DISABLED
        self.disabled_reason = "" if enabled else "disabled via ENABLE_GETGEMS=false"

    async def _query(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(GQL, json={"query": query, "variables": variables})
            r.raise_for_status()
            self._mark_ok((time.perf_counter() - started) * 1000)
            return r.json()
        except Exception as exc:  # noqa: BLE001
            self._mark_error(exc)
            raise

    async def health_check(self) -> SourceStatus:
        try:
            await self._query("{ __typename }", {})
        except Exception as exc:  # noqa: BLE001 — health endpoint не должен падать
            log.debug("Getgems health check failed: %s", exc)
        return self.status

    async def fetch_new_listings(self, since: datetime | None = None) -> list[NormalizedListing]:
        # Getgems не имеет единого "new gifts" feed по всем коллекциям без адресов коллекций.
        # Адреса коллекций подарков нужно подложить в конфиг; MVP не скрапит каталог.
        return []

    async def fetch_active_listings(
        self, gift_name: str | None = None, limit: int = 30
    ) -> list[NormalizedListing]:
        return []

    async def fetch_listing_details(self, listing_id: str) -> NormalizedListing | None:
        return None

    def normalize_listing(self, raw: dict[str, Any]) -> NormalizedListing | None:
        sale = (raw.get("sale") or {}).get("price") or {}
        price = to_decimal(sale.get("amount"))
        if price is None:
            return None
        attrs = {a.get("traitType"): a.get("value") for a in raw.get("attributes", [])}
        return NormalizedListing(
            marketplace=self.marketplace,
            listing_id=str(raw.get("address") or ""),
            gift_name=str(raw.get("name") or "").split("#")[0].strip(),
            model=str(attrs.get("Model") or ""),
            backdrop=str(attrs.get("Backdrop") or ""),
            symbol=str(attrs.get("Symbol") or ""),
            ton_contract=str(raw.get("address") or ""),
            price=price / Decimal(10**9),  # nanotons -> TON
            currency=Currency.TON,
            marketplace_fee_pct=Decimal("2"),
            updated_at=parse_dt(raw.get("updatedAt")) or utcnow(),
            is_active=True,
            raw=raw,
        )

    def get_marketplace_fee(self) -> Decimal:
        return Decimal("0.02")

    def build_listing_url(self, listing: NormalizedListing) -> str:
        return f"https://getgems.io/nft/{listing.ton_contract or listing.listing_id}"
