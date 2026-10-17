"""Изображения: только оригинальные источники; отсутствие — честный None."""
import pytest

from app.services.images import GiftImageService


@pytest.mark.asyncio
async def test_no_sources_returns_none(tmp_path, monkeypatch):
    svc = GiftImageService(bot_token="", tonapi_key="", cache_dir=str(tmp_path))

    async def no_fragment(*_args, **_kwargs):
        return None

    # Это unit-тест: отсутствие источников не должно зависеть от сети,
    # прокси или доступности Fragment CDN.
    monkeypatch.setattr(svc, "from_fragment", no_fragment)
    got = await svc.resolve(gift_name="No Such Gift Xyz", num=999999999)
    assert got is None


def test_cache_path_stable(tmp_path):
    svc = GiftImageService(cache_dir=str(tmp_path))
    p1 = svc._cache_path("key", "webp")
    p2 = svc._cache_path("key", "webp")
    assert p1 == p2
    assert str(p1).endswith(".webp")
