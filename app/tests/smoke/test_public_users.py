from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from aiogram import Bot
from aiogram.methods import AnswerCallbackQuery, SetMyCommands
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.i18n import t
from app.db.models import (
    Base,
    ClanAccessRequest,
    ClanAccessRequestStatus,
    ClanRole,
    RaidReport,
)
from app.db.repositories import ClanRepository, ReportRepository, UserRepository
from app.integrations.clash.schemas import (
    ClanMember,
    PlayerProfileData,
    RaidMemberStats,
    RaidSeason,
)
from app.integrations.telegram import command_menu
from app.integrations.telegram.handlers import admin, clans, common, reports
from app.integrations.telegram.middlewares import language
from app.tests.integration.test_access_request_telegram import RecordingSession

PRIMARY = "#2PP"
OTHER = "#2QQ"


class FakeClash:
    def __init__(self):
        self.calls = []
        self.end = datetime.now(UTC) - timedelta(days=1)

    async def get_clan(self, tag):
        self.calls.append(("clan", tag))
        return {"tag": tag, "name": "Primary Clan" if tag == PRIMARY else "Other Clan"}

    async def get_clan_members(self, tag):
        self.calls.append(("members", tag))
        return [ClanMember("#P1", "Player One")]

    async def get_latest_raid_season(self, tag):
        self.calls.append(("raid", tag))
        return RaidSeason(self.end - timedelta(days=3), self.end, [RaidMemberStats("#P1", "Player One", 0)], {})

    async def get_player_profile(self, tag):
        self.calls.append(("profile", tag))
        return PlayerProfileData(tag, "Player One", 100, 16, 10, "Gold", "member", {})


@pytest_asyncio.fixture
async def public_users(monkeypatch, dispatcher):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    for module in [common, clans, reports, admin, command_menu, language]:
        monkeypatch.setattr(module, "AsyncSessionFactory", sessions)
    api = FakeClash()
    for module in [clans, reports, admin]:
        monkeypatch.setattr(module, "ClashApiClient", lambda: api)
    monkeypatch.setenv("SUPERADMIN_TELEGRAM_IDS", "")
    transport = RecordingSession()
    bot = Bot(token="42:TEST", session=transport)
    owner = User(id=3001, is_bot=False, first_name="Owner", username="owner")
    guest = User(id=3002, is_bot=False, first_name="New user", username=None)
    outsider = User(id=3003, is_bot=False, first_name="Other owner", username="other")
    update_id = 0

    async def send(user, text):
        nonlocal update_id
        update_id += 1
        message = Message(message_id=update_id, date=datetime.now(UTC), chat=Chat(id=user.id, type="private"), from_user=user, text=text)
        await dispatcher.feed_update(bot, Update(update_id=update_id, message=message))
        return transport.messages[-1]

    async def click(user, message, data):
        nonlocal update_id
        update_id += 1
        event = CallbackQuery(id=str(update_id), from_user=user, chat_instance="public-users", message=message, data=data)
        await dispatcher.feed_update(bot, Update(update_id=update_id, callback_query=event))

    try:
        yield SimpleNamespace(sessions=sessions, api=api, transport=transport, bot=bot, owner=owner, guest=guest, outsider=outsider, send=send, click=click)
    finally:
        await bot.session.close()
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["en", "ru"])
async def test_fresh_regular_users_complete_onboarding_and_access(public_users, lang):
    ctx = public_users
    for user in [ctx.owner, ctx.guest, ctx.outsider]:
        assert (await ctx.send(user, "/start")).text == t("en", "common.start")
        if lang == "ru":
            await ctx.send(user, "/russian")
        menus = [call for call in ctx.transport.calls if isinstance(call, SetMyCommands) and call.scope.chat_id == user.id]
        assert "transfer_owner" not in {item.command for item in menus[-1].commands}
    assert (await ctx.send(ctx.guest, "/myclans")).text == t(lang, "clan.none")
    await ctx.send(ctx.owner, f"/addclan {PRIMARY}")
    await ctx.send(ctx.outsider, f"/addclan {OTHER}")
    assert (await ctx.send(ctx.guest, f"/report {PRIMARY}")).text == t(lang, "report.no_clans")
    assert (await ctx.send(ctx.guest, f"/requests {PRIMARY}")).text == t(lang, "requests.section_denied")
    assert (await ctx.send(ctx.guest, f"/transfer_owner {PRIMARY} {ctx.guest.id}")).text == t(lang, "admin.superadmin_only")
    await ctx.send(ctx.guest, f"/addclan {PRIMARY}")
    notification = next(message for message in reversed(ctx.transport.messages) if message.chat.id == ctx.owner.id)
    approve = notification.reply_markup.inline_keyboard[0][0].callback_data
    await ctx.click(ctx.guest, notification, approve)
    async with ctx.sessions() as session:
        request = (await session.scalars(select(ClanAccessRequest))).one()
        assert request.status == ClanAccessRequestStatus.PENDING
    await ctx.click(ctx.owner, notification, approve)
    listing = await ctx.send(ctx.guest, "/myclans")
    assert "Primary Clan" in listing.text and "Other Clan" not in listing.text
    report_message = await ctx.send(ctx.guest, f"/report {PRIMARY}")
    assert "Primary Clan" in report_message.text
    assert report_message.reply_markup is not None
    async with ctx.sessions() as session:
        clan = await ClanRepository(session).get_by_tag(PRIMARY)
        saved_report = await ReportRepository(session).latest_for_clan(clan.id)
        category = saved_report.players[0].category.value
    category_data = next(
        button.callback_data for row in report_message.reply_markup.inline_keyboard for button in row
        if button.callback_data.startswith("report_cat:") and f":{category}:" in button.callback_data
    )
    await ctx.click(ctx.guest, report_message, category_data)
    category_message = ctx.transport.messages[-1]
    player_data = next(
        button.callback_data for row in category_message.reply_markup.inline_keyboard for button in row
        if button.callback_data.startswith("report_player:")
    )
    await ctx.click(ctx.guest, category_message, player_data)
    player_message = ctx.transport.messages[-1]
    assert "Player One" in player_message.text
    refresh_data = next(
        button.callback_data for row in player_message.reply_markup.inline_keyboard for button in row
        if button.callback_data.startswith("report_player_refresh:")
    )
    await ctx.click(ctx.guest, player_message, refresh_data)
    assert ctx.api.calls.count(("profile", "#P1")) == 2
    assert (await ctx.send(ctx.guest, f"/report {OTHER}")).text == t(lang, "report.no_access_clan")
    async with ctx.sessions() as session:
        user = await UserRepository(session).get_by_telegram_id(ctx.guest.id)
        clan = await ClanRepository(session).get_by_tag(PRIMARY)
        assert user.username is None
        assert user.language.value == lang
        assert (await ClanRepository(session).get_access(clan.id, user.id)).role == ClanRole.MANAGER
        report = await ReportRepository(session).latest_for_clan(clan.id)
        assert report is not None and len(report.players) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["report_cat", "report_player", "report_player_refresh"])
async def test_own_clan_tag_cannot_unlock_another_clans_report(public_users, prefix):
    ctx = public_users
    await ctx.send(ctx.owner, "/start")
    await ctx.send(ctx.outsider, "/start")
    await ctx.send(ctx.owner, f"/addclan {PRIMARY}")
    await ctx.send(ctx.outsider, f"/addclan {OTHER}")
    message = await ctx.send(ctx.outsider, f"/report {OTHER}")
    async with ctx.sessions() as session:
        foreign_report = (await session.scalars(select(RaidReport))).one()
        loaded = await ReportRepository(session).get_by_id(foreign_report.id)
        report_id, row_id = loaded.id, loaded.players[0].id
    suffix = f"{PRIMARY}:{report_id}:newbie:1"
    if prefix != "report_cat":
        suffix += f":{row_id}"
    before_messages = len(ctx.transport.messages)
    before_api = len(ctx.api.calls)
    await ctx.click(ctx.owner, message, f"{prefix}:{suffix}")
    assert len(ctx.transport.messages) == before_messages
    assert len(ctx.api.calls) == before_api
    assert isinstance(ctx.transport.calls[-1], AnswerCallbackQuery)
    assert ctx.transport.calls[-1].text == t("en", "general.report_not_found")
