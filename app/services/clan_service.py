from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tags import normalize_tag
from app.db.models import Clan, ClanAccess, ClanAccessRequest, ClanAccessRequestStatus, ClanRole, User
from app.db.repositories import AccessRequestRepository, ClanRepository, PlayerRepository, UserRepository
from app.integrations.clash.client import ClashApiClient
from app.services.clan_sync_service import ClanSyncService


class ClanServiceError(Exception):
    pass


class ClanAccessDeniedError(ClanServiceError):
    pass


class ClanPermissionDeniedError(ClanServiceError):
    pass


class ClanAccessRequestNotFoundError(ClanServiceError):
    pass


class ClanAccessRequestAlreadyHandledError(ClanServiceError):
    pass


class ClanAccessRequestAction(str, Enum):
    OWNER_ASSIGNED = "owner_assigned"
    ACCESS_ALREADY_EXISTS = "access_already_exists"
    ACCESS_REQUEST_CREATED = "access_request_created"
    ACCESS_REQUEST_PENDING = "access_request_pending"


@dataclass(slots=True)
class TelegramIdentity:
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None


@dataclass(slots=True)
class AddClanResult:
    clan: Clan
    action: ClanAccessRequestAction
    role: ClanRole | None = None
    access_request: ClanAccessRequest | None = None


@dataclass(slots=True)
class RoleOverview:
    clan: Clan
    accesses: list[ClanAccess]
    pending_requests: list[ClanAccessRequest]


@dataclass(slots=True)
class PlayerNoteResult:
    clan: Clan
    player_tag: str
    player_name: str
    note: str | None


@dataclass(slots=True)
class LeaveAccessResult:
    clan: Clan
    role: ClanRole
    is_unassigned: bool


class ClanService:
    def __init__(self, session: AsyncSession, clash_client: ClashApiClient) -> None:
        self.session = session
        self.clash_client = clash_client
        self.users = UserRepository(session)
        self.clans = ClanRepository(session)
        self.players = PlayerRepository(session)
        self.access_requests = AccessRequestRepository(session)

    async def ensure_user(self, identity: TelegramIdentity) -> User:
        return await self.users.get_or_create(
            telegram_id=identity.telegram_id,
            username=identity.username,
            first_name=identity.first_name,
            last_name=identity.last_name,
        )

    async def add_clan_or_request_access(self, identity: TelegramIdentity, raw_tag: str) -> AddClanResult:
        user = await self.ensure_user(identity)
        clan_tag = normalize_tag(raw_tag)

        clan = await self.clans.get_by_tag(clan_tag)
        if clan is None:
            clan_payload = await self.clash_client.get_clan(clan_tag)
            clan_name = str(clan_payload.get("name", clan_tag)).strip() or clan_tag
            clan = await self.clans.create(tag=clan_tag, name=clan_name)
            await self.clans.grant_role(clan_id=clan.id, user_id=user.id, role=ClanRole.OWNER)
            await self._bootstrap_newbie_baseline(clan)
            await self.session.commit()
            return AddClanResult(clan=clan, action=ClanAccessRequestAction.OWNER_ASSIGNED, role=ClanRole.OWNER)

        accesses = await self.clans.list_accesses(clan.id)
        has_owner = any(item.role == ClanRole.OWNER for item in accesses)
        access = await self.clans.get_access(clan_id=clan.id, user_id=user.id)
        if access:
            if access.role != ClanRole.OWNER and not has_owner:
                await self.clans.grant_role(clan_id=clan.id, user_id=user.id, role=ClanRole.OWNER)
                await self.session.commit()
                return AddClanResult(clan=clan, action=ClanAccessRequestAction.OWNER_ASSIGNED, role=ClanRole.OWNER)
            await self.session.commit()
            return AddClanResult(clan=clan, action=ClanAccessRequestAction.ACCESS_ALREADY_EXISTS, role=access.role)

        if not accesses:
            await self.clans.grant_role(clan_id=clan.id, user_id=user.id, role=ClanRole.OWNER)
            await self._bootstrap_newbie_baseline(clan)
            await self.session.commit()
            return AddClanResult(clan=clan, action=ClanAccessRequestAction.OWNER_ASSIGNED, role=ClanRole.OWNER)

        pending_request = await self.access_requests.get_pending_for_user(clan.id, user.id)
        if pending_request:
            await self.session.commit()
            return AddClanResult(
                clan=clan,
                action=ClanAccessRequestAction.ACCESS_REQUEST_PENDING,
                access_request=pending_request,
            )

        access_request = await self.access_requests.create(
            clan_id=clan.id,
            user_id=user.id,
            requested_role=ClanRole.MANAGER,
        )
        await self.session.commit()
        stored_request = await self.access_requests.get_by_id(access_request.id)
        return AddClanResult(
            clan=clan,
            action=ClanAccessRequestAction.ACCESS_REQUEST_CREATED,
            access_request=stored_request or access_request,
        )

    async def list_user_clans(self, identity: TelegramIdentity) -> list[Clan]:
        user = await self.ensure_user(identity)
        return await self.clans.list_for_user(user.id)

    async def get_user_clan_access(self, identity: TelegramIdentity, raw_tag: str) -> tuple[Clan | None, ClanAccess | None]:
        user = await self.ensure_user(identity)
        clan = await self.clans.get_by_tag(normalize_tag(raw_tag))
        if clan is None:
            return None, None
        access = await self.clans.get_access(clan.id, user.id)
        return clan, access

    async def list_roles(self, raw_tag: str) -> RoleOverview | None:
        clan = await self.clans.get_by_tag(normalize_tag(raw_tag))
        if clan is None:
            return None
        return RoleOverview(
            clan=clan,
            accesses=await self.clans.list_accesses(clan.id),
            pending_requests=await self.access_requests.list_pending_for_clan(clan.id),
        )

    async def list_owners(self, clan_id: int) -> list[ClanAccess]:
        return await self.clans.list_accesses_by_role(clan_id, ClanRole.OWNER)

    async def get_access_request(self, request_id: int) -> ClanAccessRequest | None:
        return await self.access_requests.get_by_id(request_id)

    async def approve_access_request(
        self,
        actor_identity: TelegramIdentity,
        request_id: int,
        is_superadmin: bool = False,
    ) -> ClanAccessRequest:
        actor = await self.ensure_user(actor_identity)
        request = await self.access_requests.get_by_id(request_id)
        if request is None:
            raise ClanAccessRequestNotFoundError("Заявка не найдена")
        if request.status != ClanAccessRequestStatus.PENDING:
            raise ClanAccessRequestAlreadyHandledError("Заявка уже обработана")

        await self._ensure_request_reviewer_or_superadmin(actor.id, request.clan_id, is_superadmin)
        await self.clans.grant_role(request.clan_id, request.user_id, request.requested_role)
        await self.access_requests.resolve_for_user(
            clan_id=request.clan_id,
            user_id=request.user_id,
            status=ClanAccessRequestStatus.APPROVED,
            resolved_by_user_id=actor.id,
            resolved_at=datetime.now(UTC),
        )
        await self.session.commit()

        refreshed = await self.access_requests.get_by_id(request_id)
        if refreshed is None:
            raise ClanAccessRequestNotFoundError("Заявка не найдена после одобрения")
        return refreshed

    async def reject_access_request(
        self,
        actor_identity: TelegramIdentity,
        request_id: int,
        is_superadmin: bool = False,
    ) -> ClanAccessRequest:
        actor = await self.ensure_user(actor_identity)
        request = await self.access_requests.get_by_id(request_id)
        if request is None:
            raise ClanAccessRequestNotFoundError("Заявка не найдена")
        if request.status != ClanAccessRequestStatus.PENDING:
            raise ClanAccessRequestAlreadyHandledError("Заявка уже обработана")

        await self._ensure_request_reviewer_or_superadmin(actor.id, request.clan_id, is_superadmin)
        await self.access_requests.resolve_for_user(
            clan_id=request.clan_id,
            user_id=request.user_id,
            status=ClanAccessRequestStatus.REJECTED,
            resolved_by_user_id=actor.id,
            resolved_at=datetime.now(UTC),
        )
        await self.session.commit()

        refreshed = await self.access_requests.get_by_id(request_id)
        if refreshed is None:
            raise ClanAccessRequestNotFoundError("Заявка не найдена после отклонения")
        return refreshed

    async def grant_manager(
        self,
        actor_identity: TelegramIdentity,
        raw_tag: str,
        telegram_id: int,
        is_superadmin: bool = False,
    ) -> tuple[Clan, User]:
        actor = await self.ensure_user(actor_identity)
        clan = await self._get_clan_or_raise(raw_tag)
        await self._ensure_owner_or_superadmin(actor.id, clan.id, is_superadmin)

        target_user = await self.users.get_by_telegram_id(telegram_id)
        if target_user is None:
            target_user = await self.users.get_or_create(
                telegram_id=telegram_id,
                username=None,
                first_name=None,
                last_name=None,
            )

        current_access = await self.clans.get_access(clan.id, target_user.id)
        if current_access is not None and current_access.role == ClanRole.OWNER:
            raise ClanServiceError("Нельзя изменить владельца через /grant_manager. Используйте /transfer_owner")

        await self.clans.grant_role(clan.id, target_user.id, ClanRole.MANAGER)
        await self.access_requests.resolve_for_user(
            clan_id=clan.id,
            user_id=target_user.id,
            status=ClanAccessRequestStatus.APPROVED,
            resolved_by_user_id=actor.id,
            resolved_at=datetime.now(UTC),
        )
        await self.session.commit()
        return clan, target_user

    async def revoke_access(
        self,
        actor_identity: TelegramIdentity,
        raw_tag: str,
        telegram_id: int,
        is_superadmin: bool = False,
    ) -> tuple[Clan, User]:
        actor = await self.ensure_user(actor_identity)
        clan = await self._get_clan_or_raise(raw_tag)
        await self._ensure_owner_or_superadmin(actor.id, clan.id, is_superadmin)

        target_user = await self.users.get_by_telegram_id(telegram_id)
        if target_user is None:
            raise ClanServiceError("Пользователь не найден")

        current_access = await self.clans.get_access(clan.id, target_user.id)
        if current_access is None:
            raise ClanServiceError("У пользователя нет доступа к этому клану")
        if current_access.role == ClanRole.OWNER:
            raise ClanServiceError("Доступ владельца нельзя отзывать через /revoke_access. Используйте /transfer_owner")

        await self.clans.revoke_access(clan.id, target_user.id)
        await self.session.commit()
        return clan, target_user

    async def leave_access(
        self,
        actor_identity: TelegramIdentity,
        raw_tag: str,
    ) -> LeaveAccessResult:
        actor = await self.ensure_user(actor_identity)
        clan = await self._get_clan_or_raise(raw_tag)

        current_access = await self.clans.get_access(clan.id, actor.id)
        if current_access is None:
            raise ClanServiceError("Для этого клана нет прямого доступа, который можно снять")

        await self.clans.revoke_access(clan.id, actor.id)
        remaining_accesses = await self.clans.list_accesses(clan.id)
        await self.session.commit()

        return LeaveAccessResult(
            clan=clan,
            role=current_access.role,
            is_unassigned=len(remaining_accesses) == 0,
        )

    async def transfer_owner(self, raw_tag: str, telegram_id: int) -> Clan:
        clan_tag = normalize_tag(raw_tag)
        clan = await self.clans.get_by_tag(clan_tag)
        if clan is None:
            raise ClanServiceError("Клан не найден")

        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            user = await self.users.get_or_create(
                telegram_id=telegram_id,
                username=None,
                first_name=None,
                last_name=None,
            )
        await self.clans.transfer_owner(clan_id=clan.id, new_owner_user_id=user.id)
        await self.session.commit()
        return clan

    async def set_player_note(
        self,
        actor_identity: TelegramIdentity,
        raw_clan_tag: str,
        raw_player_tag: str,
        note: str | None,
        is_superadmin: bool = False,
    ) -> PlayerNoteResult:
        actor = await self.ensure_user(actor_identity)
        clan = await self._get_clan_or_raise(raw_clan_tag)
        await self._ensure_clan_access(actor_user_id=actor.id, clan_id=clan.id, is_superadmin=is_superadmin)

        player_tag = normalize_tag(raw_player_tag)
        state = await self.players.set_manager_note(clan_id=clan.id, player_tag=player_tag, note=note)
        if state is None or state.player is None:
            raise ClanServiceError("Игрок не найден в составе или истории клана")

        await self.session.commit()
        return PlayerNoteResult(
            clan=clan,
            player_tag=state.player.tag,
            player_name=state.player.name,
            note=state.manager_note,
        )

    async def _get_clan_or_raise(self, raw_tag: str) -> Clan:
        clan = await self.clans.get_by_tag(normalize_tag(raw_tag))
        if clan is None:
            raise ClanServiceError("Клан не найден")
        return clan

    async def _bootstrap_newbie_baseline(self, clan: Clan) -> None:
        if clan.newbie_baseline_at is not None:
            return
        snapshot = await ClanSyncService(self.session, self.clash_client).sync_clan(clan.tag)
        clan.newbie_baseline_at = snapshot.taken_at

    async def _ensure_clan_access(self, actor_user_id: int, clan_id: int, is_superadmin: bool) -> None:
        if is_superadmin:
            return
        access = await self.clans.get_access(clan_id, actor_user_id)
        if access is None:
            raise ClanAccessDeniedError("У вас нет доступа к этому клану")

    async def _ensure_owner_or_superadmin(self, actor_user_id: int, clan_id: int, is_superadmin: bool) -> None:
        await self._ensure_clan_access(actor_user_id=actor_user_id, clan_id=clan_id, is_superadmin=is_superadmin)
        access = await self.clans.get_access(clan_id, actor_user_id)
        if access is None or access.role != ClanRole.OWNER:
            raise ClanPermissionDeniedError("Только owner или superadmin могут управлять доступом")

    async def _ensure_request_reviewer_or_superadmin(self, actor_user_id: int, clan_id: int, is_superadmin: bool) -> None:
        await self._ensure_clan_access(actor_user_id=actor_user_id, clan_id=clan_id, is_superadmin=is_superadmin)
        access = await self.clans.get_access(clan_id, actor_user_id)
        if access is None:
            raise ClanPermissionDeniedError("Только owner или superadmin могут управлять доступом")
        if access.role == ClanRole.OWNER:
            return
        if access.role == ClanRole.MANAGER:
            owners = await self.clans.list_accesses_by_role(clan_id, ClanRole.OWNER)
            if not owners:
                return
        raise ClanPermissionDeniedError("Только owner или superadmin могут управлять доступом")
