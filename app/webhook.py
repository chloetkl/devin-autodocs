import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import application_settings
from app.database import get_database_session
from app.devin_client import DevinApiClient
from app.models import DocumentationDriftAnalysis
from app.poller import schedule_session_polling

logger = logging.getLogger(__name__)

github_events_router = APIRouter(tags=["GitHub Events"])


def _get_devin_api_client() -> DevinApiClient:
    return DevinApiClient(
        api_token=application_settings.devin_api_token,
        organization_id=application_settings.devin_organization_id,
        base_url=application_settings.devin_api_base_url,
    )


def verify_github_webhook_signature(
    payload_body: bytes, signature_header: str, secret: str
) -> bool:
    if not signature_header:
        return False
    expected_signature = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature_header)


@github_events_router.post("/api/github/events", status_code=202)
async def handle_github_webhook_event(
    request: Request,
    background_tasks: BackgroundTasks,
    database_session: AsyncSession = Depends(get_database_session),
    x_github_event: str | None = Header(None),
    x_hub_signature_256: str | None = Header(None),
):
    raw_payload_body = await request.body()

    webhook_secret = application_settings.github_webhook_secret
    if webhook_secret:
        if not verify_github_webhook_signature(
            raw_payload_body, x_hub_signature_256 or "", webhook_secret
        ):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if x_github_event != "pull_request":
        return {"message": f"Ignoring event type: {x_github_event}"}

    event_payload = json.loads(raw_payload_body)
    webhook_action = event_payload.get("action")

    if webhook_action != "opened":
        return {"message": f"Ignoring pull_request action: {webhook_action}"}

    pull_request_data = event_payload.get("pull_request", {})
    repository_data = event_payload.get("repository", {})

    repository_full_name = repository_data.get("full_name", "")
    pull_request_number = pull_request_data.get("number")
    pull_request_title = pull_request_data.get("title", "")
    pull_request_html_url = pull_request_data.get("html_url", "")

    if not repository_full_name or not pull_request_number:
        raise HTTPException(status_code=400, detail="Missing repository or PR information")

    drift_analysis_record = DocumentationDriftAnalysis(
        repository_full_name=repository_full_name,
        pull_request_number=pull_request_number,
        pull_request_title=pull_request_title,
        pull_request_url=pull_request_html_url,
        trigger_type="pull_request_webhook",
        analysis_status="pending",
    )
    database_session.add(drift_analysis_record)
    await database_session.commit()
    await database_session.refresh(drift_analysis_record)

    analysis_id = drift_analysis_record.id

    background_tasks.add_task(
        _create_devin_session_and_start_polling,
        analysis_id,
        repository_full_name,
        pull_request_number,
        pull_request_title,
    )

    return {
        "message": "Documentation drift analysis initiated",
        "analysis_id": analysis_id,
    }


async def _create_devin_session_and_start_polling(
    analysis_id: int,
    repository_full_name: str,
    pull_request_number: int,
    pull_request_title: str,
) -> None:
    from app.database import async_database_session_factory

    devin_client = _get_devin_api_client()
    try:
        prompt = DevinApiClient.build_pull_request_analysis_prompt(
            repository_full_name, pull_request_number, pull_request_title
        )

        session_response = await devin_client.create_documentation_drift_session(
            prompt=prompt,
            repository_full_name=repository_full_name,
            session_title=f"Doc drift check: {repository_full_name}#{pull_request_number}",
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
        logger.exception("Failed to create Devin session for analysis %d", analysis_id)
        async with async_database_session_factory() as database_session:
            analysis_record = await database_session.get(DocumentationDriftAnalysis, analysis_id)
            if analysis_record:
                analysis_record.analysis_status = "error"
                analysis_record.error_message = "Failed to create Devin session"
                await database_session.commit()
    finally:
        await devin_client.close()
