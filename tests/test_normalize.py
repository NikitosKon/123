import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.tonnel import TonnelAdapter, _split_rarity
from app.domain.enums import Currency, Marketplace, SourceStatus

FIX = Path(__file__).parent / "fixtures" / "tonnel_gifts.json"


@pytest.fixture()
def adapter():
    return TonnelAdapter(enabled=True)


@pytest.fixture()
def raw_list():
    return json.loads(FIX.read_text())


def test_split_rarity():
    assert _split_rarity("Hoverboard (3%)") == ("Hoverboard", Decimal("3"))
    assert _split_rarity("Lion Head (0.4%)") == ("Lion Head", Decimal("0.4"))
    assert _split_rarity("Plain") == ("Plain", None)


def test_normalize_ok(adapter, raw_list):
    l = adapter.normalize_listing(raw_list[0])
    assert l is not None
    assert l.marketplace == Marketplace.TONNEL
    assert l.gift_name == "Surge Board"
    assert l.gift_num == 29348
    assert l.model == "Hoverboard"
    assert l.model_rarity_pct == Decimal("3")
    assert l.backdrop == "Midnight Blue"
    assert l.symbol == "Lion Head"
    assert l.price == Decimal("4.8")
    assert isinstance(l.price, Decimal)
    assert l.currency == Currency.TON
    assert l.transferable is True
    assert l.is_active is True
    assert l.url.startswith("https://market.tonnel.network/")


def test_normalize_blocked_transfer(adapter, raw_list):
    l = adapter.normalize_listing(raw_list[2])
    assert l is not None
    assert l.transferable is False


def test_normalize_missing_price(adapter):
    assert adapter.normalize_listing({"name": "X"}) is None
    assert adapter.normalize_listing({"price": "not-a-number"}) is None
    assert adapter.normalize_listing({"price": None}) is None


def test_fee_and_status(adapter):
    assert adapter.get_marketplace_fee() == Decimal("0.10")
    disabled = TonnelAdapter(enabled=False)
    assert disabled.status == SourceStatus.DISABLED
