# ClashInfoBot на общем VPS

Проект разворачивается отдельно от Mindflower и RAID GAME в `/opt/clashinfobot`.
SSH: существующий профиль `raid-game-prod`; приватные ключи и `.env` в Git не входят.

## Устройство

- `releases/<release>` — проверенные исходники, Compose и SHA-256 manifest.
- `current` — ссылка на активный релиз.
- `shared/.env` — отдельные production-секреты, права 0600.
- `shared/backup.key` — ключ шифрования резервных копий, права 0600.
- `data/postgres` — собственная PostgreSQL 16; порт БД наружу не опубликован.
- `ops` — команды эксплуатации и резервного копирования.
- `backups` — до трёх последних зашифрованных копий, прошедших restore-test.

Постоянно работают только PostgreSQL и Telegram-бот. Служебный API запускается
по необходимости профилем `api`, чтобы сохранить запас памяти на общем VPS.
Он доступен только на `127.0.0.1:8011`; служебные операции требуют отдельный
Bearer token, Swagger выключен. Telegram использует один polling-процесс.
Контейнеры приложения работают без root с read-only файловой системой,
ограничениями памяти/CPU/PID и ротацией логов. Сеть PostgreSQL изолирована.

Локально production-секреты и отдельная копия backup key сохраняются в
`~/.config/clashinfobot/` с правами 0700/0600. Исходный проектный `.env` сохраняется.
Первый архив с Windows не содержал дампа БД. Позднее данные восстановлены из
копии от 8 июня 2026 года: активная БД — `clashinfobot_restored_20260608`.
Прежняя пустая БД `clashinfobot` сохранена для отката. Проверки и точный состав
восстановления описаны в [DATABASE_RESTORE.md](DATABASE_RESTORE.md).

## Проверки и запуск

Локальное окружение: Python 3.13, `uv sync --frozen --extra dev`.
Тесты запускать на отдельной БД и с фиктивными токенами. Зависимости зафиксированы
в `uv.lock` и экспортированы с hashes в `requirements.lock`.
Dockerfile устанавливает только зафиксированные runtime-зависимости.
Для x86_64 VPS образ на Mac собирается с `--platform linux/amd64`.
В образ и серверный source bundle не входят `.env`, Git, тесты и кэши.

Перед выпуском проверить свободную память/диск и состояние соседних служб,
проверенный backup/restore и совместимость отката. Не менять Compose, БД,
контейнеры и настройки Mindflower/RAID GAME при обновлении ClashInfoBot.

```sh
ssh raid-game-prod '/opt/clashinfobot/ops/compose.sh ps'
ssh raid-game-prod '/opt/clashinfobot/ops/compose.sh logs --tail=40 bot'
```

При необходимости API: `compose.sh --profile api up -d --wait api`, проверить
`curl -fsS http://127.0.0.1:8011/ready`, затем `compose.sh stop api`.
Бот обращается напрямую к БД и Clash API и не зависит от HTTP API.
Лимиты: bot 256 MiB, db 128 MiB, optional api 128 MiB. Новые контейнеры имеют
повышенный OOM score, чтобы при нехватке памяти защитить соседние проекты.

Новый релиз сначала проверить локально: pytest, Docker build, PostgreSQL migrations,
`/ready`, 401 без токена на `/internal/jobs/sync-clan`, 404 на `/docs`, `pip check`
и аудит зафиксированных зависимостей. Production-миграции выполнять только после
проверки backup и совместимости. Одновременно два polling-процесса не запускать.

## Резервные копии

`clashinfobot-backup.timer` запускается ежедневно в 04:00 UTC с задержкой до пяти
минут. Общий flock сериализует операцию с backup Mindflower. Скрипт проверяет
свободные ресурсы, создаёт `pg_dump -Fc`, шифрует GnuPG AES-256 и проверяет
расшифровку и SHA-256. Затем выполняет настоящий `pg_restore` в одноразовом
контейнере с `--network none` и временной БД в tmpfs. Рабочая БД не используется
для restore-test. Только после успешной проверки включается ротация до трёх копий.

```sh
ssh raid-game-prod 'systemctl start clashinfobot-backup.service'
ssh raid-game-prod 'systemctl show clashinfobot-backup.service -p Result -p ExecMainStatus'
ssh raid-game-prod 'systemctl list-timers clashinfobot-backup.timer'
```

Копии `.dump.gpg` переносить с соответствующим `.json` и сверять SHA-256.
Ключ хранить отдельно от архивов. Первая проверенная копия сохраняется также
на Mac в `~/.local/share/clashinfobot/backups/`. Автоматическая off-host передача
этим таймером не выполняется.

## Откат

Для первой установки безопасный откат — остановить только ClashInfoBot:

```sh
ssh raid-game-prod '/opt/clashinfobot/ops/compose.sh stop bot api db'
```

Данные, секреты, резервные копии и соседние сервисы сохраняются. Не использовать
`down -v`, очистку Docker или восстановление старого дампа поверх рабочей БД.
При следующих релизах сохранять предыдущие source/image/env и заранее проверять
совместимость схемы; переключать `current` и image только при остановленном боте.

## Ключи API

Telegram-токен проверяется методом `getMe`; webhook должен отсутствовать для polling.
Ключ Clash API должен разрешать исходящий IP VPS. При переносе с другого IP
создать ключ в официальном developer portal для `88.210.63.188` и обновить только
`CLASH_API_TOKEN` в защищённой production-конфигурации. Ошибка
`accessDenied.invalidIp` указывает на IP allowlist; сама по себе не означает истечение
срока токена. `deploy/check_credentials.py` делает только read-only проверки,
принимает JSON с токенами через stdin и не выводит секреты.
