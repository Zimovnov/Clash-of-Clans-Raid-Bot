from app.core.dates import format_datetime_human
from app.db.models import PlayerClanState, PlayerProfile, ReportCategory


def category_label(category: ReportCategory) -> str:
    labels = {
        ReportCategory.KICK: "На кик",
        ReportCategory.QUESTIONABLE: "Под вопросом",
        ReportCategory.NEWBIE: "Новички",
        ReportCategory.LEFT_CLAN: "Покинули клан",
        ReportCategory.OK: "Норма",
    }
    return labels[category]


def _resolve_league_label(profile: PlayerProfile) -> str:
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
        return f"Без текущей, лучшая {best_league_name}"

    return "Без лиги"


def format_profile_section(profile: PlayerProfile | None, *, is_stale: bool) -> list[str]:
    if profile is None:
        return [
            "Профиль игрока:",
            "Уровень: -",
            "Ратуша: -",
            "Лига: Без данных",
            "Роль в клане: -",
            "Профиль ещё не загружен.",
        ]

    freshness = "требует обновления" if is_stale else "актуален"
    return [
        "Профиль игрока:",
        f"Уровень: {profile.exp_level or '-'}",
        f"Ратуша: {profile.town_hall_level or '-'}",
        f"Лига: {_resolve_league_label(profile)}",
        f"Роль в клане: {profile.clan_role or '-'}",
        f"Обновлён: {format_datetime_human(profile.refreshed_at)} ({freshness})",
    ]


def build_report_player_card_text(row, manager_note: str | None, profile: PlayerProfile | None, *, is_profile_stale: bool) -> str:
    lines = [
        f"Ник: {row.player_name}",
        f"Тег: {row.player_tag}",
        f"Атак: {row.attacks_used}",
        f"Категория: {category_label(row.category)}",
        f"В клане сейчас: {'да' if row.is_current_member else 'нет'}",
        f"Первое обнаружение в клане: {format_datetime_human(row.first_seen_in_clan_at)}",
        f"Примечание: {manager_note or '-'}",
        f"Служебная пометка: {row.left_clan_note or '-'}",
        "",
        *format_profile_section(profile, is_stale=is_profile_stale),
    ]
    return "\n".join(lines)


def build_clan_member_card_text(state: PlayerClanState, manager_note: str | None, profile: PlayerProfile | None, *, is_profile_stale: bool) -> str:
    player = state.player
    lines = [
        f"Ник: {player.name if player is not None else '-'}",
        f"Тег: {player.tag if player is not None else '-'}",
        f"В клане сейчас: {'да' if state.is_current_member else 'нет'}",
        f"Первое обнаружение в клане: {format_datetime_human(state.first_seen_in_clan_at)}",
        f"Последнее обнаружение: {format_datetime_human(state.last_seen_in_clan_at)}",
        f"Примечание: {manager_note or '-'}",
        "",
        *format_profile_section(profile, is_stale=is_profile_stale),
    ]
    return "\n".join(lines)
