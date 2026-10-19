"""Базовый интерфейс адаптера маркетплейса."""
from __future__ import annotations

import abc
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.enums import Marketplace, SourceStatus
from app.domain.models import NormalizedListing, RecentSale

log = logging.getLogger(__name__)


def to_decimal(value: Any, default: Decimal | None = None) -> Decimal | None:
    """Безопасная конвертация в Decimal (деньги — только Decimal)."""
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MarketplaceAdapter(abc.ABC):
    """Общий интерфейс источника данных."""

    marketplace: Marketplace
    disabled_reason: str = ""

    def __init__(self) -> None:
        self.status: SourceStatus = SourceStatus.NOT_CONFIGURED
        self.last_ok_at: datetime | None = None
        self.last_error: str = ""
        self.latency_ms: float | None = None
        self.errors_total: int = 0

    # -- interface ---------------------------------------------------------
    @abc.abstractmethod
    async def health_check(self) -> SourceStatus: ...

    @abc.abstractmethod
    async def fetch_new_listings(self, since: datetime | None = None) -> list[NormalizedListing]: ...

    @abc.abstractmethod
    async def fetch_listing_details(self, listing_id: str) -> NormalizedListing | None: ...

    @abc.abstractmethod
    async def fetch_active_listings(self, gift_name: str | None = None, limit: int = 30) -> list[NormalizedListing]: ...

    async def fetch_sales_history(self, gift_name: str, limit: int = 50) -> list[dict[str, Any]]:
        return []

    async def fetch_recent_sales(
        self, gift_name: str, model: str, since: datetime, limit: int = 50
    ) -> list[RecentSale]:
        """Фактические продажи exact gift/model; площадки без API возвращают []."""
        return []

    @abc.abstractmethod
    def normalize_listing(self, raw: dict[str, Any]) -> NormalizedListing | None: ...

    @abc.abstractmethod
    def get_marketplace_fee(self) -> Decimal:
        """Комиссия площадки в долях (0.10 = 10%)."""

    @abc.abstractmethod
    def build_listing_url(self, listing: NormalizedListing) -> str: ...

    # -- helpers -----------------------------------------------------------
    def _mark_ok(self, latency_ms: float) -> SourceStatus:
        self.status = SourceStatus.LIVE
        self.last_ok_at = utcnow()
        self.latency_ms = latency_ms
        return self.status

    def _mark_error(self, exc: BaseException | str, degraded: bool = True) -> SourceStatus:
        self.errors_total += 1
        self.last_error = str(exc)[:500]
        self.status = SourceStatus.DEGRADED if degraded else SourceStatus.DISABLED
        log.warning("[%s] error: %s", self.marketplace.value, self.last_error)
        return self.status

    async def _retry(self, func, *, attempts: int = 3, base_delay: float = 0.8):
        """Retry с exponential backoff."""
        delay = base_delay
        for i in range(attempts):
            try:
                return await func()
            except Exception:
                if i == attempts - 1:
                    raise
                await asyncio.sleep(delay)
                delay *= 2
        return None
