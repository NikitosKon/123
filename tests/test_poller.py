"""Проверка оценки цены выхода для алертов."""
import json
from pathlib import Path

from app.adapters.tonnel import TonnelAdapter
from app.domain.enums import Currency
from app.workers.poller import select_resale_listing

FIX = Path(__file__).parent / "fixtures" / "tonnel_gifts.json"


def test_resale_target_excludes_current_listing_and_other_models():
    adapter = TonnelAdapter(enabled=True)
    listings = [adapter.normalize_listing(raw) for raw in json.loads(FIX.read_text())]
    target = listings[0]

    resale = select_resale_listing(target, listings)

    assert resale is listings[1]
    assert resale.price > target.price


def test_resale_target_requires_comparable_ton_currency():
    adapter = TonnelAdapter(enabled=True)
    listings = [adapter.normalize_listing(raw) for raw in json.loads(FIX.read_text())]
    target = listings[0]
    target.currency = Currency.USDT

    assert select_resale_listing(target, listings) is None
