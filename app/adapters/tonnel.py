"""Tonnel Market adapter — https://market.tonnel.network

Публичное чтение листингов: POST https://gifts2.tonnel.network/api/pageGifts
Использует ту же схему запросов, что официальный web-клиент:
TLS-impersonation (curl_cffi) + заголовки x-ts/x-wtf (зашифрованный timestamp).
Это НЕ обход защиты — схема идентична браузерному клиенту Tonnel.
Из datacenter-сетей Cloudflare может отвечать 403 → адаптер переходит в degraded.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Any

from Crypto.Cipher import AES  # type: ignore
from Crypto.Random import get_random_bytes  # type: ignore
from Crypto.Util.Padding import pad  # type: ignore
from curl_cffi import requests as creq  # type: ignore

from app.adapters.base import MarketplaceAdapter, parse_dt, to_decimal
from app.domain.enums import Currency, Marketplace, SourceStatus
from app.domain.models import NormalizedListing

log = logging.getLogger(__name__)

API = "https://gifts2.tonnel.network/api"
_WTF_PASSWORD = b"yowtfisthispieceofshitiiit"  # из JS-бандла официального клиента

SORTS = {
    "price_asc": '{"price":1,"gift_id":-1}',
    "price_desc": '{"price":-1,"gift_id":-1}',
    "latest": '{"message_post_time":-1,"gift_id":-1}',
    "mint_time": '{"export_at":1,"gift_id":-1}',
    "rarity": '{"rarity":-1,"gift_id":-1}',
}


def _evp(password: bytes, salt: bytes, key_len: int = 32, iv_len: int = 16) -> tuple[bytes, bytes]:
    dtot, prev = b"", b""
    while len(dtot) < key_len + iv_len:
        prev = hashlib.md5(prev + password + salt).digest()  # noqa: S324 — схема источника
        dtot += prev
    return dtot[:key_len], dtot[key_len : key_len + iv_len]


def _wtf_headers() -> dict[str, str]:
    ts = str(int(time.time()))
    salt = get_random_bytes(8)
    key, iv = _evp(_WTF_PASSWORD, salt)
    ct = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(ts.encode(), AES.block_size))
    return {"x-ts": ts, "x-wtf": base64.b64encode(b"Salted__" + salt + ct).decode()}


def _split_rarity(value: str) -> tuple[str, Decimal | None]:
    """'Hoverboard (3%)' -> ('Hoverboard', Decimal('3'))."""
    if "(" in value and value.rstrip().endswith("%)"):
        name, _, tail = value.rpartition("(")
        return name.strip(), to_decimal(tail.rstrip("%)").strip())
    return value.strip(), None


class TonnelAdapter(MarketplaceAdapter):
    marketplace = Marketplace.TONNEL

    def __init__(self, auth_data: str = "", enabled: bool = False) -> None:
        super().__init__()
        self.auth_data = auth_data
        self.status = SourceStatus.LIVE if enabled else SourceStatus.DISABLED
        self.disabled_reason = "" if enabled else "disabled via ENABLE_TONNEL=false"

    # -- low-level ---------------------------------------------------------
    def _post_sync(self, path: str, payload: dict[str, Any]) -> Any:
        headers = {
            "content-type": "application/json",
            "origin": "https://market.tonnel.network",
            "referer": "https://market.tonnel.network/",
            **_wtf_headers(),
        }
        r = creq.post(
            f"{API}{path}", headers=headers, json=payload, impersonate="chrome", timeout=25
        )
        r.raise_for_status()
        return r.json()

    async def _post(self, path: str, payload: dict[str, Any]) -> Any:
        import asyncio

        started = time.perf_counter()
        try:
            data = await asyncio.to_thread(self._post_sync, path, payload)
        except Exception as exc:  # noqa: BLE001
            self._mark_error(exc)
            raise
        self._mark_ok((time.perf_counter() - started) * 1000)
        return data

    # -- interface ---------------------------------------------------------
    async def health_check(self) -> SourceStatus:
        try:
            await self._post("/pageGifts", self._gifts_payload(limit=1))
            return self.status
        except Exception as exc:  # noqa: BLE001 — health endpoint не должен падать
            log.debug("Tonnel health check failed: %s", exc)
            return self.status

    def _gifts_payload(
        self,
        gift_name: str | None = None,
        page: int = 1,
        limit: int = 30,
        sort: str = "latest",
    ) -> dict[str, Any]:
        filter_dict: dict[str, Any] = {
            "price": {"$exists": True},
            "buyer": {"$exists": False},
            "asset": "TON",
            "refunded": {"$ne": True},
            "export_at": {"$exists": True},
        }
        if gift_name:
            filter_dict["gift_name"] = gift_name.strip().title()
        return {
            "filter": json.dumps(filter_dict),
            "limit": min(limit, 30),
            "page": page,
            "sort": SORTS.get(sort, SORTS["latest"]),
            "ref": 0,
            "user_auth": self.auth_data,
        }

    async def fetch_new_listings(self, since: datetime | None = None) -> list[NormalizedListing]:
        data = await self._post("/pageGifts", self._gifts_payload(sort="latest"))
        items = data if isinstance(data, list) else data.get("data", [])
        out = []
        for raw in items:
            lst = self.normalize_listing(raw)
            if lst and (since is None or (lst.listed_at or lst.fetched_at) >= since):
                out.append(lst)
        return out

    async def fetch_active_listings(
        self, gift_name: str | None = None, limit: int = 30
    ) -> list[NormalizedListing]:
        data = await self._post(
            "/pageGifts", self._gifts_payload(gift_name=gift_name, limit=limit, sort="price_asc")
        )
        items = data if isinstance(data, list) else data.get("data", [])
        return [x for x in (self.normalize_listing(i) for i in items) if x]

    async def fetch_listing_details(self, listing_id: str) -> NormalizedListing | None:
        data = await self._post("/giftData", {"gift_id": int(listing_id), "user_auth": self.auth_data})
        if isinstance(data, dict) and data.get("status") == "success":
            return self.normalize_listing(data.get("data", {}))
        return None

    async def fetch_sales_history(self, gift_name: str, limit: int = 50) -> list[dict[str, Any]]:
        if not self.auth_data:
            return []
        data = await self._post(
            "/saleHistory",
            {
                "filter": json.dumps({"gift_name": gift_name.strip().title()}),
                "limit": min(limit, 50),
                "page": 1,
                "sort": '{"created_at":-1}',
                "type": "ALL",
                "user_auth": self.auth_data,
            },
        )
        return data if isinstance(data, list) else data.get("data", [])

    async def fetch_floor_stats(self) -> dict[str, Any]:
        """filterStats — floor по всем моделям (требует authData)."""
        if not self.auth_data:
            return {}
        data = await self._post("/filterStats", {"user_auth": self.auth_data})
        return data.get("data", {}) if isinstance(data, dict) else {}

    def normalize_listing(self, raw: dict[str, Any]) -> NormalizedListing | None:
        if not isinstance(raw, dict) or raw.get("price") is None:
            return None
        price = to_decimal(raw.get("price"))
        if price is None:
            return None
        model, model_r = _split_rarity(str(raw.get("model") or ""))
        backdrop, back_r = _split_rarity(str(raw.get("backdrop") or ""))
        symbol, sym_r = _split_rarity(str(raw.get("symbol") or ""))
        asset = str(raw.get("asset") or "TON").upper()
        listing = NormalizedListing(
            marketplace=self.marketplace,
            listing_id=str(raw.get("gift_id") or raw.get("_id") or ""),
            gift_name=str(raw.get("name") or ""),
            gift_num=int(raw["gift_num"]) if raw.get("gift_num") else None,
            telegram_gift_id=str(raw.get("gift_num") or ""),
            custom_emoji_id=str(raw.get("customEmojiId") or ""),
            model=model,
            model_rarity_pct=model_r,
            backdrop=backdrop,
            backdrop_rarity_pct=back_r,
            symbol=symbol,
            symbol_rarity_pct=sym_r,
            price=price,  # raw price БЕЗ наценки Tonnel 10%
            currency=Currency.TON if asset == "TON" else Currency.USDT,
            marketplace_fee_pct=Decimal("10"),  # +10% к цене при покупке
            availability_issued=raw.get("availabilityIssued") or None,
            availability_total=raw.get("availabilityTotal") or None,
            transferable=not raw.get("limited", False),
            listed_at=parse_dt(raw.get("message_post_time")),
            updated_at=parse_dt(raw.get("export_at")),
            is_active=raw.get("status") == "forsale",
            is_auction=raw.get("auction") is not None,
            raw=raw,
        )
        listing.url = self.build_listing_url(listing)
        return listing

    def get_marketplace_fee(self) -> Decimal:
        return Decimal("0.10")

    def build_listing_url(self, listing: NormalizedListing) -> str:
        return f"https://market.tonnel.network/?gift={listing.listing_id}"
