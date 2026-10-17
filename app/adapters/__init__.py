"""Реестр адаптеров."""
from __future__ import annotations

from app.adapters.base import MarketplaceAdapter
from app.adapters.fragment import FragmentAdapter
from app.adapters.getgems import GetgemsAdapter
from app.adapters.mrkt import MrktAdapter
from app.adapters.portals import PortalsAdapter
from app.adapters.telegram_native import TelegramNativeAdapter
from app.adapters.tonnel import TonnelAdapter
from app.config import Settings


def build_adapters(settings: Settings) -> list[MarketplaceAdapter]:
    return [
        TelegramNativeAdapter(enabled=settings.enable_telegram_native),
        FragmentAdapter(enabled=settings.enable_fragment),
        GetgemsAdapter(api_key=settings.getgems_api_key, enabled=settings.enable_getgems),
        PortalsAdapter(auth_data=settings.portals_auth_data, enabled=settings.enable_portals),
        TonnelAdapter(auth_data=settings.tonnel_auth_data, enabled=settings.enable_tonnel),
        MrktAdapter(enabled=settings.enable_mrkt),
    ]
