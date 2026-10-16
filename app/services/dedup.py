"""Дедупликация уведомлений по fingerprint + cooldown."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

from app.domain.models import NormalizedListing


def fingerprint(listing: NormalizedListing) -> str:
    base = (
        f"{listing.marketplace.value}|{listing.listing_id}|"
        f"{listing.price}|{listing.variant_fingerprint}"
    )
    return hashlib.sha256(base.encode()).hexdigest()[:24]


@dataclass
class DedupStore:
    """In-memory дедуп (Redis-вариант — storage/redis_dedup.py в production)."""

    cooldown_seconds: int = 3600
    _seen: dict[str, float] = field(default_factory=dict)

    def is_duplicate(self, listing: NormalizedListing, *, price_changed: bool = False) -> bool:
        fp = fingerprint(listing)
        now = time.time()
        # чистим протухшие
        self._seen = {k: v for k, v in self._seen.items() if now - v < self.cooldown_seconds}
        if fp in self._seen and not price_changed:
            return True
        self._seen[fp] = now
        return False
