# GitHub, Jira & Confluence Integration

## Overview

| Integration | Transport | Auth |
|---|---|---|
| GitHub export | GitHub REST API (direct, no agent) | Per-user OAuth2 |
| Jira backlog | ADK integration agent + Atlassian REST API FunctionTools | Per-user OAuth2 |
| Confluence export | ADK integration agent + Atlassian REST API FunctionTools | Per-user OAuth2 |

GitHub export creates blobs, tree, commit, branch, and PR directly via the GitHub REST API — file content is never sent to an LLM. Jira and Confluence operations are handled by an ADK `LlmAgent` equipped with `FunctionTool` wrappers around the Atlassian REST API (Jira v3, Confluence v2).

OAuth tokens are stored per user in SQLite. There are no global service tokens.

---

## Environment Variables

Set in `backend/.env`.

### GitHub OAuth

```env
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_OAUTH_REDIRECT_URI=        # optional; defaults to {BACKEND_URL}/integrations/github/oauth/callback
GITHUB_OAUTH_SCOPE=repo           # optional; defaults to "repo"
```

### Atlassian OAuth

```env
ATLASSIAN_CLIENT_ID=
ATLASSIAN_CLIENT_SECRET=
ATLASSIAN_OAUTH_REDIRECT_URI=     # optional; defaults to {BACKEND_URL}/integrations/atlassian/oauth/callback
```

### Defaults (can be overridden per user via Preferences)

```env
GITHUB_OWNER=
GITHUB_REPO=
GITHUB_BASE_BRANCH=main
JIRA_PROJECT_KEY=
CONFLUENCE_SPACE_KEY=
CONFLUENCE_PARENT_PAGE_TITLE=
```

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
  "base_branch": "main",               // falls back to user preference → GITHUB_BASE_BRANCH
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

The integration agent calls `list_confluence_spaces`, resolves or creates the target space, then creates or updates one page per artifact in Confluence storage format (XML). Existing pages with matching titles are updated rather than duplicated.

**Response:**

```json
{ "ok": true, "reply": "Created 5 pages in space PROTO." }
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
