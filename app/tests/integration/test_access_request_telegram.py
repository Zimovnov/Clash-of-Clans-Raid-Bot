from datetime import UTC, datetime

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.filters import CommandObject
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageText,
    SendMessage,
    SetMyCommands,
)
from aiogram.types import CallbackQuery, Chat, Message, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.i18n import t
from app.db.models import (
    Base,
    Clan,
    ClanAccessRequest,
    ClanAccessRequestStatus,
    ClanRole,
    UserLanguage,
)
from app.db.repositories import ClanRepository, UserRepository
from app.integrations.telegram import command_menu
from app.integrations.telegram.handlers import clans

TAG = "#2PP"


class RecordingSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.messages = []

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, (SendMessage, EditMessageText)):
            message = Message(
                message_id=getattr(method, "message_id", None) or len(self.messages) + 1,
                date=datetime.now(UTC),
                chat=Chat(id=method.chat_id, type="private"),
                text=method.text,
                reply_markup=method.reply_markup,
            ).as_(bot)
            self.messages.append(message)
            return message
        if isinstance(method, (SetMyCommands, AnswerCallbackQuery)):
            return True
        raise AssertionError(f"Unexpected Telegram method: {type(method).__name__}")

    async def stream_content(self, *args, **kwargs):
        raise AssertionError("No downloads are allowed in request tests")
        yield b""


def incoming(bot, user):
    return Message(
        message_id=1, date=datetime.now(UTC), chat=Chat(id=user.id, type="private"),
        from_user=user, text=f"/addclan {TAG}",
    ).as_(bot)


def callback(bot, user, message, data):
    return CallbackQuery(
        id=f"callback-{len(bot.session.calls)}", from_user=user,
        chat_instance="test", message=message, data=data,
    ).as_(bot)


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["en", "ru"])
@pytest.mark.parametrize("decision", ["approve", "reject"])
async def test_request_notification_buttons_and_decision(monkeypatch, lang, decision):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    transport = RecordingSession()
    bot = Bot(token="42:TEST", session=transport)
    owner = User(id=2001, is_bot=False, first_name="Owner", username="owner")
    guest = User(id=2002, is_bot=False, first_name="Guest", username="guest")
    monkeypatch.setenv("SUPERADMIN_TELEGRAM_IDS", "")
    monkeypatch.setattr(clans, "AsyncSessionFactory", sessions)
    monkeypatch.setattr(command_menu, "AsyncSessionFactory", sessions)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            clan = Clan(tag=TAG, name="Test Clan")
            session.add(clan)
            users = UserRepository(session)
            user = await users.get_or_create(owner.id, owner.username, owner.first_name, None)
            await users.set_language(owner.id, UserLanguage(lang))
            await users.get_or_create(guest.id, guest.username, guest.first_name, None)
            await users.set_language(guest.id, UserLanguage(lang))
            await ClanRepository(session).grant_role(clan.id, user.id, ClanRole.OWNER)
            await session.commit()

        command = CommandObject(command="addclan", args=TAG)
        await clans.cmd_add_clan(incoming(bot, guest), command, bot, lang)
        owner_notifications = [message for message in transport.messages if message.chat.id == owner.id]
        assert len(owner_notifications) == 1
        notification = owner_notifications[0]
        assert notification.reply_markup is not None

        await clans.cmd_add_clan(incoming(bot, guest), command, bot, lang)
        assert len([message for message in transport.messages if message.chat.id == owner.id]) == 1
        async with sessions() as session:
            requests = list((await session.scalars(select(ClanAccessRequest))).all())
            assert len(requests) == 1
            request_id = requests[0].id

        await clans.cmd_requests(incoming(bot, owner), CommandObject(command="requests", args=TAG), lang)
        listing = transport.messages[-1]
        open_data = listing.reply_markup.inline_keyboard[0][0].callback_data
        await clans.cb_access_request_open(callback(bot, owner, listing, open_data), lang)
        review = transport.messages[-1]
        decision_data = next(
            button.callback_data for row in review.reply_markup.inline_keyboard for button in row
            if button.callback_data.startswith(f"access_request_{decision}:")
        )
        decide = getattr(clans, f"cb_access_request_{decision}")
        await decide(callback(bot, owner, review, decision_data), bot, lang)
        resolution = [method for method in transport.calls if isinstance(method, EditMessageText)][-1]
        assert owner.first_name in resolution.text
        expected = ClanAccessRequestStatus.APPROVED if decision == "approve" else ClanAccessRequestStatus.REJECTED
        async with sessions() as session:
            request = await session.get(ClanAccessRequest, request_id)
            assert request.status == expected
            access = await ClanRepository(session).get_access(request.clan_id, request.user_id)
            assert (access.role if access else None) == (ClanRole.MANAGER if decision == "approve" else None)

        notice_key = "requests.approved_notify" if decision == "approve" else "requests.rejected_notify"
        assert any(
            isinstance(method, SendMessage) and method.chat_id == guest.id
            and method.text == t(lang, notice_key, name="Test Clan", tag=TAG)
            for method in transport.calls
        )
        before = len([method for method in transport.calls if isinstance(method, SendMessage)])
        await decide(callback(bot, owner, review, decision_data), bot, lang)
        assert len([method for method in transport.calls if isinstance(method, SendMessage)]) == before
        assert transport.calls[-1].text == t(lang, "requests.already_handled")
    finally:
        await bot.session.close()
        await engine.dispose()
