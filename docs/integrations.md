# GitHub and Jira Integration

## Purpose

ProtoPilot moves generated project output into delivery tools:

- GitHub export uses the GitHub REST API to transfer generated code without sending file contents through an LLM.
- Jira task creation uses Atlassian MCP because it needs Jira workspace/tool access.

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

The backend creates blobs, a tree, a commit, a new branch, and a pull request through the GitHub REST API. Generated file contents are not included in an LLM prompt.

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

Jira authentication is handled by `mcp-remote`; the OAuth flow may open a browser on first use. Jira uses a Jira-only integration agent session so it does not initialize GitHub tooling.

## Notes

Streaming is intentionally left for later.
