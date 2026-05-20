from app.dashboard import _serialize_analysis_record
from app.models import DocumentationDriftAnalysis


class TestAnalysisRecordSerialization:
    def test_serialize_basic_analysis_record(self):
        record = DocumentationDriftAnalysis(
            id=1,
            repository_full_name="testorg/testrepo",
            pull_request_number=42,
            pull_request_title="Add endpoint",
            pull_request_url="https://github.com/testorg/testrepo/pull/42",
            trigger_type="pull_request_webhook",
            analysis_status="pending",
        )
        serialized = _serialize_analysis_record(record)
        assert serialized["id"] == 1
        assert serialized["repository_full_name"] == "testorg/testrepo"
        assert serialized["pull_request_number"] == 42
        assert serialized["analysis_status"] == "pending"

    def test_serialize_record_with_endpoints_json(self):
        record = DocumentationDriftAnalysis(
            id=2,
            repository_full_name="testorg/testrepo",
            trigger_type="repository_audit_scan",
            analysis_status="drift_detected",
            drift_detected=True,
            endpoints_changed_json='[{"method": "GET", "path": "/users"}]',
        )
        serialized = _serialize_analysis_record(record)
        assert serialized["drift_detected"] is True
        assert serialized["endpoints_changed"] == [{"method": "GET", "path": "/users"}]

    def test_serialize_record_with_invalid_json_returns_none(self):
        record = DocumentationDriftAnalysis(
            id=3,
            repository_full_name="testorg/testrepo",
            trigger_type="repository_audit_scan",
            analysis_status="error",
            endpoints_changed_json="not-valid-json",
        )
        serialized = _serialize_analysis_record(record)
        assert serialized["endpoints_changed"] is None

    def test_serialize_audit_scan_has_no_pr_number(self):
        record = DocumentationDriftAnalysis(
            id=4,
            repository_full_name="testorg/testrepo",
            trigger_type="repository_audit_scan",
            analysis_status="analyzing",
        )
        serialized = _serialize_analysis_record(record)
        assert serialized["pull_request_number"] is None
        assert serialized["trigger_type"] == "repository_audit_scan"
