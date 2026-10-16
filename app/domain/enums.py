from __future__ import annotations

import enum


class Marketplace(str, enum.Enum):
    TELEGRAM_NATIVE = "telegram_native"
    FRAGMENT = "fragment"
    GETGEMS = "getgems"
    PORTALS = "portals"
    TONNEL = "tonnel"
    MRKT = "mrkt"
    THERMOS = "thermos"


class SourceStatus(str, enum.Enum):
    LIVE = "live"
    DEGRADED = "degraded"
    DISABLED = "disabled"
    NOT_CONFIGURED = "not_configured"


class Currency(str, enum.Enum):
    TON = "TON"
    GRAM = "GRAM"  # ребрендинг TON → Gram (1:1)
    USDT = "USDT"
    STARS = "STARS"  # отображается отдельно, надёжного курса нет


class Confidence(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    LOW_CONFIDENCE = "low confidence"


class DealStatus(str, enum.Enum):
    ESTIMATED = "estimated"
    CONFIRMED = "confirmed"
