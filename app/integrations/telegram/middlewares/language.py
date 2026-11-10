from __future__ import annotations

from aiogram import BaseMiddleware

from app.core.i18n import normalize_language
from app.db.repositories import UserRepository
from app.db.session import AsyncSessionFactory


class LanguageMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        tg_user = data.get("event_from_user") or getattr(event, "from_user", None)
        lang = normalize_language(None).value

        if tg_user is not None:
            async with AsyncSessionFactory() as session:
                user = await UserRepository(session).get_or_create(
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                    last_name=tg_user.last_name,
                )
                lang = normalize_language(user.language).value
                await session.commit()

        data["lang"] = lang
        return await handler(event, data)
