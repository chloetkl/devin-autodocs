# Devin Autodocs

Autonomous API documentation drift detection and remediation powered by [Devin AI](https://devin.ai).

Detects when API endpoints change but documentation doesn't, then automatically creates fix PRs.

## How It Works

### Flow 1: New Pull Requests
A GitHub webhook fires on PR creation → the backend creates a Devin session that analyzes the PR diff for API endpoint changes → if docs weren't updated, Devin creates a fix PR.

> **Feedback loop prevention**: PRs opened by the Devin bot (`devin-ai-integration[bot]`) are silently ignored — they are fix PRs, not API changes, so re-analyzing them would cause an infinite loop.

### Flow 2: Existing Code Audit
Trigger a full repository scan via the dashboard or API → Devin scans the entire codebase for undocumented or outdated API endpoints → creates a fix PR for all drift found.

## Live Demo

▶️ [Watch the demo on Loom](https://www.loom.com/share/e5f6764d2051450abcacf060a152847a)

A hosted instance is available at **https://devin-autodocs.onrender.com/dashboard**.

> **Note**: For Devin to create fix PRs, it needs write access to the target repository: **https://github.com/chloetkl/superset**. **Webhook disabled, contact me if you would like me to reenable it**

## Prerequisites

- Python 3.11+
- A [Devin API token](https://app.devin.ai/settings/api-keys) (`DEVIN_API_TOKEN`)
- Your Devin organization ID — found in the Devin dashboard URL: `app.devin.ai/o/<org-id>` (`DEVIN_ORGANIZATION_ID`)
- A GitHub repository you want to monitor

## Quick Start

### Docker (recommended)

```bash
cp .env.example .env
# Edit .env with your credentials

docker compose up --build
```

The dashboard is available at `http://localhost:8000/dashboard`.

### Local Development

```bash
pip install -e ".[dev]"

# Set environment variables (or create .env file)
export DEVIN_API_TOKEN=your-token
export DEVIN_ORGANIZATION_ID=org-your-id
export GITHUB_WEBHOOK_SECRET=your-secret

uvicorn app.main:app --reload
```

## Simulating the Workflow

You don't need a real GitHub webhook to test the full flow. Use `curl` to simulate each trigger directly.

### Simulate a PR webhook (Flow 1)

```bash
curl -X POST http://localhost:8000/api/github/events \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -d '{
    "action": "opened",
    "pull_request": {
      "number": 42,
      "title": "Add new /users endpoint",
      "html_url": "https://github.com/your-org/your-repo/pull/42",
      "user": {"login": "your-github-username"}
    },
    "repository": {
      "full_name": "your-org/your-repo"
    }
  }'
```

> If `GITHUB_WEBHOOK_SECRET` is set, omit it from your `.env` when testing locally to skip signature verification, or sign the payload manually.

### Trigger a full repository audit (Flow 2)

```bash
curl -X POST http://localhost:8000/api/repo/analyses \
  -H "Content-Type: application/json" \
  -d '{"repository_full_name": "your-org/your-repo"}'
```

### Check analysis status

```bash
# List all analyses
curl http://localhost:8000/api/analyses

# Get a specific analysis
curl http://localhost:8000/api/analyses/1

# Retry a failed analysis
curl -X POST http://localhost:8000/api/analyses/1/retry
```

### Watch it on the dashboard

Open `http://localhost:8000/dashboard` — the analysis will appear immediately as **Devin is working.** and update to **All Clear**, **Fix PR Ready**, or **Devin needs help** once Devin finishes.

## Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `DEVIN_API_TOKEN` | Devin API v3 token | Yes |
| `DEVIN_ORGANIZATION_ID` | Devin organization ID (org-xxx) | Yes |
| `DEVIN_API_BASE_URL` | Base URL for the Devin API | No (default: `https://api.devin.ai`) |
| `GITHUB_WEBHOOK_SECRET` | GitHub webhook secret for signature verification | No (signature verification is skipped if not set) |
| `DATABASE_URL` | SQLite connection string | No (default: `sqlite+aiosqlite:///./data/autodocs.db`) |
| `SESSION_POLL_INTERVAL_SECONDS` | How often to poll Devin session status (seconds) | No (default: 30) |
| `SESSION_POLL_TIMEOUT_SECONDS` | Max time to wait for a session (seconds) | No (default: 1800) |

## Setting Up the GitHub Webhook

1. Go to your repository → Settings → Webhooks → Add webhook
2. Set Payload URL to `https://your-host/api/github/events`
3. Set Content type to `application/json`
4. Set Secret to match your `GITHUB_WEBHOOK_SECRET`
5. Select "Pull requests" under events
6. Save

## API Endpoints

### `GET /health`

Health check endpoint.

**Response** `200`:
```json
{"status": "healthy", "service": "api-documentation-drift-detector"}
```

---

### `POST /api/github/events`

GitHub webhook receiver. Listens for `pull_request` events with action `opened` and triggers drift analysis.

**Headers**:
| Header | Description | Required |
|--------|-------------|----------|
| `X-GitHub-Event` | GitHub event type (only `pull_request` is processed) | Yes |
| `X-Hub-Signature-256` | HMAC-SHA256 signature for payload verification | Only if `GITHUB_WEBHOOK_SECRET` is configured |

**Request body**: Raw GitHub webhook JSON payload.

**Response** `202`:
```json
{"message": "Documentation drift analysis initiated", "analysis_id": 1}
```

PRs where the author is `devin-ai-integration[bot]` are silently skipped (returns `202` with `"Ignoring PR opened by Devin bot"`).

**Errors**:
- `401` — Invalid webhook signature (when secret is configured).
- `400` — Missing repository or PR information in payload.

---

### `POST /api/repo/analyses`

Trigger a full repository documentation audit scan.

**Request body**:
```json
{"repository_full_name": "owner/repo"}
```

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| `repository_full_name` | string | Full name of the repository (e.g. `owner/repo`) | Yes |

**Response** `202`:
```json
{"message": "Repository audit scan initiated", "analysis_id": 1}
```

**Errors**:
- `400` — `repository_full_name` is empty.

---

### `GET /api/analyses`

List all drift analyses with pagination.

**Query parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 50 | Maximum number of results to return |
| `offset` | int | 0 | Number of results to skip |

**Response** `200`: Array of analysis objects (see [Analysis Object](#analysis-object) below).

---

### `GET /api/analyses/{analysis_id}`

Get details of a specific analysis.

**Path parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `analysis_id` | int | ID of the analysis record |

**Response** `200`: A single analysis object (see [Analysis Object](#analysis-object) below).

**Errors**:
- `404` — Analysis not found.

---

### `POST /api/analyses/{analysis_id}/retry`

Retry a failed analysis. Only analyses with status `error` can be retried.

**Path parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `analysis_id` | int | ID of the analysis record |

**Response** `202`:
```json
{"message": "Analysis queued for retry", "analysis_id": 1}
```

**Errors**:
- `404` — Analysis not found.
- `400` — Analysis is not in `error` status.

---

### `GET /api/statistics`

Dashboard statistics as JSON.

**Response** `200`:
```json
{
  "total_analyses": 0,
  "all_clear_count": 0,
  "fix_pr_ready_count": 0,
  "open_analyses": 0,
  "error_count": 0,
  "error_rate_percentage": 0.0,
  "timeout_count": 0,
  "timeout_rate_percentage": 0.0,
  "total_drift_detected": 0,
  "total_fix_prs_created": 0,
  "average_resolution_minutes": 0.0
}
```

---

### `GET /dashboard`

Web dashboard UI. Renders an HTML page showing statistics, analysis history, and an audit trigger form.

---

### Analysis Object

All analysis endpoints return objects with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Unique analysis ID |
| `repository_full_name` | string | Repository that was analyzed |
| `pull_request_number` | int \| null | PR number (if triggered by webhook) |
| `pull_request_title` | string \| null | PR title |
| `pull_request_url` | string \| null | PR URL |
| `trigger_type` | string | One of: `pull_request_webhook`, `repository_audit_scan`, `manual_trigger` |
| `devin_session_id` | string \| null | Devin session ID |
| `devin_session_url` | string \| null | Devin session URL |
| `analysis_status` | string | One of: `pending`, `analyzing`, `no_drift_detected`, `drift_detected`, `fix_pr_created`, `error` |
| `drift_detected` | bool \| null | Whether drift was found |
| `drift_summary` | string \| null | Human-readable summary of drift |
| `endpoints_changed` | array \| null | List of changed endpoints (method, path, change_type, documentation_updated) |
| `confidence_level` | string \| null | One of: `high`, `medium`, `low` |
| `fix_pull_request_url` | string \| null | URL of the fix PR (if created) |
| `error_message` | string \| null | Error description (if status is `error`) |
| `created_at` | string | ISO 8601 timestamp |
| `updated_at` | string | ISO 8601 timestamp |

## Dashboard

The dashboard shows:

- **Stats cards**: All Clear | Fix PR Ready | Devin is working. | Devin needs help
- **Secondary metrics**: Average resolution time, error rate, total analyses
- **Analysis history**: Table with links to source PRs, Devin sessions, and fix PRs — filterable by clicking a stat card
- **Audit trigger**: Form to scan any repository for documentation drift

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Linting

```bash
ruff check app/ tests/
```
