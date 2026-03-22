import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base, ClanAccessRequestStatus, ClanRole
from app.db.repositories import ClanRepository, UserRepository
from app.services.clan_service import ClanAccessRequestAction, ClanService, TelegramIdentity


class FakeClashClient:
    async def get_clan(self, clan_tag: str) -> dict[str, str]:
        return {"name": "Test Clan", "tag": clan_tag}

    async def get_clan_members(self, clan_tag: str):
        return []


@pytest.mark.asyncio
async def test_access_request_flow_creates_pending_and_grants_manager() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    owner = TelegramIdentity(telegram_id=1001, username="owner", first_name="Owner", last_name=None)
    requester = TelegramIdentity(telegram_id=1002, username="guest", first_name="Guest", last_name=None)

    async with session_factory() as session:
        service = ClanService(session=session, clash_client=FakeClashClient())
        owner_result = await service.add_clan_or_request_access(owner, "#CLAN")
        assert owner_result.action == ClanAccessRequestAction.OWNER_ASSIGNED
        assert owner_result.role == ClanRole.OWNER

    async with session_factory() as session:
        service = ClanService(session=session, clash_client=FakeClashClient())
        request_result = await service.add_clan_or_request_access(requester, "#CLAN")
        assert request_result.action == ClanAccessRequestAction.ACCESS_REQUEST_CREATED
        assert request_result.access_request is not None
        assert request_result.access_request.status == ClanAccessRequestStatus.PENDING

        duplicate_result = await service.add_clan_or_request_access(requester, "#CLAN")
        assert duplicate_result.action == ClanAccessRequestAction.ACCESS_REQUEST_PENDING
        assert duplicate_result.access_request is not None
        assert duplicate_result.access_request.id == request_result.access_request.id

        overview = await service.list_roles("#CLAN")
        assert overview is not None
        assert len(overview.pending_requests) == 1

    async with session_factory() as session:
        service = ClanService(session=session, clash_client=FakeClashClient())
        approved_request = await service.approve_access_request(owner, request_result.access_request.id)
        assert approved_request.status == ClanAccessRequestStatus.APPROVED
        assert approved_request.requested_role == ClanRole.MANAGER

        users = UserRepository(session)
        clans = ClanRepository(session)
        requester_user = await users.get_by_telegram_id(requester.telegram_id)
        clan = await clans.get_by_tag("#CLAN")
        assert requester_user is not None
        assert clan is not None

        access = await clans.get_access(clan.id, requester_user.id)
        assert access is not None
        assert access.role == ClanRole.MANAGER

    await engine.dispose()
