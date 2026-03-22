from app.db.models.entities import ClanAccess, JobRun, OutboxMessage, RaidReport, RaidReportPlayer


def test_sqlalchemy_enums_use_lowercase_values() -> None:
    assert ClanAccess.__table__.c.role.type.enums == ["owner", "manager"]
    assert RaidReport.__table__.c.source.type.enums == ["auto", "manual", "retry"]
    assert RaidReport.__table__.c.status.type.enums == ["success", "failed"]
    assert RaidReportPlayer.__table__.c.category.type.enums == ["kick", "questionable", "newbie", "left_clan", "ok"]
    assert JobRun.__table__.c.status.type.enums == ["running", "success", "failed"]
    assert OutboxMessage.__table__.c.status.type.enums == ["pending", "sent", "failed"]
