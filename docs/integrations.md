# GitHub and Jira MCP Integration

## Purpose

ProtoPilot uses MCP integrations to move generated project output into delivery tools:

- GitHub MCP exports ProtoPilot generated code to GitHub.
- Jira MCP creates Jira tasks from ProtoPilot requirements.

GitHub export should create a branch and pull request. It should not push directly to `main`.

## Environment Variables

Set these in `backend/.env`:

```env
GITHUB_TOKEN=
GITHUB_OWNER=Team-OXYZen
GITHUB_REPO=ProtoPilot
JIRA_PROJECT_KEY=PROTO
LITELLM_MODEL_INTEGRATION=
```

Do not commit real secrets.

## Run Backend

```bash
cd backend
uvicorn api.server:app --reload --port 8000
```

## Test GitHub Export

Use `POST /integrations/github/export`.

Example using generated project files:

```bash
curl -X POST http://localhost:8000/integrations/github/export \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "demo-project",
    "session_id": "demo-integration-session"
  }'
```

Example using explicit files:

```bash
curl -X POST http://localhost:8000/integrations/github/export \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "manual-github-export",
    "owner": "Team-OXYZen",
    "repo": "ProtoPilot",
    "files": [
      {
        "path": "generated/README.md",
        "content": "# Generated Prototype\n"
      }
    ]
  }'
```

The integration agent is instructed to create a new branch, commit generated files, and open a pull request.

## Test Jira Task Creation

Use `POST /integrations/jira/create-tasks`.

Example using tasks derived from project requirements:

```bash
curl -X POST http://localhost:8000/integrations/jira/create-tasks \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "demo-project",
    "session_id": "demo-jira-session"
  }'
```

Example using explicit tasks:

```bash
curl -X POST http://localhost:8000/integrations/jira/create-tasks \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "manual-jira-create",
    "jira_project_key": "PROTO",
    "tasks": [
      {
        "title": "Review generated prototype",
        "description": "Review the exported ProtoPilot prototype for completeness.",
        "acceptance_criteria": [
          "Prototype files are reviewed.",
          "Follow-up defects are documented."
        ],
        "priority": "Medium"
      }
    ]
  }'
```

Jira authentication is handled by `mcp-remote`; the OAuth flow may open a browser on first use.

## Notes

Streaming is intentionally left for later.
