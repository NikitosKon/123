from decimal import Decimal

import pytest

from app.domain.enums import Currency
from app.services.currency import CurrencyConverter


@pytest.mark.asyncio
async def test_gram_equals_ton():
    c = CurrencyConverter()
    assert c.to_ton(Decimal("6.12"), Currency.GRAM) == Decimal("6.12")
    assert c.to_ton(Decimal("6.12"), Currency.TON) == Decimal("6.12")


@pytest.mark.asyncio
async def test_stars_not_converted():
    c = CurrencyConverter()
    assert c.to_ton(Decimal("100"), Currency.STARS) is None
    assert await c.to_usd(Decimal("100"), Currency.STARS) is None


@pytest.mark.asyncio
async def test_no_provider_no_rate():
    c = CurrencyConverter(provider_url="")
    assert await c.ton_usd_rate() is None
    assert await c.to_usd(Decimal("10"), Currency.TON) is None
