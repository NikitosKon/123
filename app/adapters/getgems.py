"""Getgems adapter using the official Read API.

Read API docs: https://api.getgems.io/public-api/docs
Telegram gift history supplies listing timestamps; NFT details and active
collection listings are loaded through the authenticated Read API.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import httpx

from app.adapters.base import MarketplaceAdapter, parse_dt, to_decimal
from app.domain.enums import Currency, Marketplace, SourceStatus
from app.domain.models import NormalizedListing

log = logging.getLogger(__name__)

API = "https://api.getgems.io/public-api/v1"
NANO = Decimal(10**9)
HISTORY_PAGE_SIZE = 100
MAX_HISTORY_PAGES = 3
ACTIVE_CACHE_SECONDS = 10


class GetgemsAdapter(MarketplaceAdapter):
    marketplace = Marketplace.GETGEMS

    def __init__(self, api_key: str = "", enabled: bool = False) -> None:
        super().__init__()
        self.api_key = api_key.strip()
        self._collections_by_gift: dict[str, set[tuple[str, bool]]] = {}
        self._active_cache: dict[str, tuple[float, list[NormalizedListing]]] = {}

        if not enabled:
            self.status = SourceStatus.DISABLED
            self.disabled_reason = "disabled via ENABLE_GETGEMS=false"
        elif not self.api_key:
            self.status = SourceStatus.NOT_CONFIGURED
            self.disabled_reason = "Getgems Read API key is missing; set GETGEMS_API_KEY"
        else:
            self.status = SourceStatus.LIVE
            self.disabled_reason = ""

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        headers = {"accept": "application/json", "authorization": self.api_key}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.request(
                method,
                f"{API}{path}",
                headers=headers,
                params=params,
                json=json_body,
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("success") is False:
            raise ValueError("Getgems Read API returned an unsuccessful response")
        return payload.get("response")

    async def health_check(self) -> SourceStatus:
        if self.status in (SourceStatus.DISABLED, SourceStatus.NOT_CONFIGURED):
            return self.status
        started = time.perf_counter()
        try:
            await self._request("GET", "/nfts/offchain/on-sale/gifts", params={"limit": 1})
            return self._mark_ok((time.perf_counter() - started) * 1000)
        except Exception as exc:  # noqa: BLE001 — health endpoint must not fail
            log.debug("Getgems health check failed: %s", exc)
            return self._mark_error(exc)

    async def fetch_new_listings(self, since: datetime | None = None) -> list[NormalizedListing]:
        if not self.api_key or self.status in (SourceStatus.DISABLED, SourceStatus.NOT_CONFIGURED):
            return []

        since_dt = self._as_utc(since) if since else datetime.now(timezone.utc) - timedelta(minutes=10)
        params: dict[str, Any] = {
            "minTime": int(since_dt.timestamp() * 1000),
            "limit": HISTORY_PAGE_SIZE,
            "types": "putUpForSale",
        }
        event_times: dict[str, datetime] = {}
        seen_cursors: set[str] = set()
        started = time.perf_counter()

        try:
            for _ in range(MAX_HISTORY_PAGES):
                page = await self._request("GET", "/nfts/history/gifts", params=params)
                if not isinstance(page, dict):
                    break
                events = page.get("items", [])
                if not isinstance(events, list) or not events:
                    break

                oldest_on_page: datetime | None = None
                for event in events:
                    if not isinstance(event, dict):
                        continue
                    type_data = event.get("typeData") or {}
                    if not isinstance(type_data, dict):
                        continue
                    if type_data.get("type") not in (None, "putUpForSale"):
                        continue
                    address = str(event.get("address") or "")
                    listed_at = self._event_time(event)
                    if not address or not listed_at or listed_at < since_dt:
                        continue
                    event_times[address] = max(event_times.get(address, listed_at), listed_at)
                    oldest_on_page = min(oldest_on_page, listed_at) if oldest_on_page else listed_at

                cursor = page.get("cursor")
                if not cursor or str(cursor) in seen_cursors or len(events) < HISTORY_PAGE_SIZE:
                    break
                if oldest_on_page and oldest_on_page <= since_dt:
                    break
                seen_cursors.add(str(cursor))
                params["after"] = str(cursor)

            listings: list[NormalizedListing] = []
            addresses = list(event_times)
            for offset in range(0, len(addresses), HISTORY_PAGE_SIZE):
                detail_response = await self._request(
                    "POST",
                    "/nfts/list",
                    json_body={"addressList": addresses[offset : offset + HISTORY_PAGE_SIZE]},
                )
                if not isinstance(detail_response, dict):
                    continue
                for raw in detail_response.get("items", []):
                    if not isinstance(raw, dict):
                        continue
                    listing = self.normalize_listing(raw)
                    listed_at = event_times.get(str(raw.get("address") or ""))
                    if not listing or listing.is_auction or not listed_at:
                        continue
                    listing.listed_at = listed_at
                    listing.updated_at = listed_at
                    self._remember_collection(listing, raw)
                    listings.append(listing)

            self._mark_ok((time.perf_counter() - started) * 1000)
            return listings
        except Exception as exc:  # noqa: BLE001 — worker keeps other sources alive
            self._mark_error(exc)
            raise

    async def fetch_active_listings(
        self, gift_name: str | None = None, limit: int = 30
    ) -> list[NormalizedListing]:
        if not self.api_key or self.status in (SourceStatus.DISABLED, SourceStatus.NOT_CONFIGURED):
            return []

        name_key = gift_name.strip().casefold() if gift_name else ""
        collections = sorted(self._collections_by_gift.get(name_key, set()))
        targets = collections or [("", True)]
        listings: list[NormalizedListing] = []
        started = time.perf_counter()

        try:
            for collection, offchain in targets:
                if collection:
                    encoded = quote(collection, safe="")
                    path = (
                        f"/nfts/offchain/on-sale/{encoded}"
                        if offchain
                        else f"/nfts/on-sale/{encoded}"
                    )
                else:
                    path = "/nfts/offchain/on-sale/gifts"

                cached = self._active_cache.get(path)
                if cached and cached[0] > time.monotonic():
                    page_items = cached[1]
                else:
                    response = await self._request(
                        "GET",
                        path,
                        params={"limit": min(max(limit, 1), HISTORY_PAGE_SIZE)},
                    )
                    page = response if isinstance(response, dict) else {}
                    raw_items = page.get("items", [])
                    page_items = [
                        listing
                        for raw in raw_items
                        if isinstance(raw, dict)
                        and (listing := self.normalize_listing(raw)) is not None
                        and not listing.is_auction
                    ]
                    self._active_cache[path] = (
                        time.monotonic() + ACTIVE_CACHE_SECONDS,
                        page_items,
                    )
                    for listing in page_items:
                        self._remember_collection(listing, listing.raw)

                listings.extend(
                    listing
                    for listing in page_items
                    if not name_key or listing.gift_name.casefold() == name_key
                )

            self._mark_ok((time.perf_counter() - started) * 1000)
            return listings
        except Exception as exc:  # noqa: BLE001
            self._mark_error(exc)
            raise

    async def fetch_listing_details(self, listing_id: str) -> NormalizedListing | None:
        if not self.api_key or self.status in (SourceStatus.DISABLED, SourceStatus.NOT_CONFIGURED):
            return None
        started = time.perf_counter()
        try:
            address = quote(str(listing_id), safe="")
            raw = await self._request("GET", f"/nft/{address}")
            if not isinstance(raw, dict):
                return None
            listing = self.normalize_listing(raw)
            if listing:
                self._remember_collection(listing, raw)
            self._mark_ok((time.perf_counter() - started) * 1000)
            return listing
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            self._mark_error(exc)
            raise
        except Exception as exc:  # noqa: BLE001
            self._mark_error(exc)
            raise

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @classmethod
    def _event_time(cls, event: dict[str, Any]) -> datetime | None:
        value = parse_dt(event.get("time"))
        if value is not None:
            return cls._as_utc(value)
        timestamp = to_decimal(event.get("timestamp"))
        if timestamp is None:
            return None
        try:
            # Getgems history timestamps are Unix seconds; minTime query uses milliseconds.
            return datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    def _remember_collection(self, listing: NormalizedListing, raw: dict[str, Any]) -> None:
        collection = str(raw.get("collectionAddress") or "")
        if not collection:
            return
        sale = raw.get("sale") or {}
        is_offchain = (
            raw.get("kind") in ("OffchainNft", "OffchainSticker")
            or sale.get("contractType") == "offchain"
        )
        key = listing.gift_name.casefold()
        self._collections_by_gift.setdefault(key, set()).add((collection, is_offchain))

    def normalize_listing(self, raw: dict[str, Any]) -> NormalizedListing | None:
        sale = raw.get("sale") or {}
        if not isinstance(sale, dict):
            return None

        sale_type = str(sale.get("type") or "")
        is_auction = sale_type == "Auction"
        raw_price = sale.get("minBid") if is_auction else sale.get("fullPrice")
        amount = to_decimal(raw_price)
        if amount is None or amount <= 0:
            return None

        currency_code = str(sale.get("currency") or "TON").upper()
        if currency_code not in (Currency.TON.value, Currency.GRAM.value):
            return None
        currency = Currency(currency_code)
        price = amount / NANO

        attributes = raw.get("attributes") or []
        attrs = {
            str(item.get("traitType") or item.get("trait_type") or "").casefold(): str(
                item.get("value") or ""
            )
            for item in attributes
            if isinstance(item, dict)
        }
        name = str(raw.get("name") or attrs.get("gift") or "").strip()
        match = re.match(r"^(?P<gift>.+?)\s*#\s*(?P<number>\d+)$", name)
        gift_name = match.group("gift").strip() if match else name
        gift_num = int(match.group("number")) if match else None
        if not gift_name:
            return None

        address = str(raw.get("address") or "")
        if not address:
            return None

        marketplace_fee_pct = to_decimal(sale.get("marketplaceFeePercent"))
        if marketplace_fee_pct is None:
            marketplace_fee_pct = Decimal("2")

        listing = NormalizedListing(
            marketplace=self.marketplace,
            listing_id=address,
            gift_name=gift_name,
            gift_num=gift_num,
            model=attrs.get("model", ""),
            backdrop=attrs.get("backdrop", ""),
            symbol=attrs.get("symbol", ""),
            ton_contract=str(raw.get("collectionAddress") or ""),
            ton_token_id=address,
            image_url=str(raw.get("image") or ""),
            price=price,
            price_ton=price,
            currency=currency,
            marketplace_fee_pct=marketplace_fee_pct,
            transferable=True,
            is_active=True,
            is_auction=is_auction,
            raw=raw,
        )
        listing.url = self.build_listing_url(listing)
        return listing

    def get_marketplace_fee(self) -> Decimal:
        return Decimal("0.02")

    def build_listing_url(self, listing: NormalizedListing) -> str:
        raw = listing.raw
        address = str(raw.get("address") or listing.listing_id)
        collection = str(raw.get("collectionAddress") or listing.ton_contract)
        if collection:
            return f"https://getgems.io/collection/{quote(collection, safe='')}/{quote(address, safe='')}"
        return f"https://getgems.io/nft/{quote(address, safe='')}"
