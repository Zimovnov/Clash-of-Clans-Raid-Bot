# ClashInfoBot MVP

Telegram-бот для руководителей кланов Clash of Clans.

- Мультиклановая модель доступа: `owner` / `manager` / `superadmin`
- Интеграция с официальным Clash API
- Ручные и автоматические рейд-отчёты
- Классификация игроков:
  - `kick` - 0 атак
  - `questionable` - 1-5 атак
  - `newbie` - по правилу 7 дней / с начала рейда
  - `left_clan` - был в период рейда, но вышел
- Отправка автоотчётов owner/manager в личные сообщения Telegram
