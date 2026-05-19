import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_database_session
from app.models import DocumentationDriftAnalysis

logger = logging.getLogger(__name__)

dashboard_router = APIRouter(tags=["Dashboard"])

templates = Jinja2Templates(directory="templates")


@dashboard_router.get("/dashboard")
async def render_dashboard_page(
    request: Request,
    database_session: AsyncSession = Depends(get_database_session),
):
    statistics = await _compute_dashboard_statistics(database_session)
    recent_analyses = await _get_recent_analyses(database_session, limit=50)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "statistics": statistics,
            "analyses": recent_analyses,
        },
    )


@dashboard_router.get("/api/statistics")
async def get_dashboard_statistics(
    database_session: AsyncSession = Depends(get_database_session),
):
    return await _compute_dashboard_statistics(database_session)


@dashboard_router.get("/api/analyses")
async def list_all_analyses(
    database_session: AsyncSession = Depends(get_database_session),
    limit: int = 50,
    offset: int = 0,
):
    query = (
        select(DocumentationDriftAnalysis)
        .order_by(DocumentationDriftAnalysis.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await database_session.execute(query)
    analyses = result.scalars().all()
    return [_serialize_analysis_record(analysis) for analysis in analyses]


@dashboard_router.get("/api/analyses/{analysis_id}")
async def get_analysis_details(
    analysis_id: int,
    database_session: AsyncSession = Depends(get_database_session),
):
    analysis_record = await database_session.get(DocumentationDriftAnalysis, analysis_id)
    if not analysis_record:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return _serialize_analysis_record(analysis_record)


@dashboard_router.post("/api/analyses/{analysis_id}/retry", status_code=202)
async def retry_failed_analysis(
    analysis_id: int,
    database_session: AsyncSession = Depends(get_database_session),
):
    analysis_record = await database_session.get(DocumentationDriftAnalysis, analysis_id)
    if not analysis_record:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis_record.analysis_status != "error":
        raise HTTPException(status_code=400, detail="Only failed analyses can be retried")

    analysis_record.analysis_status = "pending"
    analysis_record.error_message = None
    analysis_record.devin_session_id = None
    analysis_record.devin_session_url = None
    await database_session.commit()

    return {"message": "Analysis queued for retry", "analysis_id": analysis_id}


async def _compute_dashboard_statistics(database_session: AsyncSession) -> dict:
    completed_statuses = ("no_drift_detected", "fix_pr_created")
    open_statuses = ("pending", "analyzing")
    unresolved_statuses = ("drift_detected",)
    error_statuses = ("error",)

    total_count = await _count_analyses_by_statuses(database_session, None)
    completed_count = await _count_analyses_by_statuses(database_session, completed_statuses)
    open_count = await _count_analyses_by_statuses(database_session, open_statuses)
    unresolved_count = await _count_analyses_by_statuses(database_session, unresolved_statuses)
    error_count = await _count_analyses_by_statuses(database_session, error_statuses)

    drift_found_count = await _count_where_drift_detected(database_session)
    fix_prs_created_count = await _count_analyses_by_statuses(
        database_session, ("fix_pr_created",)
    )

    error_rate = (error_count / total_count * 100) if total_count > 0 else 0.0

    average_resolution_minutes = await _compute_average_resolution_minutes(database_session)

    timeout_count = await _count_timeout_errors(database_session)
    timeout_rate = (timeout_count / total_count * 100) if total_count > 0 else 0.0

    return {
        "total_analyses": total_count,
        "completed_analyses": completed_count,
        "open_analyses": open_count,
        "unresolved_analyses": unresolved_count,
        "error_count": error_count,
        "error_rate_percentage": round(error_rate, 1),
        "timeout_count": timeout_count,
        "timeout_rate_percentage": round(timeout_rate, 1),
        "total_drift_detected": drift_found_count,
        "total_fix_prs_created": fix_prs_created_count,
        "average_resolution_minutes": round(average_resolution_minutes, 1),
    }


async def _count_analyses_by_statuses(
    database_session: AsyncSession, statuses: tuple[str, ...] | None
) -> int:
    query = select(func.count(DocumentationDriftAnalysis.id))
    if statuses is not None:
        query = query.where(DocumentationDriftAnalysis.analysis_status.in_(statuses))
    result = await database_session.execute(query)
    return result.scalar() or 0


async def _count_where_drift_detected(database_session: AsyncSession) -> int:
    query = select(func.count(DocumentationDriftAnalysis.id)).where(
        DocumentationDriftAnalysis.drift_detected.is_(True)
    )
    result = await database_session.execute(query)
    return result.scalar() or 0


async def _count_timeout_errors(database_session: AsyncSession) -> int:
    query = select(func.count(DocumentationDriftAnalysis.id)).where(
        DocumentationDriftAnalysis.analysis_status == "error",
        DocumentationDriftAnalysis.error_message.contains("timed out"),
    )
    result = await database_session.execute(query)
    return result.scalar() or 0


async def _compute_average_resolution_minutes(database_session: AsyncSession) -> float:
    terminal_statuses = ("no_drift_detected", "fix_pr_created", "drift_detected", "error")
    query = select(
        DocumentationDriftAnalysis.created_at,
        DocumentationDriftAnalysis.updated_at,
    ).where(DocumentationDriftAnalysis.analysis_status.in_(terminal_statuses))
    result = await database_session.execute(query)
    rows = result.all()

    if not rows:
        return 0.0

    total_minutes = 0.0
    count = 0
    for created_at, updated_at in rows:
        if created_at and updated_at:
            delta = updated_at - created_at
            total_minutes += delta.total_seconds() / 60
            count += 1

    return total_minutes / count if count > 0 else 0.0


async def _get_recent_analyses(
    database_session: AsyncSession, limit: int = 50
) -> list[dict]:
    query = (
        select(DocumentationDriftAnalysis)
        .order_by(DocumentationDriftAnalysis.created_at.desc())
        .limit(limit)
    )
    result = await database_session.execute(query)
    analyses = result.scalars().all()
    return [_serialize_analysis_record(analysis) for analysis in analyses]


def _serialize_analysis_record(analysis: DocumentationDriftAnalysis) -> dict:
    endpoints_changed = None
    if analysis.endpoints_changed_json:
        try:
            endpoints_changed = json.loads(analysis.endpoints_changed_json)
        except json.JSONDecodeError:
            endpoints_changed = None

    return {
        "id": analysis.id,
        "repository_full_name": analysis.repository_full_name,
        "pull_request_number": analysis.pull_request_number,
        "pull_request_title": analysis.pull_request_title,
        "pull_request_url": analysis.pull_request_url,
        "trigger_type": analysis.trigger_type,
        "devin_session_id": analysis.devin_session_id,
        "devin_session_url": analysis.devin_session_url,
        "analysis_status": analysis.analysis_status,
        "drift_detected": analysis.drift_detected,
        "drift_summary": analysis.drift_summary,
        "endpoints_changed": endpoints_changed,
        "confidence_level": analysis.confidence_level,
        "fix_pull_request_url": analysis.fix_pull_request_url,
        "error_message": analysis.error_message,
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        "updated_at": analysis.updated_at.isoformat() if analysis.updated_at else None,
    }
