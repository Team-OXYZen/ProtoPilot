# GitHub, Jira & Confluence Integration

## Overview

| Integration | Transport | Auth |
|---|---|---|
| GitHub export | GitHub REST API (direct, no agent) | Per-user OAuth2 |
| Jira backlog | ADK integration agent + Atlassian REST API FunctionTools | Per-user OAuth2 |
| Confluence export | Atlassian Confluence REST API (direct, no agent) | Per-user OAuth2 |

GitHub export creates blobs, tree, commit, branch, and PR directly via the GitHub REST API — file content is never sent to an LLM. Jira backlog creation is handled by an ADK `LlmAgent` equipped with `FunctionTool` wrappers around the Atlassian REST API. Confluence export is deterministic: the backend creates or updates every artifact page directly through the Confluence v2 REST API.

OAuth tokens are stored per user in SQLite. There are no global service tokens.

---

## Configuration

Some values are server/runtime credentials and must stay in `backend/.env`. Integration destination values and integration OAuth app credentials can be set either in `backend/.env` or by each user in the dashboard **Preferences → Connection Settings** popup.

### Env-only Runtime Variables

These are not configurable from the UI:

```env
CLIENT_ID=
CLIENT_SECRET=

LITELLM_MODEL=
LITELLM_API_BASE=
LITELLM_API_KEY=

JWT_SECRET=
BACKEND_URL=http://127.0.0.1:8000
FRONTEND_URL=http://127.0.0.1:4200
```

`CLIENT_ID` / `CLIENT_SECRET` are used to obtain the upstream OAuth token for the private LLM service. LiteLLM settings are used by all generation agents.

### UI-configurable Integration Values

Users can configure these from the dashboard Preferences popup. Saved secret values are masked in the UI and stored per user in SQLite.

```env
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_OWNER=
GITHUB_REPO=

ATLASSIAN_CLIENT_ID=
ATLASSIAN_CLIENT_SECRET=
JIRA_PROJECT_KEY=
CONFLUENCE_SPACE_KEY=
CONFLUENCE_PARENT_PAGE_TITLE=
```

The backend resolves these in this order: request body when supported → user preference → `.env` → default/discovery behavior.

### GitHub OAuth

```env
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_OAUTH_REDIRECT_URI=        # optional; defaults to {BACKEND_URL}/integrations/github/oauth/callback
GITHUB_OAUTH_SCOPE=repo           # optional; defaults to "repo"
```

Create the GitHub OAuth app in GitHub under **Settings → Developer settings → OAuth Apps → New OAuth App**. For an organization-owned app, use the organization settings instead.

Use these URLs:

```text
Homepage URL:              {FRONTEND_URL}
Authorization callback URL: {BACKEND_URL}/integrations/github/oauth/callback
```

The default scope is `repo`, because the export flow needs to create Git blobs, commits, branches, and pull requests in the target repository. For public repositories only, this can be reduced to `public_repo`, but private repository export requires `repo`.

### Atlassian OAuth

```env
ATLASSIAN_CLIENT_ID=
ATLASSIAN_CLIENT_SECRET=
ATLASSIAN_OAUTH_REDIRECT_URI=     # optional; defaults to {BACKEND_URL}/integrations/atlassian/oauth/callback
```

Create the Atlassian OAuth app in the [Atlassian Developer Console](https://developer.atlassian.com/console/myapps/) with an **OAuth 2.0 (3LO)** integration. Add this callback URL:

```text
{BACKEND_URL}/integrations/atlassian/oauth/callback
```

Required Atlassian scopes:

```text
read:me
offline_access
read:jira-user
read:jira-work
write:jira-work
manage:jira-project
manage:jira-configuration
read:space:confluence
write:space:confluence
read:page:confluence
write:page:confluence
read:content:confluence
write:content:confluence
read:user:confluence
```

Jira needs read/write issue permissions plus project/board management so the agent can discover projects, create Scrum projects when needed, create issues, create sprints, and move issues into sprints. Confluence needs space/page/content read-write scopes so the backend can find spaces, create spaces when needed, find pages, and create or update exported pages.

### Destination Defaults

```env
GITHUB_OWNER=
GITHUB_REPO=
GITHUB_BASE_BRANCH=main          # env-only fallback for export base branch
JIRA_PROJECT_KEY=
CONFLUENCE_SPACE_KEY=
CONFLUENCE_PARENT_PAGE_TITLE=
```

`GITHUB_OWNER`, `GITHUB_REPO`, `JIRA_PROJECT_KEY`, `CONFLUENCE_SPACE_KEY`, and `CONFLUENCE_PARENT_PAGE_TITLE` are configurable from the dashboard Preferences popup. `GITHUB_BASE_BRANCH` remains env-only unless a request explicitly sends `base_branch`.

---

## OAuth Endpoints

All endpoints require `Authorization: Bearer <token>` except the OAuth callbacks.

### GitHub

| Method | Path | Description |
|---|---|---|
| `GET` | `/integrations/github/oauth/start` | Returns `{authorization_url}` |
| `GET` | `/integrations/github/oauth/callback` | Exchanges code, stores user token, closes popup |
| `GET` | `/integrations/github/oauth/status` | Returns `{connected, github_username}` |
| `DELETE` | `/integrations/github/oauth/disconnect` | Clears stored token |

### Atlassian

| Method | Path | Description |
|---|---|---|
| `GET` | `/integrations/atlassian/oauth/start` | Returns `{authorization_url}` |
| `GET` | `/integrations/atlassian/oauth/callback` | Exchanges code, stores access + refresh token, closes popup |
| `GET` | `/integrations/atlassian/oauth/status` | Returns `{connected, atlassian_username}` |
| `DELETE` | `/integrations/atlassian/oauth/disconnect` | Clears stored token |

---

## GitHub Export

**`POST /integrations/github/export`**

Requires GitHub account connected. Either `project_id` (loads generated files from disk) or explicit `files` must be provided.

```json
{
  "project_id": "my-project",
  "owner": "github-org",               // falls back to user preference → GITHUB_OWNER
  "repo": "target-repo",               // falls back to user preference → GITHUB_REPO
  "base_branch": "main",               // falls back to GITHUB_BASE_BRANCH → "main"
  "new_branch": "protopilot-export-x", // auto-generated if omitted
  "commit_message": "...",
  "pull_request_title": "...",
  "pull_request_body": "...",
  "files": [                           // optional; overrides project_id lookup
    { "path": "src/app.ts", "content": "..." }
  ]
}
```

**Response:**

```json
{
  "ok": true,
  "branch": "protopilot-export-my-project-a1b2c3d4",
  "commit_sha": "abc123...",
  "pull_request_url": "https://github.com/org/repo/pull/42",
  "files_exported": 7
}
```

---

## Jira Backlog Creation

**`POST /integrations/jira/create-tasks`**

Requires Atlassian account connected. One of `jira_context`, `product_plan`, `tasks`, or `project_id` must be provided.

```json
{
  "project_id": "my-project",         // loads jira_plan artifact from disk
  "jira_project_key": "PROTO",        // falls back to user preference → JIRA_PROJECT_KEY
  "jira_context": { ... },            // explicit context; overrides project_id
  "product_plan": { ... },            // alternative explicit input
  "tasks": [                          // lowest-priority explicit input
    {
      "title": "...",
      "description": "...",
      "acceptance_criteria": ["..."],
      "priority": "Medium"
    }
  ]
}
```

The integration agent creates a Jira Software Scrum hierarchy (Epics → Stories → Sub-tasks) using `FunctionTool` wrappers over the Atlassian REST API. It calls `get_jira_project_meta` to inspect available issue types and fields before creating issues.

**Response:**

```json
{ "ok": true, "reply": "Created 3 Epics, 12 Stories, 28 Sub-tasks in PROTO." }
```

---

## Confluence Artifact Export

**`POST /integrations/confluence/export-artifacts`**

Requires Atlassian account connected. Either `project_id` or explicit `pages` must be provided.

```json
{
  "project_id": "my-project",
  "confluence_space_key": "PROTO",      // falls back to user preference → CONFLUENCE_SPACE_KEY
  "parent_page_title": "ProtoPilot",    // falls back to user preference → CONFLUENCE_PARENT_PAGE_TITLE
  "pages": [                            // optional; overrides project_id lookup
    { "title": "PRD", "content": "# PRD\n..." }
  ]
}
```

The backend resolves the target space, then creates or updates one page per artifact in Confluence storage format (XML). Existing pages with matching titles are updated rather than duplicated. Mermaid diagrams and code blocks are exported as Confluence code macros. The response reports `pages_requested` and `pages_exported` so the UI can show whether every document was exported.

**Response:**

```json
{
  "ok": true,
  "space_key": "PROTO",
  "pages_requested": 5,
  "pages_exported": 5,
  "reply": "Exported 5 of 5 documents to Confluence."
}
```

---

## Atlassian FunctionTools Reference

The integration agent has access to the following tools bound to the user's personal OAuth token:

| Tool | Description |
|---|---|
| `get_atlassian_accessible_sites` | Discovery — returns all accessible cloud sites and their `cloud_id` |
| `list_jira_projects` | Lists Jira Software projects in a site |
| `create_jira_project` | Creates a new Scrum/Kanban project |
| `get_jira_project_meta` | Returns available issue types and fields for a project |
| `create_jira_issue` | Creates an Epic, Story, Task, Sub-task, or Bug |
| `get_jira_boards` | Lists boards to get `board_id` for sprint creation |
| `create_jira_sprint` | Creates a sprint on a Scrum board |
| `move_issues_to_sprint` | Moves issues into a sprint |
| `list_confluence_spaces` | Lists Confluence spaces (returns numeric `space_id`) |
| `create_confluence_space` | Creates a new global Confluence space |
| `find_confluence_page` | Finds a page by title; returns `page_id` and `version` |
| `create_confluence_page` | Creates a page in Confluence storage format |
| `update_confluence_page` | Updates an existing page (increments version) |
