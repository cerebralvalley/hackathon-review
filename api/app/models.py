"""SQLAlchemy ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from api.app.database import Base

PIPELINE_STAGES = [
    "parse",
    "clone",
    "video_download",
    "static_analysis",
    "code_review",
    "video_analysis",
    "scoring",
    "reporting",
]


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Hackathon(Base):
    __tablename__ = "hackathons"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    config = Column(JSON, nullable=False, default=dict)
    csv_filename = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    runs = relationship("PipelineRun", back_populates="hackathon", cascade="all, delete-orphan")


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(String, primary_key=True, default=_uuid)
    hackathon_id = Column(String, ForeignKey("hackathons.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending | running | completed | failed
    current_stage = Column(String, nullable=True)
    stage_progress = Column(JSON, nullable=False, default=dict)
    stage_detail = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    # List of "<team_number>:<flag_type>" keys that the organizer has marked
    # as not-a-big-deal. The flags endpoint still returns the flag but with
    # `dismissed: true` so audit history is preserved.
    dismissed_flags = Column(JSON, nullable=False, default=list)

    hackathon = relationship("Hackathon", back_populates="runs")
