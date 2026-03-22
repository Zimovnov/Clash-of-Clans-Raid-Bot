from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base, Clan, ClanRole
from app.db.repositories import ClanRepository, PlayerRepository, UserRepository
from app.services.clan_service import ClanPermissionDeniedError, ClanService, TelegramIdentity


class DummyClashClient:
    async def get_clan_members(self, clan_tag: str):
        return []


@pytest.mark.asyncio
async def test_manager_cannot_grant_or_revoke_access() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        users = UserRepository(session)
        clans = ClanRepository(session)

        owner = await users.get_or_create(telegram_id=1001, username="owner", first_name="Owner", last_name=None)
        manager = await users.get_or_create(telegram_id=1002, username="manager", first_name="Manager", last_name=None)
        target = await users.get_or_create(telegram_id=1003, username="target", first_name="Target", last_name=None)

        clan = Clan(tag="#CLAN", name="Clan", is_tracking=True)
        session.add(clan)
        await session.flush()

        await clans.grant_role(clan.id, owner.id, ClanRole.OWNER)
        await clans.grant_role(clan.id, manager.id, ClanRole.MANAGER)
        await clans.grant_role(clan.id, target.id, ClanRole.MANAGER)
        await session.commit()

    async with session_factory() as session:
        service = ClanService(session=session, clash_client=DummyClashClient())
        manager_identity = TelegramIdentity(
            telegram_id=1002,
            username="manager",
            first_name="Manager",
            last_name=None,
        )

        with pytest.raises(ClanPermissionDeniedError):
            await service.grant_manager(
                actor_identity=manager_identity,
                raw_tag="#CLAN",
                telegram_id=1004,
                is_superadmin=False,
            )

        with pytest.raises(ClanPermissionDeniedError):
            await service.revoke_access(
                actor_identity=manager_identity,
                raw_tag="#CLAN",
                telegram_id=1003,
                is_superadmin=False,
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_manager_can_leave_clan_access() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        users = UserRepository(session)
        clans = ClanRepository(session)

        owner = await users.get_or_create(telegram_id=4001, username="owner", first_name="Owner", last_name=None)
        manager = await users.get_or_create(telegram_id=4002, username="manager", first_name="Manager", last_name=None)

        clan = Clan(tag="#CLAN", name="Clan", is_tracking=True)
        session.add(clan)
        await session.flush()

        await clans.grant_role(clan.id, owner.id, ClanRole.OWNER)
        await clans.grant_role(clan.id, manager.id, ClanRole.MANAGER)
        await session.commit()

    async with session_factory() as session:
        service = ClanService(session=session, clash_client=DummyClashClient())
        result = await service.leave_access(
            actor_identity=TelegramIdentity(
                telegram_id=4002,
                username="manager",
                first_name="Manager",
                last_name=None,
            ),
            raw_tag="#CLAN",
        )

        remaining = await ClanRepository(session).list_accesses(result.clan.id)
        assert result.role == ClanRole.MANAGER
        assert result.is_unassigned is False
        assert len(remaining) == 1
        assert remaining[0].role == ClanRole.OWNER

    await engine.dispose()


@pytest.mark.asyncio
async def test_last_owner_can_leave_and_next_user_can_claim_clan() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        users = UserRepository(session)
        clans = ClanRepository(session)

        owner = await users.get_or_create(telegram_id=5001, username="owner", first_name="Owner", last_name=None)
        clan = Clan(tag="#CLAN", name="Clan", is_tracking=True)
        session.add(clan)
        await session.flush()

        await clans.grant_role(clan.id, owner.id, ClanRole.OWNER)
        await session.commit()

    async with session_factory() as session:
        service = ClanService(session=session, clash_client=OnboardingClashClient())
        leave_result = await service.leave_access(
            actor_identity=TelegramIdentity(
                telegram_id=5001,
                username="owner",
                first_name="Owner",
                last_name=None,
            ),
            raw_tag="#CLAN",
        )

        assert leave_result.role == ClanRole.OWNER
        assert leave_result.is_unassigned is True
        assert await ClanRepository(session).list_accesses(leave_result.clan.id) == []

    async with session_factory() as session:
        service = ClanService(session=session, clash_client=OnboardingClashClient())
        claim_result = await service.add_clan_or_request_access(
            TelegramIdentity(
                telegram_id=5002,
                username="new_owner",
                first_name="New Owner",
                last_name=None,
            ),
            "#CLAN",
        )

        accesses = await ClanRepository(session).list_accesses(claim_result.clan.id)
        assert claim_result.action.value == "owner_assigned"
        assert claim_result.role == ClanRole.OWNER
        assert len(accesses) == 1
        assert accesses[0].role == ClanRole.OWNER
        assert accesses[0].user.telegram_id == 5002

    await engine.dispose()


@pytest.mark.asyncio
async def test_manager_can_claim_owner_via_addclan_when_clan_has_no_owner() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        users = UserRepository(session)
        clans = ClanRepository(session)

        owner = await users.get_or_create(telegram_id=6001, username="owner", first_name="Owner", last_name=None)
        manager = await users.get_or_create(telegram_id=6002, username="manager", first_name="Manager", last_name=None)

        clan = Clan(tag="#CLAN", name="Clan", is_tracking=True)
        session.add(clan)
        await session.flush()

        await clans.grant_role(clan.id, owner.id, ClanRole.OWNER)
        await clans.grant_role(clan.id, manager.id, ClanRole.MANAGER)
        await session.commit()

    async with session_factory() as session:
        service = ClanService(session=session, clash_client=OnboardingClashClient())
        await service.leave_access(
            actor_identity=TelegramIdentity(
                telegram_id=6001,
                username="owner",
                first_name="Owner",
                last_name=None,
            ),
            raw_tag="#CLAN",
        )

    async with session_factory() as session:
        service = ClanService(session=session, clash_client=OnboardingClashClient())
        result = await service.add_clan_or_request_access(
            TelegramIdentity(
                telegram_id=6002,
                username="manager",
                first_name="Manager",
                last_name=None,
            ),
            "#CLAN",
        )

        accesses = await ClanRepository(session).list_accesses(result.clan.id)
        assert result.action.value == "owner_assigned"
        assert result.role == ClanRole.OWNER
        assert len(accesses) == 1
        assert accesses[0].role == ClanRole.OWNER
        assert accesses[0].user.telegram_id == 6002

    await engine.dispose()


@pytest.mark.asyncio
async def test_outsider_can_create_manager_request_when_clan_has_managers_but_no_owner() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        users = UserRepository(session)
        clans = ClanRepository(session)

        owner = await users.get_or_create(telegram_id=7001, username="owner", first_name="Owner", last_name=None)
        manager = await users.get_or_create(telegram_id=7002, username="manager", first_name="Manager", last_name=None)

        clan = Clan(tag="#CLAN", name="Clan", is_tracking=True)
        session.add(clan)
        await session.flush()

        await clans.grant_role(clan.id, owner.id, ClanRole.OWNER)
        await clans.grant_role(clan.id, manager.id, ClanRole.MANAGER)
        await session.commit()

    async with session_factory() as session:
        service = ClanService(session=session, clash_client=OnboardingClashClient())
        await service.leave_access(
            actor_identity=TelegramIdentity(
                telegram_id=7001,
                username="owner",
                first_name="Owner",
                last_name=None,
            ),
            raw_tag="#CLAN",
        )

    async with session_factory() as session:
        service = ClanService(session=session, clash_client=OnboardingClashClient())
        result = await service.add_clan_or_request_access(
            TelegramIdentity(
                telegram_id=7003,
                username="outsider",
                first_name="Outsider",
                last_name=None,
            ),
            "#CLAN",
        )

        overview = await service.list_roles("#CLAN")
        assert result.action.value == "access_request_created"
        assert result.access_request is not None
        assert overview is not None
        assert len(overview.pending_requests) == 1

    await engine.dispose()


class OnboardingClashClient:
    async def get_clan(self, clan_tag: str):
        return {"tag": clan_tag, "name": "Clan"}

    async def get_clan_members(self, clan_tag: str):
        from app.integrations.clash.schemas import ClanMember

        return [
            ClanMember(tag="#P1", name="Member One"),
            ClanMember(tag="#P2", name="Member Two"),
        ]


@pytest.mark.asyncio
async def test_first_owner_assignment_sets_newbie_baseline_automatically() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        service = ClanService(session=session, clash_client=OnboardingClashClient())
        result = await service.add_clan_or_request_access(
            TelegramIdentity(
                telegram_id=2001,
                username="owner",
                first_name="Owner",
                last_name=None,
            ),
            "#CLAN",
        )
        clan = await ClanRepository(session).get_by_tag("#CLAN")

        assert clan is not None
        assert result.clan.tag == "#CLAN"
        assert clan.newbie_baseline_at is not None
        assert clan.newbie_baseline_at.tzinfo is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_manager_can_set_player_note_for_clan_member() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        users = UserRepository(session)
        clans = ClanRepository(session)
        players = PlayerRepository(session)

        owner = await users.get_or_create(telegram_id=3001, username="owner", first_name="Owner", last_name=None)
        manager = await users.get_or_create(telegram_id=3002, username="manager", first_name="Manager", last_name=None)
        clan = Clan(tag="#CLAN", name="Clan", is_tracking=True)
        session.add(clan)
        await session.flush()

        await clans.grant_role(clan.id, owner.id, ClanRole.OWNER)
        await clans.grant_role(clan.id, manager.id, ClanRole.MANAGER)

        now = datetime.now(UTC)
        player = await players.get_or_create(tag="#P1", name="Player One", now=now)
        await players.upsert_state(clan_id=clan.id, player_id=player.id, now=now, is_current_member=True)
        await session.commit()

    async with session_factory() as session:
        service = ClanService(session=session, clash_client=DummyClashClient())
        manager_identity = TelegramIdentity(
            telegram_id=3002,
            username="manager",
            first_name="Manager",
            last_name=None,
        )

        result = await service.set_player_note(
            actor_identity=manager_identity,
            raw_clan_tag="#CLAN",
            raw_player_tag="#P1",
            note="Опытный игрок, не трогать",
            is_superadmin=False,
        )

        assert result.clan.tag == "#CLAN"
        assert result.player_tag == "#P1"
        assert result.player_name == "Player One"
        assert result.note == "Опытный игрок, не трогать"

    await engine.dispose()
