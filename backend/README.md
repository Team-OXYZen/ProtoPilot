# ProtoPilot Backend

FastAPI + Google ADK multi-agent backend for AI-driven prototype generation.

## Setup

```bash
cp .env.example .env  # fill in credentials
uvicorn api.server:app --reload --port 8000
```
## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CLIENT_ID` | Yes | OAuth client ID for Cotality authentication |
| `CLIENT_SECRET` | Yes | OAuth client secret for Cotality authentication |
| `LITELLM_MODEL` | Yes | Default LLM model to use (e.g., `openai/gemini-2.5-pro-litellm-usc1`) |
| `LITELLM_API_BASE` | Yes | Base URL for Cotality's LiteLLM proxy service |
| `LITELLM_API_KEY` | Yes | API key for LiteLLM service authentication |
| `LITELLM_MODEL_REQUIREMENTS` | No | Override model for Requirements Agent (falls back to `LITELLM_MODEL` if not set) |
| `LITELLM_MODEL_CODEGEN` | No | Override model for Code Generation Agent |
| `LITELLM_MODEL_QA` | No | Override model for QA Agent |
| `LITELLM_MODEL_ARTIFACTS` | No | Override model for Artifacts Agent |
| `USER_ID` | No | Current user identifier for session tracking |
| `APP_NAME` | No | Application name for logging and identification |
| `SESSION_ID` | No | Session identifier for tracking |

**Note:** Refer to `.example.env` for sample values and default configurations.
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
