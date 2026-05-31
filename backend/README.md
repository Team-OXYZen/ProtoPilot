# ProtoPilot Backend

FastAPI + Google ADK multi-agent backend for AI-driven prototype generation.

## Setup

```bash
cp .env.example .env  # fill in credentials
uvicorn api.server:app --reload --port 8000
```

Key environment variables are documented in `.env.example`. Integration-related values include:

| Variable | Purpose |
|---|---|
| `BACKEND_URL` | Public/local backend base URL used for generated callbacks. |
| `FRONTEND_URL` | Public/local frontend URL used after GitHub OAuth returns. |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | GitHub OAuth app credentials for user-scoped code export. |
| `GITHUB_OAUTH_REDIRECT_URI` | Optional explicit GitHub callback URL. Defaults from `BACKEND_URL`. |
| `GITHUB_OAUTH_SCOPE` | GitHub OAuth scope, defaults to `repo`. |
| `GITHUB_TOKEN` | Optional server token used only when initializing GitHub MCP tooling. |
| `JIRA_PROJECT_KEY` | Optional default Jira project key. If omitted, the Atlassian agent discovers or creates a suitable Scrum software project. |
| `CONFLUENCE_SPACE_KEY` | Optional default Confluence space key. If omitted, the Atlassian agent discovers or creates a suitable space. |
| `LITELLM_MODEL_INTEGRATION` | Optional model override for GitHub/Jira/Confluence integration work. |

## Completed Workflow

The backend runs a stage-driven pipeline. Each user message hits `POST /chat` and the orchestrator routes it based on the current project stage.

### Stage Flow

```
REQ → ARTIFACTS_NON_TECH → WAIT_APPROVAL → TECH_ARTIFACTS → CODEGEN → QA
```

| Stage | What happens |
|---|---|
| **REQ** | Requirements agent gathers info via Q&A. On completion, auto-submits spec and immediately triggers non-tech artifact generation. |
| **ARTIFACTS_NON_TECH** | Artifacts agent generates PM-facing documents (user stories, feature list, etc.) in markdown. Stage moves to WAIT_APPROVAL on success. |
| **WAIT_APPROVAL** | No model call. User sends `approve` → moves to TECH_ARTIFACTS. User sends `change` → drops back to REQ for revision. |
| **TECH_ARTIFACTS** | Artifacts agent generates technical documents (data model, API spec, system design, etc.). Stage moves to CODEGEN on success. |
| **CODEGEN** | Code generation agent produces a POC Angular frontend with mocked API calls. Stage moves to QA on success. |
| **QA** | QA agent handles user feedback. Classifies each request and updates code, docs, or both accordingly. |

### QA Agent Behavior

The QA agent classifies user feedback into three categories:

- **code_only** — UI/styling (colors, layout, fonts): updates Angular files only
- **docs_only** — Doc/spec changes (rename, descriptions): updates artifact markdown only
- **both** — Functional changes (new feature, entity, screen): updates artifacts then regenerates affected code

### Key Behaviors

- `ARTIFACTS_NON_TECH` is triggered **automatically** after REQ completes — no separate call needed
- `TECH_ARTIFACTS` + `CODEGEN` are triggered automatically after approval
- Project state is persisted — reloading a project from the dashboard restores all artifacts and generated code
- Each response includes `nontech_artifacts_md`, `technical_artifacts_md`, and `generated_code_files` so the frontend always has the latest data
- Code generation writes files one at a time via `patch_generated_code_file` to avoid WAF blocking large payloads
