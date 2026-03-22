from app.core.dates import format_datetime_human
from app.core.i18n import category_label, t
from app.db.models import PlayerClanState, PlayerProfile, ReportCategory


def _resolve_league_label(profile: PlayerProfile, lang: str) -> str:
    raw_payload = profile.raw_payload or {}
    league_tier = raw_payload.get("leagueTier") or {}
    league_tier_name = str(league_tier.get("name")).strip() if league_tier.get("name") else None
    if league_tier_name:
        return league_tier_name

    if profile.league_name:
        return profile.league_name

    league = raw_payload.get("league") or {}
    league_name = str(league.get("name")).strip() if league.get("name") else None
    if league_name:
        return league_name

    best_league = raw_payload.get("bestLeague") or {}
    best_league_name = str(best_league.get("name")).strip() if best_league.get("name") else None
    if best_league_name:
        return t(lang, "profile.no_current_best", name=best_league_name)

    return t(lang, "profile.no_league")


def format_profile_section(profile: PlayerProfile | None, *, is_stale: bool, lang: str) -> list[str]:
    if profile is None:
        return [
            t(lang, "profile.title"),
            t(lang, "profile.level", value="-"),
            t(lang, "profile.town_hall", value="-"),
            t(lang, "profile.builder_hall", value="-"),
            t(lang, "profile.league", value=t(lang, "profile.empty_league")),
            t(lang, "profile.role", value="-"),
            t(lang, "profile.not_loaded"),
        ]

    freshness = t(lang, "profile.stale") if is_stale else t(lang, "profile.fresh")
    return [
        t(lang, "profile.title"),
        t(lang, "profile.level", value=profile.exp_level or "-"),
        t(lang, "profile.town_hall", value=profile.town_hall_level or "-"),
        t(lang, "profile.builder_hall", value=profile.builder_hall_level or "-"),
        t(lang, "profile.league", value=_resolve_league_label(profile, lang)),
        t(lang, "profile.role", value=profile.clan_role or "-"),
        t(lang, "profile.updated", value=format_datetime_human(profile.refreshed_at), freshness=freshness),
    ]


def _service_note(lang: str, row) -> str:
    if row.left_clan_note:
        return t(lang, "player.left_clan_note")
    return t(lang, "general.none")


def build_report_player_card_text(row, manager_note: str | None, profile: PlayerProfile | None, *, is_profile_stale: bool, lang: str) -> str:
    lines = [
        t(lang, "player.nickname", value=row.player_name),
        t(lang, "player.tag", value=row.player_tag),
        t(lang, "player.attacks", value=row.attacks_used),
        t(lang, "player.category", value=category_label(lang, row.category)),
        t(lang, "player.current_member", value=t(lang, "general.yes") if row.is_current_member else t(lang, "general.no")),
        t(lang, "player.first_seen", value=format_datetime_human(row.first_seen_in_clan_at)),
        t(lang, "player.note", value=manager_note or t(lang, "general.none")),
        t(lang, "player.service_note", value=_service_note(lang, row)),
        "",
        *format_profile_section(profile, is_stale=is_profile_stale, lang=lang),
    ]
    return "\n".join(lines)


def build_clan_member_card_text(state: PlayerClanState, manager_note: str | None, profile: PlayerProfile | None, *, is_profile_stale: bool, lang: str) -> str:
    player = state.player
    lines = [
        t(lang, "player.nickname", value=player.name if player is not None else "-"),
        t(lang, "player.tag", value=player.tag if player is not None else "-"),
        t(lang, "player.current_member", value=t(lang, "general.yes") if state.is_current_member else t(lang, "general.no")),
        t(lang, "player.first_seen", value=format_datetime_human(state.first_seen_in_clan_at)),
        t(lang, "player.last_seen", value=format_datetime_human(state.last_seen_in_clan_at)),
        t(lang, "player.note", value=manager_note or t(lang, "general.none")),
        "",
        *format_profile_section(profile, is_stale=is_profile_stale, lang=lang),
    ]
    return "\n".join(lines)
