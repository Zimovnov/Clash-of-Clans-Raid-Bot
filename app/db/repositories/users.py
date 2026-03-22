from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, UserLanguage


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> User:
        existing = await self.get_by_telegram_id(telegram_id)
        if existing:
            existing.username = username
            existing.first_name = first_name
            existing.last_name = last_name
            await self.session.flush()
            return existing

        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language=UserLanguage.EN,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def set_language(self, telegram_id: int, language: UserLanguage) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=None,
                first_name=None,
                last_name=None,
                language=language,
            )
            self.session.add(user)
            await self.session.flush()
            return user

        user.language = language
        await self.session.flush()
        return user

    async def list_telegram_ids(self) -> list[int]:
        stmt = select(User.telegram_id).order_by(User.telegram_id.asc())
        result = await self.session.execute(stmt)
        return [int(item) for item in result.scalars().all()]
