import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import application_settings
from app.database import get_database_session
from app.devin_client import DevinApiClient
from app.models import DocumentationDriftAnalysis
from app.poller import schedule_session_polling

logger = logging.getLogger(__name__)

repository_analysis_router = APIRouter(tags=["Repository Analysis"])


class RepositoryAuditScanRequest(BaseModel):
    repository_full_name: str


def _get_devin_api_client() -> DevinApiClient:
    return DevinApiClient(
        api_token=application_settings.devin_api_token,
        organization_id=application_settings.devin_organization_id,
        base_url=application_settings.devin_api_base_url,
    )


@repository_analysis_router.post("/api/repo/analyses", status_code=202)
async def trigger_repository_audit_scan(
    scan_request: RepositoryAuditScanRequest,
    background_tasks: BackgroundTasks,
    database_session: AsyncSession = Depends(get_database_session),
):
    if not scan_request.repository_full_name:
        raise HTTPException(status_code=400, detail="repository_full_name is required")

    drift_analysis_record = DocumentationDriftAnalysis(
        repository_full_name=scan_request.repository_full_name,
        trigger_type="repository_audit_scan",
        analysis_status="pending",
    )
    database_session.add(drift_analysis_record)
    await database_session.commit()
    await database_session.refresh(drift_analysis_record)

    analysis_id = drift_analysis_record.id

    background_tasks.add_task(
        _create_audit_session_and_start_polling,
        analysis_id,
        scan_request.repository_full_name,
    )

    return {
        "message": "Repository audit scan initiated",
        "analysis_id": analysis_id,
    }


async def _create_audit_session_and_start_polling(
    analysis_id: int,
    repository_full_name: str,
) -> None:
    from app.database import async_database_session_factory

    devin_client = _get_devin_api_client()
    try:
        prompt = DevinApiClient.build_repository_audit_scan_prompt(repository_full_name)

        session_response = await devin_client.create_documentation_drift_session(
            prompt=prompt,
            repository_full_name=repository_full_name,
            session_tags=["autodocs", "documentation-drift", "audit-scan"],
            session_title=f"Doc audit: {repository_full_name}",
        )

        session_id = session_response.get("session_id", "")
        session_url = devin_client.build_session_web_url(session_id)

        async with async_database_session_factory() as database_session:
            analysis_record = await database_session.get(DocumentationDriftAnalysis, analysis_id)
            if analysis_record:
                analysis_record.devin_session_id = session_id
                analysis_record.devin_session_url = session_url
                analysis_record.analysis_status = "analyzing"
                await database_session.commit()

        await schedule_session_polling(analysis_id, session_id, devin_client)

    except Exception:
        logger.exception("Failed to create audit session for analysis %d", analysis_id)
        async with async_database_session_factory() as database_session:
            analysis_record = await database_session.get(DocumentationDriftAnalysis, analysis_id)
            if analysis_record:
                analysis_record.analysis_status = "error"
                analysis_record.error_message = "Failed to create Devin audit session"
                await database_session.commit()
    finally:
        await devin_client.close()
