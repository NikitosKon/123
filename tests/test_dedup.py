import json
from pathlib import Path

import pytest

from app.adapters.tonnel import TonnelAdapter
from app.services.dedup import DedupStore, fingerprint

FIX = Path(__file__).parent / "fixtures" / "tonnel_gifts.json"


@pytest.fixture()
def listing():
    a = TonnelAdapter(enabled=True)
    return a.normalize_listing(json.loads(FIX.read_text())[0])


def test_fingerprint_stable(listing):
    assert fingerprint(listing) == fingerprint(listing)


def test_fingerprint_changes_with_price(listing):
    fp1 = fingerprint(listing)
    listing.price = listing.price + 1
    assert fingerprint(listing) != fp1


def test_dedup_same_deal(listing):
    store = DedupStore(cooldown_seconds=3600)
    assert store.is_duplicate(listing) is False
    assert store.is_duplicate(listing) is True


def test_dedup_price_change(listing):
    store = DedupStore(cooldown_seconds=3600)
    assert store.is_duplicate(listing) is False
    listing.price = listing.price + 1
    assert store.is_duplicate(listing, price_changed=True) is False


def test_dedup_cooldown_expired(listing):
    store = DedupStore(cooldown_seconds=1)
    assert store.is_duplicate(listing) is False
    store._seen = {k: v - 10 for k, v in store._seen.items()}  # протухли
    assert store.is_duplicate(listing) is False
