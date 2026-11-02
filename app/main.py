"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import github_issues, indexing, issues, pr, testing
from app.config import configure_logging, settings

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Autonomous Software Engineer API on port %s", settings.app_port)
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Autonomous Software Engineer",
    description="AI agent that fixes GitHub issues and opens pull requests automatically.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(indexing.router)
app.include_router(issues.router)
app.include_router(testing.router)
app.include_router(pr.router)
app.include_router(github_issues.router)


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}
