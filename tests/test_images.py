"""Изображения: только оригинальные источники; отсутствие — честный None."""
import pytest

from app.services.images import GiftImageService


@pytest.mark.asyncio
async def test_no_sources_returns_none(tmp_path):
    svc = GiftImageService(bot_token="", tonapi_key="", cache_dir=str(tmp_path))
    # Fragment CDN вернёт 404 для несуществующего подарка; остальные источники не настроены
    got = await svc.resolve(gift_name="No Such Gift Xyz", num=999999999)
    assert got is None


def test_cache_path_stable(tmp_path):
    svc = GiftImageService(cache_dir=str(tmp_path))
    p1 = svc._cache_path("key", "webp")
    p2 = svc._cache_path("key", "webp")
    assert p1 == p2
    assert str(p1).endswith(".webp")
