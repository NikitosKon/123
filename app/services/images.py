"""Получение ОРИГИНАЛЬНЫХ изображений подарков. Никаких случайных/AI-картинок.

Приоритет источников:
1. Fragment NFT CDN (заминченные подарки) — webp/png + lottie
2. Telegram Bot API getCustomEmojiStickers по custom_emoji_id (неминченные тоже работают)
3. TON metadata по контракту (tonapi.io)
Если ничего нет — честно возвращаем None.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import httpx

from app.adapters.fragment import slugify

log = logging.getLogger(__name__)

BOT_API = "https://api.telegram.org"
TONAPI = "https://tonapi.io/v2"


class GiftImageService:
    def __init__(
        self,
        bot_token: str = "",
        tonapi_key: str = "",
        cache_dir: str = ".cache/images",
    ) -> None:
        self.bot_token = bot_token
        self.tonapi_key = tonapi_key
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str, ext: str) -> Path:
        h = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{h}.{ext}"

    async def _download(self, url: str, key: str) -> Path | None:
        ext = url.rsplit(".", 1)[-1].split("?")[0][:5] or "bin"
        path = self._cache_path(key, ext)
        if path.exists():
            return path
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
                r = await c.get(url)
            if r.status_code == 200 and len(r.content) > 100:
                path.write_bytes(r.content)
                return path
        except Exception as exc:  # noqa: BLE001
            log.warning("image download failed %s: %s", url, exc)
        return None

    async def from_fragment(self, gift_name: str, num: int) -> Path | None:
        """Оригинальное изображение заминченного NFT-подарка."""
        base = f"https://nft.fragment.com/gift/{slugify(gift_name)}-{num}"
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{base}.json")
        if r.status_code != 200:
            return None
        image = r.json().get("image")
        if not image:
            return None
        return await self._download(image, f"fragment-{slugify(gift_name)}-{num}")

    async def from_custom_emoji(self, custom_emoji_id: str) -> Path | None:
        """Оригинальная анимация через Bot API (webp/tgs/webm стикер подарка)."""
        if not self.bot_token or not custom_emoji_id:
            return None
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(
                    f"{BOT_API}/bot{self.bot_token}/getCustomEmojiStickers",
                    json={"custom_emoji_ids": [custom_emoji_id]},
                )
                stickers = r.json().get("result") or []
                if not stickers:
                    return None
                file_id = stickers[0]["file_id"]
                fr = await c.get(f"{BOT_API}/bot{self.bot_token}/getFile", params={"file_id": file_id})
                fpath = fr.json()["result"]["file_path"]
                url = f"{BOT_API}/file/bot{self.bot_token}/{fpath}"
            return await self._download(url, f"emoji-{custom_emoji_id}")
        except Exception as exc:  # noqa: BLE001
            log.warning("custom emoji fetch failed: %s", exc)
            return None

    async def from_ton_metadata(self, contract: str) -> Path | None:
        if not contract:
            return None
        try:
            headers = {"Authorization": f"Bearer {self.tonapi_key}"} if self.tonapi_key else {}
            async with httpx.AsyncClient(timeout=20, headers=headers) as c:
                r = await c.get(f"{TONAPI}/nfts/{contract}")
            if r.status_code != 200:
                return None
            previews = r.json().get("previews") or []
            url = next((p["url"] for p in previews if p.get("resolution") == "500x500"), None)
            if not url and previews:
                url = previews[-1].get("url")
            if url:
                return await self._download(url, f"ton-{contract}")
        except Exception as exc:  # noqa: BLE001
            log.warning("ton metadata fetch failed: %s", exc)
        return None

    async def resolve(
        self,
        gift_name: str,
        num: int | None = None,
        custom_emoji_id: str = "",
        contract: str = "",
        listing_image_url: str = "",
    ) -> Path | None:
        """Единая точка: перебираем легальные источники оригинала."""
        if listing_image_url:
            got = await self._download(listing_image_url, f"src-{listing_image_url[-40:]}")
            if got:
                return got
        if num is not None:
            got = await self.from_fragment(gift_name, num)
            if got:
                return got
        if custom_emoji_id:
            got = await self.from_custom_emoji(custom_emoji_id)
            if got:
                return got
        if contract:
            got = await self.from_ton_metadata(contract)
            if got:
                return got
        return None
