"""Конвертация валют. TON ≡ GRAM (ребрендинг 2026, 1:1). STARS — отдельно."""
from __future__ import annotations

import time
from decimal import Decimal

import httpx

from app.domain.enums import Currency

# STARS не конвертируем автоматически — нет надёжного курса; показываем отдельно.
_NON_CONVERTIBLE = {Currency.STARS}


class CurrencyConverter:
    def __init__(self, provider_url: str = "", cache_seconds: int = 60) -> None:
        self.provider_url = provider_url
        self.cache_seconds = cache_seconds
        self._ton_usd: Decimal | None = None
        self._cached_at: float = 0.0

    async def ton_usd_rate(self) -> Decimal | None:
        if self._ton_usd and time.time() - self._cached_at < self.cache_seconds:
            return self._ton_usd
        if not self.provider_url:
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(self.provider_url)
            r.raise_for_status()
            data = r.json()
            # поддержка coingecko-подобного ответа
            rate = data.get("the-open-network", {}).get("usd") or data.get("usd")
            if rate:
                self._ton_usd = Decimal(str(rate))
                self._cached_at = time.time()
        except Exception:  # noqa: BLE001,S110
            pass
        return self._ton_usd

    def to_ton(self, amount: Decimal, currency: Currency) -> Decimal | None:
        if currency in (Currency.TON, Currency.GRAM):
            return amount
        if currency in _NON_CONVERTIBLE:
            return None
        if currency == Currency.USDT:
            # USDT→TON требует курс; без провайдера — None
            return None
        return None

    async def to_usd(self, amount: Decimal, currency: Currency) -> Decimal | None:
        if currency == Currency.USDT:
            return amount
        ton = self.to_ton(amount, currency)
        if ton is None:
            return None
        rate = await self.ton_usd_rate()
        return ton * rate if rate else None
