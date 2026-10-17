from decimal import Decimal

from app.adapters.getgems import GetgemsAdapter
from app.domain.enums import Currency, SourceStatus


def test_getgems_requires_api_key_when_enabled():
    adapter = GetgemsAdapter(enabled=True)
    assert adapter.status == SourceStatus.NOT_CONFIGURED
    assert "GETGEMS_API_KEY" in adapter.disabled_reason


def test_getgems_normalizes_offchain_gift_listing():
    adapter = GetgemsAdapter(api_key="test-key", enabled=True)
    listing = adapter.normalize_listing(
        {
            "address": "EQ-test-gift",
            "collectionAddress": "EQ-test-collection",
            "kind": "OffchainNft",
            "name": "Plush Pepe #42",
            "image": "https://example.test/gift.webp",
            "attributes": [
                {"traitType": "Model", "value": "Pepe"},
                {"traitType": "Backdrop", "value": "Green"},
                {"traitType": "Symbol", "value": "Star"},
            ],
            "sale": {
                "type": "FixPriceSale",
                "fullPrice": "1250000000",
                "currency": "TON",
                "marketplaceFee": "25000000",
                "contractType": "offchain",
            },
        }
    )

    assert listing is not None
    assert listing.gift_name == "Plush Pepe"
    assert listing.gift_num == 42
    assert listing.price == Decimal("1.25")
    assert listing.currency == Currency.TON
    assert listing.model == "Pepe"
    assert listing.backdrop == "Green"
    assert listing.symbol == "Star"
    assert listing.url.endswith("/EQ-test-collection/EQ-test-gift")


def test_getgems_skips_unsupported_currency():
    adapter = GetgemsAdapter(api_key="test-key", enabled=True)
    listing = adapter.normalize_listing(
        {
            "address": "EQ-test-gift",
            "name": "Plush Pepe #42",
            "sale": {"type": "FixPriceSale", "fullPrice": "1250000000", "currency": "USDT"},
        }
    )
    assert listing is None
