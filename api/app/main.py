"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

logger = logging.getLogger(__name__)

load_dotenv()
from fastapi.middleware.cors import CORSMiddleware

from api.app.config import settings
from api.app.database import Base, engine
from api.app.routes import hackathons, parse_rules, results, runs


def _run_migrations() -> None:
    """Lightweight schema migrations for new columns on existing tables."""
    import sqlalchemy
    with engine.connect() as conn:
        inspector = sqlalchemy.inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("pipeline_runs")} if inspector.has_table("pipeline_runs") else set()
        if "stage_detail" not in columns and "pipeline_runs" in {t for t in inspector.get_table_names()}:
            conn.execute(sqlalchemy.text("ALTER TABLE pipeline_runs ADD COLUMN stage_detail JSON NOT NULL DEFAULT '{}'"))
            conn.commit()


def _recover_interrupted_runs() -> None:
    """Mark any runs left in 'running'/'pending' from a prior server session as 'interrupted'."""
    from api.app.database import SessionLocal
    from api.app.models import PipelineRun
    db = SessionLocal()
    try:
        stuck = db.query(PipelineRun).filter(PipelineRun.status.in_(["running", "pending"])).all()
        for run in stuck:
            run.status = "interrupted"
            progress = dict(run.stage_progress or {})
            if run.current_stage and progress.get(run.current_stage) == "running":
                progress[run.current_stage] = "interrupted"
            run.stage_progress = progress
        if stuck:
            db.commit()
            logger.info("Marked %d interrupted run(s)", len(stuck))
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _run_migrations()
    _recover_interrupted_runs()
    settings.data_root.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Hackathon Reviewer API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(hackathons.router)
app.include_router(runs.router)
app.include_router(results.router)
app.include_router(parse_rules.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
