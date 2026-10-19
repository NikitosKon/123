# 🎁 Gift Deals Aggregator Bot

Telegram-бот-агрегатор коллекционных подарков Telegram. Отслеживает листинги на маркетплейсах, считает floor и потенциальную прибыль, присылает красивую карточку сделки.

## Возможности

- 6 адаптеров маркетплейсов с честными статусами (`live / degraded / disabled / not_configured`) — см. [MARKETPLACE_INTEGRATION_MATRIX.md](MARKETPLACE_INTEGRATION_MATRIX.md)
- Нормализация листингов в единый формат (деньги — только `Decimal`)
- 4 типа floor: **gift / model / exact variant / global** (с confidence и возрастом данных)
- Расчёт net profit и ROI с учётом всех комиссий (buy/sell fee, deposit, withdrawal, transfer, network, slippage)
- Дедупликация по fingerprint `marketplace + listing_id + price + variant` + cooldown
- Автоматические уведомления только по активным листингам, прошедшим пороги прибыли и ROI; проверка работает в фоне с настраиваемым интервалом
- Короткое уведомление показывает характеристики, цену покупки, флоры подарка и модели, недавние продажи и расчётный выход; ссылки на подарок Telegram и покупку ведут на соответствующие страницы
- Визуальная карточка уведомления (Pillow) в тёмном Telegram-стиле по референсу
- Режим уведомлений `NOTIFICATION_MODE=link` по умолчанию: текст, прямая ссылка и inline-кнопки без PNG-карточки; `card` включает визуальную карточку
- **Только оригинальные изображения подарков**: Fragment NFT CDN → Bot API `getCustomEmojiStickers` → TON metadata. Никаких AI/случайных картинок.
- Команды: `/start /latest /deals /top /gift /watchlist /filters /markets /history /flips /settings /help`. `/latest` вручную показывает до пяти новых листингов без фильтра прибыли; `/flips` показывает подтверждённые продажи после рекомендаций.
- Inline-кнопки: Открыть подарок / Купить / История цен / В избранное / Скрыть похожие
- Health endpoint `:8080/health` со статусом каждого источника
- PostgreSQL + Redis + Alembic, Docker Compose, pytest

## Быстрый старт

```bash
cp .env.example .env   # BOT_TOKEN, ADMIN_IDS и при необходимости authData
docker compose up -d --build
```

Проверка: `curl localhost:8080/health`

## Локальный запуск без Docker

```bash
pip install -r requirements.txt
cp .env.example .env   # BOT_TOKEN, DATABASE_URL
alembic upgrade head
python -m app.main
```

## Тесты

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Демо карточки без бота

```bash
python scripts/demo_card.py   # -> card_preview.png
```

## Что важно знать (честные ограничения)

- **Tonnel** — единственный источник с публичным чтением листингов без авторизации. Cloudflare блочит datacenter IP → нужен residential IP/proxy или запуск с домашней машины. Комиссия покупателя +10% (цены в API — raw, без наценки).
- **Fragment** — нет публичного API листингов. Используется только NFT-metadata CDN (оригинальные изображения/атрибуты).
- **Portals** — нужен `PORTALS_AUTH_DATA` (initData mini-app). Без него адаптер `not_configured`.
- **Getgems** — используется Read API; доступность зависит от API-ключа и сети хостинга.
- **MRKT / Telegram native** — публичного API нет, адаптеры `disabled` с причинами.
- Потенциал оценивается по сопоставимым активным листингам и последним продажам; это ориентир до комиссий и не гарантия продажи по этой цене.
- Трекер `/flips` сохраняет только предложения с определённым номером и моделью подарка. Он отслеживает последующие подтверждённые продажи в истории Getgems; для хранения нужна доступная PostgreSQL через `DATABASE_URL`. Сравнение показывает изменение цены до комиссий и не доказывает прибыль конкретного покупателя.
- `MAX_LISTING_AGE_SECONDS=600` означает, что алерт отправляется только для листингов младше десяти минут. Это окно защищает от пропусков при кратковременном сбое сети; повторные уведомления сдерживает dedup.
- `/deals` пока является информационной командой и не выводит сохранённую историю рекомендаций; подтверждённые исходы доступны через `/flips`.
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
  adapters/   base + tonnel, fragment, getgems, portals, mrkt, telegram_native
  domain/     enums, pydantic-модели (NormalizedListing, FloorQuote, DealAnalysis)
  services/   currency, floors, profit, dedup, recommendations, images
  workers/    poller (фоновый сборщик)
  storage/    db, models (SQLAlchemy), repo
  api/        health (FastAPI)
tests/        pytest + fixtures
migrations/   alembic
```
