import logging

import httpx

from app.config import application_settings

logger = logging.getLogger(__name__)


def get_devin_api_client() -> "DevinApiClient":
    """Construct a DevinApiClient from the current application settings."""
    return DevinApiClient(
        api_token=application_settings.devin_api_token,
        organization_id=application_settings.devin_organization_id,
        base_url=application_settings.devin_api_base_url,
    )


DOCUMENTATION_DRIFT_STRUCTURED_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "drift_detected": {
            "type": "boolean",
            "description": "Whether API documentation drift was detected",
        },
        "endpoints_changed": {
            "type": "array",
            "description": "List of API endpoints that changed",
            "items": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "description": "HTTP method (GET, POST, etc.)"},
                    "path": {"type": "string", "description": "Endpoint path"},
                    "change_type": {
                        "type": "string",
                        "enum": ["added", "modified", "removed"],
                        "description": "Type of change",
                    },
                    "documentation_updated": {
                        "type": "boolean",
                        "description": "Whether docs were updated for this endpoint",
                    },
                },
                "required": ["method", "path", "change_type", "documentation_updated"],
            },
        },
        "summary": {
            "type": "string",
            "description": "Human-readable summary of the analysis",
        },
        "fix_pull_request_url": {
            "type": ["string", "null"],
            "description": "URL of the fix PR if one was created",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Confidence level of the drift detection",
        },
    },
    "required": ["drift_detected", "summary"],
}


class DevinApiClient:
    """Async HTTP client for the Devin AI API (session creation and status polling)."""

    def __init__(self, api_token: str, organization_id: str, base_url: str) -> None:
        self._api_token = api_token
        self._organization_id = organization_id
        self._base_url = base_url.rstrip("/")
        self._http_client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_token}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    async def create_documentation_drift_session(
        self,
        prompt: str,
        repository_full_name: str,
        session_tags: list[str] | None = None,
        session_title: str | None = None,
    ) -> dict:
        request_payload = {
            "prompt": prompt,
            "repos": [repository_full_name],
            "tags": session_tags or ["autodocs", "documentation-drift"],
            "structured_output_schema": DOCUMENTATION_DRIFT_STRUCTURED_OUTPUT_SCHEMA,
        }
        if session_title:
            request_payload["title"] = session_title

        response = await self._http_client.post(
            f"/v3/organizations/{self._organization_id}/sessions",
            json=request_payload,
        )
        response.raise_for_status()
        return response.json()

    async def get_session_details(self, session_id: str) -> dict:
        response = await self._http_client.get(
            f"/v3/organizations/{self._organization_id}/sessions/{session_id}",
        )
        response.raise_for_status()
        return response.json()

    def build_session_web_url(self, session_id: str) -> str:
        return f"https://app.devin.ai/sessions/{session_id}"

    async def close(self) -> None:
        """Close the underlying HTTP client. Always call this when done with the client."""
        await self._http_client.aclose()

    @staticmethod
    def build_pull_request_analysis_prompt(
        repository_full_name: str,
        pull_request_number: int,
        pull_request_title: str,
    ) -> str:
        return (
            f'Analyze pull request #{pull_request_number} ("{pull_request_title}") '
            f"in the repository {repository_full_name} for API documentation drift.\n"
            "\n"
            "Instructions:\n"
            "1. Check out the PR branch and review the diff.\n"
            "2. Identify any changes to API endpoints — new endpoints added, "
            "existing endpoints modified (parameters, request/response bodies, "
            "status codes), or endpoints removed.\n"
            "3. Check if the corresponding API documentation (README, "
            "OpenAPI/Swagger specs, doc files, inline docstrings, wiki pages) "
            "has been updated to reflect these changes.\n"
            "4. If documentation drift is detected (API changed but docs not "
            "updated), create a new pull request that updates the documentation "
            "to match the current API.\n"
            "5. If no API endpoint changes are found in the PR, or if the "
            "documentation is already up to date, report no drift.\n"
            "\n"
            "Be thorough: check route definitions, handler functions, middleware "
            "changes, schema/model changes that affect API contracts, and any "
            "auto-generated API specs."
        )

    @staticmethod
    def build_repository_audit_scan_prompt(
        repository_full_name: str,
    ) -> str:
        return (
            "Perform a comprehensive API documentation audit of the "
            f"repository {repository_full_name}.\n"
            "\n"
            "Instructions:\n"
            "1. Scan the entire codebase for all API endpoint definitions "
            "(REST routes, GraphQL resolvers, RPC handlers, etc.).\n"
            "2. Locate all existing API documentation (README files, "
            "OpenAPI/Swagger specs, doc directories, wiki pages, "
            "inline docstrings).\n"
            "3. Compare every discovered endpoint against the documentation. "
            "Identify:\n"
            "   - Endpoints that exist in code but are not documented\n"
            "   - Endpoints whose documentation is outdated "
            "(wrong parameters, response formats, status codes)\n"
            "   - Documentation for endpoints that no longer exist in code\n"
            "4. Create a pull request that adds or updates documentation "
            "for all identified drift.\n"
            "5. Provide a detailed summary of all findings.\n"
            "\n"
            "Be thorough and check all source files, not just the main "
            "entry point."
        )
