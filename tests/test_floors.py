import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.tonnel import TonnelAdapter
from app.domain.enums import Confidence
from app.services.floors import (
    exact_variant_floor,
    gift_floor,
    global_floor,
    model_floor,
)

FIX = Path(__file__).parent / "fixtures" / "tonnel_gifts.json"


@pytest.fixture()
def listings():
    a = TonnelAdapter(enabled=True)
    return [a.normalize_listing(r) for r in json.loads(FIX.read_text())]


def test_gift_floor(listings):
    target = listings[1]  # Hoverboard 6.12
    f = gift_floor(target, listings)
    assert f.value == Decimal("4.8")  # минимум по всем Surge Board
    assert f.listings_count == 4


def test_model_floor(listings):
    target = listings[0]
    f = model_floor(target, listings)
    assert f.value == Decimal("4.8")  # оба Hoverboard: 4.8 и 6.12
    assert f.listings_count == 2
    assert f.confidence == Confidence.MEDIUM


def test_exact_variant_floor_single_low_confidence(listings):
    target = listings[0]
    f = exact_variant_floor(target, listings)
    assert f.value == Decimal("4.8")
    assert f.listings_count == 1
    assert f.confidence == Confidence.LOW_CONFIDENCE


def test_floors_ignore_inactive(listings):
    for l in listings:
        l.is_active = False
    f = gift_floor(listings[0], listings)
    assert f.value is None


def test_global_floor_requires_ton_normalization(listings):
    # price_ton не заполнен -> global floor пустой
    f = global_floor(listings[0], listings)
    assert f.value is None
    for l in listings:
        l.price_ton = l.price
    f = global_floor(listings[0], listings)
    assert f.value == Decimal("4.8")
