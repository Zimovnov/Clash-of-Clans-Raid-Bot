import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import (
    Base,
    Clan,
    ClanAccessRequest,
    ClanAccessRequestStatus,
    ClanRole,
)
from app.db.repositories import ClanRepository, UserRepository
from app.services.clan_service import (
    ClanAccessDeniedError,
    ClanAccessRequestAction,
    ClanAccessRequestAlreadyHandledError,
    ClanPermissionDeniedError,
    ClanService,
    TelegramIdentity,
)

TAG = "#2PP"
OWNER = TelegramIdentity(1001, "owner", "Owner", None)
REQUESTER = TelegramIdentity(1002, "requester", "Requester", None)
REVIEWER = TelegramIdentity(1003, "reviewer", "Reviewer", None)


@pytest_asyncio.fixture
async def sessions():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield factory
    finally:
        await engine.dispose()


async def seed_request(sessions, *, has_owner=True, reviewer_role=None):
    async with sessions() as session:
        clan = Clan(tag=TAG, name="Test Clan")
        session.add(clan)
        users = UserRepository(session)
        owner = await users.get_or_create(OWNER.telegram_id, OWNER.username, OWNER.first_name, None)
        reviewer = await users.get_or_create(REVIEWER.telegram_id, REVIEWER.username, REVIEWER.first_name, None)
        if has_owner:
            await ClanRepository(session).grant_role(clan.id, owner.id, ClanRole.OWNER)
        if reviewer_role:
            await ClanRepository(session).grant_role(clan.id, reviewer.id, reviewer_role)
        await session.commit()
        result = await ClanService(session, None).add_clan_or_request_access(REQUESTER, TAG)
        assert result.action == ClanAccessRequestAction.ACCESS_REQUEST_CREATED
        return result.access_request.id


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["approve", "reject"])
@pytest.mark.parametrize("reviewer_role", [None, ClanRole.MANAGER])
async def test_superadmin_reviews_without_owner_role(sessions, decision, reviewer_role):
    request_id = await seed_request(sessions, reviewer_role=reviewer_role)
    async with sessions() as session:
        service = ClanService(session, None)
        decide = getattr(service, f"{decision}_access_request")
        request = await decide(REVIEWER, request_id, is_superadmin=True)
        expected = ClanAccessRequestStatus.APPROVED if decision == "approve" else ClanAccessRequestStatus.REJECTED
        assert request.status == expected
        assert request.resolved_by_user_id == (await service.users.get_by_telegram_id(REVIEWER.telegram_id)).id
        access = await service.clans.get_access(request.clan_id, request.user_id)
        assert (access.role if access else None) == (ClanRole.MANAGER if decision == "approve" else None)


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["approve", "reject"])
@pytest.mark.parametrize("reviewer_role", [None, ClanRole.MANAGER])
async def test_non_owner_cannot_decide_when_owner_exists(sessions, decision, reviewer_role):
    request_id = await seed_request(sessions, reviewer_role=reviewer_role)
    async with sessions() as session:
        service = ClanService(session, None)
        with pytest.raises((ClanAccessDeniedError, ClanPermissionDeniedError)):
            await getattr(service, f"{decision}_access_request")(REVIEWER, request_id)
        await session.rollback()
        request = await service.get_access_request(request_id)
        assert request.status == ClanAccessRequestStatus.PENDING
        assert await service.clans.get_access(request.clan_id, request.user_id) is None


@pytest.mark.asyncio
async def test_rejection_allows_new_request_and_old_buttons_cannot_change_decision(sessions):
    first_id = await seed_request(sessions)
    async with sessions() as session:
        service = ClanService(session, None)
        await service.reject_access_request(OWNER, first_id)
        second = await service.add_clan_or_request_access(REQUESTER, TAG)
        assert second.action == ClanAccessRequestAction.ACCESS_REQUEST_CREATED
        assert second.access_request.id != first_id
        with pytest.raises(ClanAccessRequestAlreadyHandledError):
            await service.approve_access_request(OWNER, first_id)
        await session.rollback()
        second = await service.access_requests.get_pending_for_user(
            (await service.clans.get_by_tag(TAG)).id,
            (await service.users.get_by_telegram_id(REQUESTER.telegram_id)).id,
        )
        approved = await service.approve_access_request(OWNER, second.id)
        with pytest.raises(ClanAccessRequestAlreadyHandledError):
            await service.reject_access_request(OWNER, approved.id)
        await session.rollback()
        rows = list((await session.scalars(select(ClanAccessRequest).order_by(ClanAccessRequest.id))).all())
        assert [row.status for row in rows] == [ClanAccessRequestStatus.REJECTED, ClanAccessRequestStatus.APPROVED]


@pytest.mark.asyncio
async def test_superadmin_can_grant_manager_without_clan_access(sessions):
    request_id = await seed_request(sessions)
    async with sessions() as session:
        service = ClanService(session, None)
        clan, user = await service.grant_manager(REVIEWER, TAG, REQUESTER.telegram_id, is_superadmin=True)
        assert (await service.clans.get_access(clan.id, user.id)).role == ClanRole.MANAGER
        assert (await service.get_access_request(request_id)).status == ClanAccessRequestStatus.APPROVED
