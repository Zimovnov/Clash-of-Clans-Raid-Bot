from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base, Player
from app.services.player_profile_service import PlayerProfileService


class FakeClashClient:
    async def get_player_profile(self, player_tag: str):
        from app.integrations.clash.schemas import PlayerProfileData

        return PlayerProfileData(
            tag=player_tag,
            name="Player",
            exp_level=222,
            town_hall_level=16,
            builder_hall_level=10,
            league_name="Legend League",
            clan_role="member",
            raw={"tag": player_tag},
        )


@pytest.mark.asyncio
async def test_profile_is_loaded_automatically_when_missing() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        player = Player(tag="#P1", name="Player")
        session.add(player)
        await session.commit()
        await session.refresh(player)

        service = PlayerProfileService(session=session, clash_client=FakeClashClient())
        result = await service.get_for_player(player, refresh_if_missing=True, force_refresh=False)

        assert result.refreshed is True
        assert result.profile is not None
        assert result.profile.exp_level == 222
        assert result.profile.town_hall_level == 16
        assert result.profile.league_name == "Legend League"

    await engine.dispose()


def test_profile_stale_detection_uses_24_hours() -> None:
    refreshed_at = datetime.now(UTC) - timedelta(hours=25)
    fresh_profile = type("Profile", (), {"refreshed_at": datetime.now(UTC)})()
    stale_profile = type("Profile", (), {"refreshed_at": refreshed_at})()

    assert PlayerProfileService.is_stale(fresh_profile) is False
    assert PlayerProfileService.is_stale(stale_profile) is True
