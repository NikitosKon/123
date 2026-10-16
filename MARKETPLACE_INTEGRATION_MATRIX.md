# MARKETPLACE_INTEGRATION_MATRIX

Дата проверки: 2026-10-17. Проверка выполнялась из серверного окружения (datacenter IP).

| # | Маркетплейс | Способ получения данных | Auth | Антибот | Статус адаптера | Комментарий |
|---|-------------|------------------------|------|---------|-----------------|-------------|
| 1 | Telegram native marketplace | Нет публичного API. Данные доступны только внутри Telegram-клиента / через MTProto-сессию | MTProto session | — | `disabled` | Использование чужих/украденных сессий запрещено. Официального Bot API endpoint для маркетплейса нет. Оставлено отключённым до появления официального API. |
| 2 | Fragment | Нет публичного API листингов подарков. Сайт — SPA с подписанными запросами, требует Telegram login + KYC для действий | Telegram login | Cloudflare + подписи | `degraded` | **Что работает легально:** публичный NFT-metadata CDN `https://nft.fragment.com/gift/{slug}-{num}.json` (метаданные, изображение `.webp`, lottie-анимация заминченных подарков) — используется как источник изображений и атрибутов. Листинги/цены — нет публичного endpoint, не обходим. |
| 3 | Getgems | Публичный GraphQL `https://api.getgems.io/graphql` | Не нужен для чтения | CloudFront (блочит datacenter IP) | `degraded` | API существует и отвечает с residential IP / через их web app. Из datacenter — 403. Адаптер реализован, статус помечается автоматически через health_check. Fee по подаркам ~2%. |
| 4 | Portals | Внутреннее API mini-app `https://portals-market.com/api/...` | Требуется authData (initData mini-app) | Cloudflare | `degraded` | Публичного неавторизованного endpoint нет. Чтение листингов требует authData. Адаптер реализован, по умолчанию `not_configured` (нужен `PORTALS_AUTH_DATA`). Fee ~6–7%. |
| 5 | Tonnel Market | `https://gifts2.tonnel.network/api/*` (pageGifts, floorPrices, saleHistory и др.) | Чтение листингов — без auth; floor-статистика — с authData | Cloudflare (блочит datacenter IP) + `x-ts`/`x-wtf` подпись | `live` (с residential IP) / `degraded` (datacenter) | Реализован легально: та же схема запросов, что у их web-клиента (подпись — шифрование timestamp, не обход защиты). Из datacenter Cloudflare возвращает 403 — адаптер честно переходит в `degraded`. Комиссия покупателя +10% к цене листинга. |
| 6 | MRKT | Telegram-бот @mrkt, веб mrkt.land. Публичного документированного API нет; существуют community-обёртки (`tgmrkt-api`) | Зависит от endpoint | Cloudflare | `disabled` | Нет стабильного публичного endpoint для автоматического чтения листингов. Адаптер-заглушка с подробной причиной. Включить, когда появится официальный публичный API. |

## Дополнительные источники (не в списке, но полезны)

| Источник | Что даёт | Статус |
|----------|----------|--------|
| Fragment NFT CDN (`nft.fragment.com`) | Метаданные + оригинальные изображения/lottie заминченных подарков | Используется (`services/images.py`) |
| Telegram Bot API `getCustomEmojiStickers` | Оригинальная анимация подарка по `custom_emoji_id` (даже если не заминчен на Fragment) | Используется как fallback для изображений |
| Thermos (swap.coffee) API | Агрегированный каталог листингов TONNEL/PORTALS/MRKT, требует API token | Опциональный адаптер, `not_configured` по умолчанию |
| tonapi.io | On-chain данные (владелец, контракт, история транзакций NFT) | Используется для обогащения (опционально, ключ `TONAPI_KEY`) |

## Выводы

- **Единственный источник с рабочим публичным чтением листингов без auth — Tonnel**, и то с ограничением по IP. MVP рассчитан на Tonnel как primary source, остальные включаются по мере появления доступа (authData / API keys / residential proxy).
- **Изображения подарков** берутся только оригинальные: Fragment NFT CDN → Telegram Bot API (custom emoji) → TON metadata. AI-генерация и случайные картинки запрещены на уровне кода (`services/images.py` не имеет такого пути).
- Все адаптеры сообщают статус `live / degraded / disabled / not_configured` через `health_check()`, сборщик не останавливается при падении отдельного источника.
