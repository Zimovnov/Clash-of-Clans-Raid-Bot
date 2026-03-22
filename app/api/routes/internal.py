from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.tags import TagNormalizationError, normalize_tag
from app.db.models import ReportSource
from app.db.repositories import ClanRepository, PlayerRepository, ReportRepository, SnapshotRepository
from app.integrations.clash.client import ClashApiClient, ClashApiError, ClashApiForbidden, ClashApiRateLimited, ClashApiUnavailable
from app.services.clan_sync_service import ClanSyncService
from app.services.report_builder import ReportBuildError, ReportBuilderService

router = APIRouter(prefix="/internal", tags=["internal"])
logger = logging.getLogger(__name__)


class SyncClanRequest(BaseModel):
    tag: str = Field(min_length=2)


class BuildReportRequest(BaseModel):
    tag: str = Field(min_length=2)
    force_rebuild: bool = False


def _raise_clash_http_error(exc: ClashApiError) -> None:
    if isinstance(exc, ClashApiForbidden):
        raise HTTPException(
            status_code=502,
            detail="Clash API returned 403. Check allowed IP addresses and CLASH_API_TOKEN.",
        ) from exc
    if isinstance(exc, ClashApiRateLimited):
        raise HTTPException(status_code=503, detail="Clash API rate limited the request.") from exc
    if isinstance(exc, ClashApiUnavailable):
        raise HTTPException(status_code=503, detail="Clash API is temporarily unavailable.") from exc
    raise HTTPException(status_code=502, detail="Clash API request failed.") from exc


@router.post("/jobs/sync-clan")
async def sync_clan(request: SyncClanRequest, session: AsyncSession = Depends(get_db_session)) -> dict:
    try:
        tag = normalize_tag(request.tag)
    except TagNormalizationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    service = ClanSyncService(session=session, clash_client=ClashApiClient())
    try:
        snapshot = await service.sync_clan(tag)
    except ClashApiError as exc:
        _raise_clash_http_error(exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("internal_sync_clan_failed", extra={"tag": tag})
        raise HTTPException(status_code=500, detail="Internal server error.") from exc

    return {
        "tag": tag,
        "snapshot_id": snapshot.id,
        "member_count": snapshot.member_count,
        "taken_at": snapshot.taken_at,
    }


@router.post("/jobs/build-report")
async def build_report(request: BuildReportRequest, session: AsyncSession = Depends(get_db_session)) -> dict:
    try:
        tag = normalize_tag(request.tag)
    except TagNormalizationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    service = ReportBuilderService(session=session, clash_client=ClashApiClient())
    try:
        result = await service.build_report_for_clan(
            raw_clan_tag=tag,
            source=ReportSource.MANUAL,
            force_rebuild=request.force_rebuild,
        )
    except ClashApiError as exc:
        _raise_clash_http_error(exc)
    except ReportBuildError as exc:
        logger.warning("internal_build_report_failed", extra={"tag": tag, "error_type": type(exc).__name__})
        raise HTTPException(status_code=500, detail="Unable to build report.") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("internal_build_report_unhandled_failed", extra={"tag": tag})
        raise HTTPException(status_code=500, detail="Internal server error.") from exc

    report = await ReportRepository(session).get_by_id(result.report.id)
    if report is None:
        raise HTTPException(status_code=500, detail="Report not found after build")

    return {
        "report_id": report.id,
        "clan_tag": report.clan.tag,
        "generated_at": report.generated_at,
        "is_cached": result.is_cached,
        "kick_count": report.kick_count,
        "question_count": report.question_count,
        "newbie_count": report.newbie_count,
        "left_count": report.left_count,
    }


@router.get("/clans/{tag}/report/latest")
async def latest_report(tag: str, session: AsyncSession = Depends(get_db_session)) -> dict:
    try:
        clan_tag = normalize_tag(tag)
    except TagNormalizationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clans = ClanRepository(session)
    reports = ReportRepository(session)
    clan = await clans.get_by_tag(clan_tag)
    if clan is None:
        raise HTTPException(status_code=404, detail="Clan not found")

    report = await reports.latest_for_clan(clan.id)
    if report is None:
        raise HTTPException(status_code=404, detail="No reports")

    return {
        "id": report.id,
        "clan_tag": clan.tag,
        "clan_name": clan.name,
        "generated_at": report.generated_at,
        "raid_weekend_start_at": report.raid_weekend_start_at,
        "raid_weekend_end_at": report.raid_weekend_end_at,
        "kick_count": report.kick_count,
        "question_count": report.question_count,
        "newbie_count": report.newbie_count,
        "left_count": report.left_count,
    }


@router.get("/clans/{tag}/members")
async def clan_members(tag: str, session: AsyncSession = Depends(get_db_session)) -> dict:
    try:
        clan_tag = normalize_tag(tag)
    except TagNormalizationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clans = ClanRepository(session)
    clan = await clans.get_by_tag(clan_tag)
    if clan is None:
        raise HTTPException(status_code=404, detail="Clan not found")

    snapshot = await SnapshotRepository(session).latest(clan.id)
    states = await PlayerRepository(session).list_states_for_clan(clan.id)

    current_tags = set(snapshot.member_tags if snapshot else [])
    members = [
        {
            "tag": state.player.tag,
            "name": state.player.name,
            "first_seen_in_clan_at": state.first_seen_in_clan_at,
            "last_seen_in_clan_at": state.last_seen_in_clan_at,
            "is_current_member": state.player.tag in current_tags,
        }
        for state in states
        if state.player is not None and state.player.tag in current_tags
    ]

    return {
        "clan_tag": clan.tag,
        "snapshot_taken_at": snapshot.taken_at if snapshot else datetime.now(UTC),
        "count": len(members),
        "members": members,
    }
