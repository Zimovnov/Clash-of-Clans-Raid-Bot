# ClashInfoBot MVP

Telegram-бот для руководителей кланов Clash of Clans.

## Возможности

- Мультиклановая модель доступа: `owner` / `manager` / `superadmin`
- Интеграция с официальным Clash API
- Ручные и автоматические рейд-отчёты
- Классификация игроков:
  - `kick` - 0 атак
  - `questionable` - 1-5 атак
  - `newbie` - по правилу 7 дней / с начала рейда
  - `left_clan` - был в период рейда, но вышел
- Отправка автоотчётов owner/manager в личные сообщения Telegram

## Быстрый старт

1. Скопируйте `.env.example` в `.env`.
2. Заполните минимум:
   - `BOT_TOKEN`
   - `CLASH_API_TOKEN`
   - `POSTGRES_PASSWORD`
   - `DATABASE_URL`
   - `INTERNAL_API_TOKEN`
   - `SUPERADMIN_TELEGRAM_IDS`
3. Поднимите базу и сервисы:

```bash
docker compose up -d --build
```

4. Примените миграции:

```bash
docker compose exec api alembic upgrade head
```

## Безопасность и VPS

- `api` и `db` по умолчанию публикуются только на `127.0.0.1`. Не меняйте `API_BIND_HOST` и `DB_BIND_HOST` на `0.0.0.0`, если в этом нет реальной необходимости.
- Внутренний HTTP API выключен, если не задан `INTERNAL_API_TOKEN`.
- Swagger/ReDoc и `openapi.json` выключены по умолчанию. Для локальной отладки можно временно включить `API_DOCS_ENABLED=true`.
- Контейнеры `api` и `bot` запускаются от непривилегированного пользователя, с `read_only` root filesystem и `cap_drop: ALL`.
- Для VPS обязательно задайте `SUPERADMIN_TELEGRAM_IDS`, используйте длинные случайные секреты и храните `.env` с правами `600`.
- Лучше открывать наружу только SSH и, при необходимости, reverse proxy на `80/443`. Самому приложению входящий публичный порт не нужен для long polling Telegram.

## Внутренний API

Если `api` включен и задан `INTERNAL_API_TOKEN`, запросы к `/internal/*` нужно подписывать bearer-токеном:

```bash
curl -H "Authorization: Bearer <INTERNAL_API_TOKEN>" \
  http://127.0.0.1:8000/internal/clans/%23TAG/report/latest
```

## Рекомендации для продакшена

- Используйте отдельного пользователя на VPS и вход по SSH-ключам.
- Включите firewall (`ufw`/`iptables`) и `fail2ban`.
- Делайте резервные копии тома Postgres и периодически проверяйте восстановление.
- После первого деплоя ротируйте все тестовые или ранее использованные токены.
