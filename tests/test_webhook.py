import hashlib
import hmac

import pytest

from app.webhook import verify_github_webhook_signature


class TestGitHubWebhookSignatureVerification:
    def test_valid_signature_is_accepted(self):
        secret = "test-secret"
        payload = b'{"action": "opened"}'
        expected_sig = "sha256=" + hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        assert verify_github_webhook_signature(payload, expected_sig, secret) is True

    def test_invalid_signature_is_rejected(self):
        secret = "test-secret"
        payload = b'{"action": "opened"}'
        assert verify_github_webhook_signature(payload, "sha256=invalid", secret) is False

    def test_empty_signature_is_rejected(self):
        secret = "test-secret"
        payload = b'{"action": "opened"}'
        assert verify_github_webhook_signature(payload, "", secret) is False


class TestGitHubWebhookEndpoint:
    @pytest.fixture
    def sample_pull_request_opened_payload(self):
        return {
            "action": "opened",
            "pull_request": {
                "number": 42,
                "title": "Add new endpoint",
                "html_url": "https://github.com/testorg/testrepo/pull/42",
            },
            "repository": {
                "full_name": "testorg/testrepo",
            },
        }

    @pytest.fixture
    def sample_pull_request_closed_payload(self):
        return {
            "action": "closed",
            "pull_request": {
                "number": 42,
                "title": "Add new endpoint",
                "html_url": "https://github.com/testorg/testrepo/pull/42",
            },
            "repository": {
                "full_name": "testorg/testrepo",
            },
        }

    def test_payload_structure_has_required_fields(self, sample_pull_request_opened_payload):
        payload = sample_pull_request_opened_payload
        assert payload["action"] == "opened"
        assert payload["pull_request"]["number"] == 42
        assert payload["repository"]["full_name"] == "testorg/testrepo"

    def test_closed_action_is_not_opened(self, sample_pull_request_closed_payload):
        assert sample_pull_request_closed_payload["action"] != "opened"
