"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()
from fastapi.middleware.cors import CORSMiddleware

from api.app.config import settings
from api.app.database import Base, engine
from api.app.routes import hackathons, parse_rules, results, runs


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
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
