from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import ClanAccessRequest, ClanAccessRequestStatus, ClanRole


class AccessRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, clan_id: int, user_id: int, requested_role: ClanRole) -> ClanAccessRequest:
        request = ClanAccessRequest(
            clan_id=clan_id,
            user_id=user_id,
            requested_role=requested_role,
            status=ClanAccessRequestStatus.PENDING,
        )
        self.session.add(request)
        await self.session.flush()
        return request

    async def get_by_id(self, request_id: int) -> ClanAccessRequest | None:
        stmt = (
            select(ClanAccessRequest)
            .where(ClanAccessRequest.id == request_id)
            .options(
                selectinload(ClanAccessRequest.clan),
                selectinload(ClanAccessRequest.user),
                selectinload(ClanAccessRequest.resolved_by_user),
            )
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_for_user(self, clan_id: int, user_id: int) -> ClanAccessRequest | None:
        stmt = (
            select(ClanAccessRequest)
            .where(
                ClanAccessRequest.clan_id == clan_id,
                ClanAccessRequest.user_id == user_id,
                ClanAccessRequest.status == ClanAccessRequestStatus.PENDING,
            )
            .order_by(ClanAccessRequest.created_at.desc(), ClanAccessRequest.id.desc())
            .options(selectinload(ClanAccessRequest.clan), selectinload(ClanAccessRequest.user))
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_pending_for_clan(self, clan_id: int) -> list[ClanAccessRequest]:
        stmt = (
            select(ClanAccessRequest)
            .where(
                ClanAccessRequest.clan_id == clan_id,
                ClanAccessRequest.status == ClanAccessRequestStatus.PENDING,
            )
            .options(selectinload(ClanAccessRequest.user))
            .order_by(ClanAccessRequest.created_at.asc(), ClanAccessRequest.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def resolve_for_user(
        self,
        clan_id: int,
        user_id: int,
        status: ClanAccessRequestStatus,
        resolved_by_user_id: int,
        resolved_at,
    ) -> None:
        stmt = select(ClanAccessRequest).where(
            ClanAccessRequest.clan_id == clan_id,
            ClanAccessRequest.user_id == user_id,
            ClanAccessRequest.status == ClanAccessRequestStatus.PENDING,
        )
        result = await self.session.execute(stmt)
        for request in result.scalars().all():
            request.status = status
            request.resolved_by_user_id = resolved_by_user_id
            request.resolved_at = resolved_at
        await self.session.flush()
