# API Documentation Drift Detector

Autonomous API documentation drift detection and remediation powered by [Devin AI](https://devin.ai).

Detects when API endpoints change but documentation doesn't, then automatically creates fix PRs.

## How It Works

### Flow 1: New Pull Requests
A GitHub webhook fires on PR creation → the backend creates a Devin session that analyzes the PR diff for API endpoint changes → if docs weren't updated, Devin creates a fix PR.

### Flow 2: Existing Code Audit
Trigger a full repository scan via the dashboard or API → Devin scans the entire codebase for undocumented or outdated API endpoints → creates a fix PR for all drift found.

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

## Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `DEVIN_API_TOKEN` | Devin API v3 token | Yes |
| `DEVIN_ORGANIZATION_ID` | Devin organization ID (org-xxx) | Yes |
| `GITHUB_WEBHOOK_SECRET` | GitHub webhook secret for signature verification | Yes |
| `DATABASE_URL` | SQLite connection string | No (default: `sqlite+aiosqlite:///./data/autodocs.db`) |
| `SESSION_POLL_INTERVAL_SECONDS` | How often to poll Devin session status | No (default: 30) |
| `SESSION_POLL_TIMEOUT_SECONDS` | Max time to wait for a session | No (default: 1800) |

## Setting Up the GitHub Webhook

1. Go to your repository → Settings → Webhooks → Add webhook
2. Set Payload URL to `https://your-host/api/github/events`
3. Set Content type to `application/json`
4. Set Secret to match your `GITHUB_WEBHOOK_SECRET`
5. Select "Pull requests" under events
6. Save

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/github/events` | GitHub webhook receiver (PR creation triggers drift analysis) |
| `POST` | `/api/repo/analyses` | Trigger a full repository documentation audit scan |
| `GET` | `/api/analyses` | List all drift analyses (paginated) |
| `GET` | `/api/analyses/{id}` | Get details of a specific analysis |
| `POST` | `/api/analyses/{id}/retry` | Retry a failed analysis |
| `GET` | `/api/statistics` | Dashboard statistics as JSON |
| `GET` | `/dashboard` | Web dashboard |
| `GET` | `/health` | Health check |

## Dashboard

The dashboard shows:

- **Stats cards**: Completed | Open | Unresolved | Errors
- **Failure metrics**: Error rate, timeout rate, average resolution time, drift detected count, fix PRs created
- **Analysis history**: Table with links to source PRs, Devin sessions, and fix PRs
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
