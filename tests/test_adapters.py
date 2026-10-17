"""Статусы адаптеров без сети + недоступный маркетплейс не роняет сборщик."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.adapters import build_adapters
from app.adapters.mrkt import MrktAdapter
from app.adapters.portals import PortalsAdapter
from app.adapters.telegram_native import TelegramNativeAdapter
from app.config import Settings
from app.domain.enums import Marketplace, SourceStatus
from app.domain.models import NormalizedListing


def test_default_statuses():
    adapters = build_adapters(Settings())
    by_mp = {a.marketplace: a for a in adapters}
    assert by_mp[Marketplace.TELEGRAM_NATIVE].status == SourceStatus.DISABLED
    assert by_mp[Marketplace.MRKT].status == SourceStatus.DISABLED
    assert by_mp[Marketplace.TONNEL].status == SourceStatus.DISABLED
    # Portals включён, но без authData -> not_configured
    p = PortalsAdapter(auth_data="", enabled=True)
    assert p.status == SourceStatus.NOT_CONFIGURED
    assert "PORTALS_AUTH_DATA" in p.disabled_reason


@pytest.mark.asyncio
async def test_disabled_adapters_return_empty():
    for a in (MrktAdapter(), TelegramNativeAdapter(), PortalsAdapter(enabled=False)):
        assert await a.fetch_new_listings() == []
        assert await a.fetch_active_listings("X") == []
        assert await a.fetch_listing_details("1") is None
        assert await a.health_check() in (
            SourceStatus.DISABLED,
            SourceStatus.NOT_CONFIGURED,
        )


@pytest.mark.asyncio
async def test_failing_source_does_not_stop_others():
    """Сборщик продолжает работу, когда один источник падает."""

    class BrokenAdapter(MrktAdapter):
        marketplace = Marketplace.MRKT
        status = SourceStatus.LIVE

        async def fetch_new_listings(self, since=None):
            raise ConnectionError("source down")

    class OkAdapter(MrktAdapter):
        marketplace = Marketplace.TONNEL
        status = SourceStatus.LIVE

        async def fetch_new_listings(self, since=None):
            return [
                NormalizedListing(
                    marketplace=Marketplace.TONNEL,
                    listing_id="1",
                    gift_name="X",
                    price=Decimal("1"),
                    fetched_at=datetime.now(timezone.utc),
                )
            ]

    results = []
    for a in (BrokenAdapter(), OkAdapter()):
        try:
            results += await a.fetch_new_listings()
        except ConnectionError:
            continue
    assert len(results) == 1
