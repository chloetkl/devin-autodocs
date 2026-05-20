import asyncio
import json
import logging

from app.devin_client import DevinApiClient
from app.models import DocumentationDriftAnalysis

logger = logging.getLogger(__name__)

TERMINAL_SESSION_STATUSES = {"exit", "error"}
SETTLED_STATUS_DETAILS = {"finished", "waiting_for_user"}


async def schedule_session_polling(
    analysis_id: int,
    session_id: str,
    devin_client: DevinApiClient,
) -> None:
    from app.config import application_settings

    poll_interval = application_settings.session_poll_interval_seconds
    poll_timeout = application_settings.session_poll_timeout_seconds
    elapsed_seconds = 0

    try:
        while elapsed_seconds < poll_timeout:
            await asyncio.sleep(poll_interval)
            elapsed_seconds += poll_interval

            try:
                session_details = await devin_client.get_session_details(session_id)
            except Exception:
                logger.exception("Failed to poll session %s", session_id)
                continue

            session_status = session_details.get("status", "")
            session_status_detail = session_details.get("status_detail", "")

            is_terminal = session_status in TERMINAL_SESSION_STATUSES
            is_settled_running = (
                session_status == "running" and session_status_detail in SETTLED_STATUS_DETAILS
            )

            if is_terminal or is_settled_running:
                await _process_completed_session(analysis_id, session_details)
                return

        await _mark_analysis_error(analysis_id, "Session polling timed out")
        logger.warning("Analysis %d timed out", analysis_id)

    except Exception:
        logger.exception("Polling error for analysis %d, session %s", analysis_id, session_id)
        await _mark_analysis_error(analysis_id, "Unexpected polling error")


async def _process_completed_session(analysis_id: int, session_details: dict) -> None:
    from app.database import async_database_session_factory

    session_status = session_details.get("status", "")
    structured_output = session_details.get("structured_output")

    async with async_database_session_factory() as database_session:
        analysis_record = await database_session.get(DocumentationDriftAnalysis, analysis_id)
        if not analysis_record:
            logger.warning("Analysis record %d not found", analysis_id)
            return

        if session_status == "error":
            analysis_record.analysis_status = "error"
            analysis_record.error_message = "Devin session ended with error"
            await database_session.commit()
            return

        if not structured_output:
            analysis_record.analysis_status = "error"
            analysis_record.error_message = "No structured output returned from Devin session"
            await database_session.commit()
            return

        drift_detected = structured_output.get("drift_detected", False)
        summary = structured_output.get("summary", "")
        fix_pr_url = structured_output.get("fix_pull_request_url")
        endpoints_changed = structured_output.get("endpoints_changed", [])
        confidence = structured_output.get("confidence")

        analysis_record.drift_detected = drift_detected
        analysis_record.drift_summary = summary
        analysis_record.confidence_level = confidence
        analysis_record.fix_pull_request_url = fix_pr_url

        if endpoints_changed:
            analysis_record.endpoints_changed_json = json.dumps(endpoints_changed)

        if not drift_detected:
            analysis_record.analysis_status = "no_drift_detected"
        elif fix_pr_url:
            analysis_record.analysis_status = "fix_pr_created"
        else:
            analysis_record.analysis_status = "drift_detected"

        await database_session.commit()
        logger.info(
            "Analysis %d completed: status=%s, drift=%s",
            analysis_id,
            analysis_record.analysis_status,
            drift_detected,
        )


async def _mark_analysis_error(analysis_id: int, error_message: str) -> None:
    from app.database import async_database_session_factory

    async with async_database_session_factory() as database_session:
        analysis_record = await database_session.get(DocumentationDriftAnalysis, analysis_id)
        if analysis_record:
            analysis_record.analysis_status = "error"
            analysis_record.error_message = error_message
            await database_session.commit()


async def update_analysis_with_session(
    analysis_id: int, session_id: str, session_url: str
) -> None:
    """Persist the Devin session ID/URL on an analysis record and mark it as analyzing."""
    from app.database import async_database_session_factory

    async with async_database_session_factory() as database_session:
        analysis_record = await database_session.get(DocumentationDriftAnalysis, analysis_id)
        if analysis_record:
            analysis_record.devin_session_id = session_id
            analysis_record.devin_session_url = session_url
            analysis_record.analysis_status = "analyzing"
            await database_session.commit()
