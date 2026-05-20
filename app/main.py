import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.dashboard import dashboard_router
from app.database import initialize_database
from app.scanner import repository_analysis_router
from app.webhook import github_events_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def application_lifespan(app: FastAPI):
    logger.info("Starting API Documentation Drift Detector")
    await initialize_database()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down API Documentation Drift Detector")


app = FastAPI(
    title="API Documentation Drift Detector",
    description="Autonomous API documentation drift detection and remediation powered by Devin AI",
    version="0.1.0",
    lifespan=application_lifespan,
)

app.include_router(github_events_router)
app.include_router(repository_analysis_router)
app.include_router(dashboard_router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "api-documentation-drift-detector"}
