from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class DatabaseBaseModel(DeclarativeBase):
    pass


class DocumentationDriftAnalysis(DatabaseBaseModel):
    __tablename__ = "documentation_drift_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repository_full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    pull_request_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pull_request_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pull_request_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    trigger_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "pull_request_webhook" | "repository_audit_scan" | "manual_trigger"

    devin_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    devin_session_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    analysis_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", index=True
    )  # pending | analyzing | no_drift_detected | drift_detected | fix_pr_created | error

    drift_detected: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    drift_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    endpoints_changed_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_level: Mapped[str | None] = mapped_column(String(20), nullable=True)

    fix_pull_request_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
