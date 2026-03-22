from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.tags import tag_for_url
from app.integrations.clash.schemas import ClanMember, PlayerProfileData, RaidMemberStats, RaidSeason, parse_clash_time

logger = logging.getLogger(__name__)


class ClashApiError(Exception):
    pass


class ClashApiForbidden(ClashApiError):
    pass


class ClashApiRateLimited(ClashApiError):
    pass


class ClashApiUnavailable(ClashApiError):
    pass


def _extract_league_name(payload: dict[str, Any]) -> str | None:
    league_tier = payload.get("leagueTier") or {}
    if league_tier.get("name"):
        return str(league_tier.get("name")).strip() or None

    league = payload.get("league") or {}
    if league.get("name"):
        return str(league.get("name")).strip() or None

    return None


class ClashApiClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.clash_api_base_url.rstrip("/")
        self._token = settings.clash_api_token
        self._timeout = httpx.Timeout(20.0)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }

    async def _request_json(self, method: str, path: str) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(method, url, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise ClashApiUnavailable("Clash API request timed out") from exc
        except httpx.HTTPError as exc:
            raise ClashApiUnavailable("Failed to reach Clash API") from exc

        if response.status_code == 403:
            raise ClashApiForbidden("Clash API forbidden (check IP whitelist/token)")
        if response.status_code == 429:
            raise ClashApiRateLimited("Clash API rate limited")
        if response.status_code >= 500:
            raise ClashApiUnavailable(f"Clash API temporary unavailable: {response.status_code}")
        if response.status_code >= 400:
            raise ClashApiError(f"Clash API error: {response.status_code}")

        try:
            return response.json()
        except ValueError as exc:
            raise ClashApiError("Clash API returned invalid JSON") from exc

    async def get_clan(self, clan_tag: str) -> dict[str, Any]:
        encoded_tag = tag_for_url(clan_tag)
        return await self._request_json("GET", f"/clans/{encoded_tag}")

    async def get_clan_members(self, clan_tag: str) -> list[ClanMember]:
        payload = await self.get_clan(clan_tag)
        members_raw = payload.get("memberList", [])
        members: list[ClanMember] = []
        for member in members_raw:
            tag = str(member.get("tag", "")).strip()
            name = str(member.get("name", "Unknown")).strip() or "Unknown"
            if not tag:
                continue
            members.append(ClanMember(tag=tag, name=name))
        return members

    async def get_latest_raid_season(self, clan_tag: str) -> RaidSeason | None:
        encoded_tag = tag_for_url(clan_tag)
        payload = await self._request_json("GET", f"/clans/{encoded_tag}/capitalraidseasons?limit=1")
        items = payload.get("items", [])
        if not items:
            return None

        item = items[0]
        start_time = parse_clash_time(item.get("startTime"))
        end_time = parse_clash_time(item.get("endTime"))
        members_raw = item.get("members", [])

        members: list[RaidMemberStats] = []
        for m in members_raw:
            member_tag = str(m.get("tag", "")).strip()
            member_name = str(m.get("name", "Unknown")).strip() or "Unknown"
            attacks = int(m.get("attacks", 0) or 0)
            if not member_tag:
                continue
            members.append(RaidMemberStats(tag=member_tag, name=member_name, attacks=attacks))

        return RaidSeason(start_time=start_time, end_time=end_time, members=members, raw=item)

    async def get_player_profile(self, player_tag: str) -> PlayerProfileData:
        encoded_tag = tag_for_url(player_tag)
        payload = await self._request_json("GET", f"/players/{encoded_tag}")

        role = payload.get("role")
        role_value = str(role).strip() if role is not None else None

        return PlayerProfileData(
            tag=str(payload.get("tag", player_tag)).strip() or player_tag,
            name=str(payload.get("name", "Unknown")).strip() or "Unknown",
            exp_level=int(payload.get("expLevel")) if payload.get("expLevel") is not None else None,
            town_hall_level=(
                int(payload.get("townHallLevel"))
                if payload.get("townHallLevel") is not None
                else None
            ),
            builder_hall_level=(
                int(payload.get("builderHallLevel"))
                if payload.get("builderHallLevel") is not None
                else None
            ),
            league_name=_extract_league_name(payload),
            clan_role=role_value or None,
            raw=payload,
        )
