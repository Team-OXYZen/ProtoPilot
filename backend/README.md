# ProtoPilot Backend

FastAPI + Google ADK multi-agent backend for AI-driven prototype generation.

## Quick Start

```bash
cp .env.example .env   # fill in credentials
uvicorn api.server:app --reload --port 8000
```

Requires Docker for the live deploy feature.

---

## Environment Variables

Full reference in `.env.example`. Key variables:

- `LITELLM_MODEL` / `LITELLM_API_KEY` — default model and credentials for all agents
- `CLIENT_ID` / `CLIENT_SECRET` — upstream OAuth credentials for the private LLM service
- `JWT_SECRET` — HS256 signing secret; required in production
- `BACKEND_URL` / `FRONTEND_URL` — used for OAuth callback construction and redirects
- `DEPLOY_HOST` — public host for live preview URLs; set to server IP/domain in cloud

Integration values can be configured in two places:

- Env-only: `CLIENT_ID`, `CLIENT_SECRET`, LiteLLM settings, `JWT_SECRET`, app URLs, database paths, and deploy host.
- Dashboard Preferences: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_OWNER`, `GITHUB_REPO`, `ATLASSIAN_CLIENT_ID`, `ATLASSIAN_CLIENT_SECRET`, `JIRA_PROJECT_KEY`, `CONFLUENCE_SPACE_KEY`, and `CONFLUENCE_PARENT_PAGE_TITLE`.

GitHub and Atlassian OAuth app setup, callback URLs, and required scopes are documented in [docs/integrations.md](../docs/integrations.md).

---

## API Routes


| Prefix | Description |
|---|---|
| `/auth` | Login, register |
| `/projects` | CRUD, stage control |
| `/projects/{id}/deploy` | Live deploy (see below) |
| `/chat` | Main agent interaction |
| `/preferences` | Per-user non-secret settings |
| `/integrations` | GitHub / Jira / Confluence (see [docs/integrations.md](../docs/integrations.md)) |

---

## Stage Pipeline

User messages hit `POST /chat`; the orchestrator routes by the project's current stage.

```
REQ → ARTIFACTS_NON_TECH → WAIT_APPROVAL → TECH_ARTIFACTS → CODEGEN → QA → FINALIZE → QA
```

Manual gates: `WAIT_APPROVAL`（`approve` / `change`）and `QA → FINALIZE`（user sends `finalize`）. All other transitions are automatic.

- `CODEGEN` generates the Angular frontend, runs build verification and UX review, then advances to `QA`
- `FINALIZE` generates the Java Spring Boot backend and wires up real API calls in Angular, then returns to `QA`

---

## Live Deploy

`POST /projects/{id}/deploy` writes generated files to `~/protopilot-projects/{project_id}/`, runs `docker compose up`, and allocates a port in `5001–5999`.

| Endpoint | Description |
|---|---|
| `POST /projects/{id}/deploy` | Build and start; returns `{status, port}` |
| `GET /projects/{id}/deploy/status` | Returns `building`, `running`, or `failed` |
| `POST /projects/{id}/undeploy` | Stop and remove containers |

Port assignments persist in `~/protopilot-projects/port_registry.json` and are restored on startup.
