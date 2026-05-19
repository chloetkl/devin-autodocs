from app.devin_client import (
    DOCUMENTATION_DRIFT_STRUCTURED_OUTPUT_SCHEMA,
    DevinApiClient,
)


class TestDevinApiClientPromptGeneration:
    def test_pull_request_analysis_prompt_includes_pr_details(self):
        prompt = DevinApiClient.build_pull_request_analysis_prompt(
            repository_full_name="myorg/myrepo",
            pull_request_number=42,
            pull_request_title="Add user endpoint",
        )
        assert "myorg/myrepo" in prompt
        assert "#42" in prompt
        assert "Add user endpoint" in prompt
        assert "documentation drift" in prompt.lower()

    def test_repository_audit_scan_prompt_includes_repo_name(self):
        prompt = DevinApiClient.build_repository_audit_scan_prompt(
            repository_full_name="myorg/myrepo"
        )
        assert "myorg/myrepo" in prompt
        assert "audit" in prompt.lower()

    def test_session_web_url_is_correct(self):
        client = DevinApiClient(
            api_token="test-token",
            organization_id="org-test",
            base_url="https://api.devin.ai",
        )
        url = client.build_session_web_url("abc123")
        assert url == "https://app.devin.ai/sessions/abc123"


class TestStructuredOutputSchema:
    def test_schema_has_required_fields(self):
        assert "properties" in DOCUMENTATION_DRIFT_STRUCTURED_OUTPUT_SCHEMA
        props = DOCUMENTATION_DRIFT_STRUCTURED_OUTPUT_SCHEMA["properties"]
        assert "drift_detected" in props
        assert "summary" in props
        assert "endpoints_changed" in props
        assert "fix_pull_request_url" in props

    def test_schema_required_list(self):
        required = DOCUMENTATION_DRIFT_STRUCTURED_OUTPUT_SCHEMA["required"]
        assert "drift_detected" in required
        assert "summary" in required
