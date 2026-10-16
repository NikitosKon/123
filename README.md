# 🎁 Gift Deals Aggregator Bot

Telegram-бот-агрегатор коллекционных подарков Telegram. Отслеживает листинги на маркетплейсах, считает floor и потенциальную прибыль, присылает красивую карточку сделки.

## Возможности

- 6 адаптеров маркетплейсов с честными статусами (`live / degraded / disabled / not_configured`) — см. [MARKETPLACE_INTEGRATION_MATRIX.md](MARKETPLACE_INTEGRATION_MATRIX.md)
- Нормализация листингов в единый формат (деньги — только `Decimal`)
- 4 типа floor: **gift / model / exact variant / global** (с confidence и возрастом данных)
- Расчёт net profit и ROI с учётом всех комиссий (buy/sell fee, deposit, withdrawal, transfer, network, slippage)
- Дедупликация по fingerprint `marketplace + listing_id + price + variant` + cooldown
- Визуальная карточка уведомления (Pillow) в тёмном Telegram-стиле по референсу
- **Только оригинальные изображения подарков**: Fragment NFT CDN → Bot API `getCustomEmojiStickers` → TON metadata. Никаких AI/случайных картинок.
- Команды: `/start /latest /deals /top /gift /watchlist /filters /markets /history /settings /help`
- Inline-кнопки: Открыть подарок / Купить / История цен / В избранное / Скрыть похожие
- Health endpoint `:8080/health` со статусом каждого источника
- PostgreSQL + Redis + Alembic, Docker Compose, pytest

## Быстрый старт

```bash
cp .env.example .env   # заполнить BOT_TOKEN
docker compose up -d --build
```

Проверка: `curl localhost:${PORT:-8080}/health`

## Локальный запуск без Docker

```bash
pip install -r requirements.txt
cp .env.example .env   # BOT_TOKEN, DATABASE_URL
alembic upgrade head
python -m app.main
```

## Тесты

```bash
pip install pytest pytest-asyncio aiosqlite
pytest -q
```

## Демо карточки без бота

```bash
python scripts/demo_card.py   # -> card_preview.png
```

## Размещение на хостинге

Приложение работает как постоянно запущенный Docker-сервис: бот использует Telegram long polling и одновременно отдаёт health endpoint `/health`. На хостинге укажите Dockerfile из корня репозитория и сохраните процесс работающим постоянно; приложение слушает `0.0.0.0:$PORT` (по умолчанию `8080`). Секреты `BOT_TOKEN`, `ADMIN_IDS` и данные авторизации маркетплейсов задавайте только в защищённых переменных окружения хостинга, не в репозитории. После запуска откройте бота в Telegram и отправьте `/start`.

По умолчанию все источники выключены. Перед включением проверьте требования в [матрице интеграций](MARKETPLACE_INTEGRATION_MATRIX.md): некоторым источникам нужны токены, авторизация или подходящий IP.

## Что важно знать (честные ограничения)

- **Tonnel** — единственный источник с публичным чтением листингов без авторизации. Cloudflare блочит datacenter IP → нужен residential IP/proxy или запуск с домашней машины. Комиссия покупателя +10% (цены в API — raw, без наценки).
- **Fragment** — нет публичного API листингов. Используется только NFT-metadata CDN (оригинальные изображения/атрибуты).
- **Portals** — нужен `PORTALS_AUTH_DATA` (initData mini-app). Без него адаптер `not_configured`.
- **Getgems** — GraphQL публичный, но CloudFront блочит datacenter IP.
- **MRKT / Telegram native** — публичного API нет, адаптеры `disabled` с причинами.
- Прибыль всегда подписана `estimated`, если нет исполнимых buy orders.
- Telegram Stars не конвертируются автоматически (нет надёжного курса) — показываются отдельно.
- TON ≡ GRAM (ребрендинг 2026), отображение валюты зависит от исходного маркетплейса.

## Для production нужно добавить

- Residential proxy pool для Tonnel/Getgems (или запуск с residential IP)
- authData/токены для Portals/Thermos (ротация, TTL initData)
- Redis-backed dedup (сейчас in-memory) и per-user rate limiting
- Персистентные user filters через `/settings` (сейчас читаются из .env-дефолтов)
- Курс TON/USD провайдер (`TON_PRICE_PROVIDER`) для нормализации USD/USDT
- Алерты на падение источников (Telegram admin), Prometheus-метрики
- Webhook-режим бота вместо polling

## Структура

```
app/
  bot/        handlers, keyboards, formatters, cards (Pillow-рендер)
  adapters/   base + tonnel, fragment, getgems, portals, tonnel, mrkt, telegram_native
  domain/     enums, pydantic-модели (NormalizedListing, FloorQuote, DealAnalysis)
  services/   currency, floors, profit, dedup, images
  workers/    poller (фоновый сборщик)
  storage/    db, models (SQLAlchemy), repo
  api/        health (FastAPI)
tests/        pytest + fixtures
migrations/   alembic
```
