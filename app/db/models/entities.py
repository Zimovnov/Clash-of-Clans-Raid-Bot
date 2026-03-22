from __future__ import annotations

from enum import Enum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ClanRole(str, Enum):
    OWNER = "owner"
    MANAGER = "manager"


class ClanAccessRequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReportCategory(str, Enum):
    KICK = "kick"
    QUESTIONABLE = "questionable"
    NEWBIE = "newbie"
    LEFT_CLAN = "left_clan"
    OK = "ok"


class ReportSource(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"
    RETRY = "retry"


class ReportStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class JobStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class OutboxStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class UserLanguage(str, Enum):
    EN = "en"
    RU = "ru"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum_cls]


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[UserLanguage] = mapped_column(
        SqlEnum(UserLanguage, name="user_language", values_callable=_enum_values),
        default=UserLanguage.EN,
        server_default=UserLanguage.EN.value,
        nullable=False,
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    accesses: Mapped[list[ClanAccess]] = relationship(back_populates="user", cascade="all, delete-orphan")
    access_requests: Mapped[list[ClanAccessRequest]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="ClanAccessRequest.user_id",
    )
    resolved_access_requests: Mapped[list[ClanAccessRequest]] = relationship(
        back_populates="resolved_by_user",
        foreign_keys="ClanAccessRequest.resolved_by_user_id",
    )
    outbox_messages: Mapped[list[OutboxMessage]] = relationship(back_populates="user")


class Clan(Base):
    __tablename__ = "clans"

    id: Mapped[int] = mapped_column(primary_key=True)
    tag: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    is_tracking: Mapped[bool] = mapped_column(Boolean, default=True)
    newbie_baseline_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    accesses: Mapped[list[ClanAccess]] = relationship(back_populates="clan", cascade="all, delete-orphan")
    access_requests: Mapped[list[ClanAccessRequest]] = relationship(
        back_populates="clan",
        cascade="all, delete-orphan",
    )
    player_states: Mapped[list[PlayerClanState]] = relationship(back_populates="clan", cascade="all, delete-orphan")
    snapshots: Mapped[list[ClanMembershipSnapshot]] = relationship(back_populates="clan", cascade="all, delete-orphan")
    reports: Mapped[list[RaidReport]] = relationship(back_populates="clan", cascade="all, delete-orphan")
    job_runs: Mapped[list[JobRun]] = relationship(back_populates="clan")
    outbox_messages: Mapped[list[OutboxMessage]] = relationship(back_populates="clan")


class ClanAccess(Base):
    __tablename__ = "clan_access"
    __table_args__ = (UniqueConstraint("clan_id", "user_id", name="uq_clan_access_clan_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    clan_id: Mapped[int] = mapped_column(ForeignKey("clans.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[ClanRole] = mapped_column(
        SqlEnum(ClanRole, name="clan_role", values_callable=_enum_values),
        index=True,
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    clan: Mapped[Clan] = relationship(back_populates="accesses")
    user: Mapped[User] = relationship(back_populates="accesses")


class ClanAccessRequest(Base):
    __tablename__ = "clan_access_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    clan_id: Mapped[int] = mapped_column(ForeignKey("clans.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    requested_role: Mapped[ClanRole] = mapped_column(
        SqlEnum(ClanRole, name="clan_role", values_callable=_enum_values),
        default=ClanRole.MANAGER,
    )
    status: Mapped[ClanAccessRequestStatus] = mapped_column(
        SqlEnum(
            ClanAccessRequestStatus,
            name="clan_access_request_status",
            values_callable=_enum_values,
        ),
        default=ClanAccessRequestStatus.PENDING,
        index=True,
    )
    resolved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    clan: Mapped[Clan] = relationship(back_populates="access_requests")
    user: Mapped[User] = relationship(back_populates="access_requests", foreign_keys=[user_id])
    resolved_by_user: Mapped[User | None] = relationship(
        back_populates="resolved_access_requests",
        foreign_keys=[resolved_by_user_id],
    )


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    tag: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    first_seen_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    clan_states: Mapped[list[PlayerClanState]] = relationship(back_populates="player", cascade="all, delete-orphan")
    profile: Mapped[PlayerProfile | None] = relationship(back_populates="player", cascade="all, delete-orphan", uselist=False)
    report_rows: Mapped[list[RaidReportPlayer]] = relationship(back_populates="player")


class PlayerProfile(Base):
    __tablename__ = "player_profiles"
    __table_args__ = (UniqueConstraint("player_id", name="uq_player_profiles_player"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    exp_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    town_hall_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    builder_hall_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    league_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clan_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    refreshed_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    player: Mapped[Player] = relationship(back_populates="profile")


class PlayerClanState(Base):
    __tablename__ = "player_clan_state"
    __table_args__ = (UniqueConstraint("player_id", "clan_id", name="uq_player_clan_state_player_clan"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    clan_id: Mapped[int] = mapped_column(ForeignKey("clans.id", ondelete="CASCADE"), index=True)
    first_seen_in_clan_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_in_clan_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_current_member: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    manager_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    player: Mapped[Player] = relationship(back_populates="clan_states")
    clan: Mapped[Clan] = relationship(back_populates="player_states")


class ClanMembershipSnapshot(Base):
    __tablename__ = "clan_membership_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    clan_id: Mapped[int] = mapped_column(ForeignKey("clans.id", ondelete="CASCADE"), index=True)
    taken_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    member_count: Mapped[int] = mapped_column(Integer)
    member_tags: Mapped[list[str]] = mapped_column(JSON)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    clan: Mapped[Clan] = relationship(back_populates="snapshots")


class RaidReport(Base):
    __tablename__ = "raid_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    clan_id: Mapped[int] = mapped_column(ForeignKey("clans.id", ondelete="CASCADE"), index=True)
    raid_weekend_start_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raid_weekend_end_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    source: Mapped[ReportSource] = mapped_column(
        SqlEnum(ReportSource, name="report_source", values_callable=_enum_values),
        index=True,
    )
    status: Mapped[ReportStatus] = mapped_column(
        SqlEnum(ReportStatus, name="report_status", values_callable=_enum_values),
        default=ReportStatus.SUCCESS,
    )
    kick_count: Mapped[int] = mapped_column(Integer, default=0)
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    newbie_count: Mapped[int] = mapped_column(Integer, default=0)
    left_count: Mapped[int] = mapped_column(Integer, default=0)
    ok_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    clan: Mapped[Clan] = relationship(back_populates="reports")
    players: Mapped[list[RaidReportPlayer]] = relationship(back_populates="report", cascade="all, delete-orphan")
    outbox_messages: Mapped[list[OutboxMessage]] = relationship(back_populates="report")


class RaidReportPlayer(Base):
    __tablename__ = "raid_report_players"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("raid_reports.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    player_tag: Mapped[str] = mapped_column(String(32), index=True)
    player_name: Mapped[str] = mapped_column(String(255))
    attacks_used: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[ReportCategory] = mapped_column(
        SqlEnum(ReportCategory, name="report_category", values_callable=_enum_values),
        index=True,
    )
    is_current_member: Mapped[bool] = mapped_column(Boolean, default=True)
    first_seen_in_clan_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    left_clan_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    report: Mapped[RaidReport] = relationship(back_populates="players")
    player: Mapped[Player | None] = relationship(back_populates="report_rows")


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(255), index=True)
    clan_id: Mapped[int | None] = mapped_column(ForeignKey("clans.id", ondelete="SET NULL"), nullable=True, index=True)
    scheduled_for: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        SqlEnum(JobStatus, name="job_status", values_callable=_enum_values),
        default=JobStatus.RUNNING,
    )
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    clan: Mapped[Clan | None] = relationship(back_populates="job_runs")


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    clan_id: Mapped[int] = mapped_column(ForeignKey("clans.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("raid_reports.id", ondelete="SET NULL"), nullable=True)
    message_type: Mapped[str] = mapped_column(String(64), index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    status: Mapped[OutboxStatus] = mapped_column(
        SqlEnum(OutboxStatus, name="outbox_status", values_callable=_enum_values),
        default=OutboxStatus.PENDING,
    )
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    clan: Mapped[Clan] = relationship(back_populates="outbox_messages")
    user: Mapped[User] = relationship(back_populates="outbox_messages")
    report: Mapped[RaidReport | None] = relationship(back_populates="outbox_messages")
