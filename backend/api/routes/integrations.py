import json
import os
import uuid
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
import httpx
from pydantic import BaseModel

from agents.registry import AGENT_FACTORIES
from core.auth import get_current_user, get_oauth_token
from core.logging_utils import log_event
from core.runner import run_turn
from core.user_store import (
    consume_github_oauth_state,
    get_github_connection,
    save_github_connection,
    save_github_oauth_state,
)
from orchestration.integration_payloads import (
    build_confluence_pages_from_project,
    build_github_files_from_project,
    build_jira_context_from_project,
)

router = APIRouter(prefix="/integrations")
GITHUB_API_BASE = "https://api.github.com"
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"


class GitHubFile(BaseModel):
    path: str
    content: str


class GitHubExportRequest(BaseModel):
    project_id: str | None = None
    session_id: str | None = None
    owner: str | None = None
    repo: str | None = None
    base_branch: str = "main"
    new_branch: str | None = None
    commit_message: str | None = None
    pull_request_title: str | None = None
    pull_request_body: str | None = None
    files: list[GitHubFile] | None = None


class GitHubOAuthStartResponse(BaseModel):
    authorization_url: str


class GitHubConnectionStatus(BaseModel):
    connected: bool
    github_username: str | None = None


class JiraCreateTasksRequest(BaseModel):
    project_id: str | None = None
    session_id: str | None = None
    jira_project_key: str | None = None
    jira_context: dict[str, Any] | None = None
    product_plan: dict[str, Any] | None = None
    tasks: list[dict[str, Any]] | None = None


class ConfluenceExportRequest(BaseModel):
    project_id: str | None = None
    session_id: str | None = None
    confluence_space_key: str | None = None
    parent_page_title: str | None = None
    pages: list[dict[str, Any]] | None = None


def _model_to_dict(model: BaseModel) -> dict:
    """Return a Pydantic model as a plain dict across Pydantic v1/v2."""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _safe_session_id(_req_session_id: str | None, project_id: str | None, action: str) -> str:
    """Build a stable ADK-safe integration session id for one external action."""
    raw_session_id = f"integration-{action}-{project_id or uuid.uuid4().hex[:8]}"
    safe_chars = []
    for char in raw_session_id:
        safe_chars.append(char if char.isalnum() or char in "-_" else "-")
    return "".join(safe_chars)


def _json_prompt_payload(payload: dict) -> str:
    """Serialize prompt payloads with readable indentation for the integration agent."""
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _github_headers(token: str) -> dict[str, str]:
    """Create GitHub API headers without logging or exposing the token."""
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _github_oauth_config() -> tuple[str, str, str]:
    """Read GitHub OAuth configuration and fail fast when it is incomplete."""
    client_id = os.getenv("GITHUB_CLIENT_ID")
    client_secret = os.getenv("GITHUB_CLIENT_SECRET")
    redirect_uri = os.getenv("GITHUB_OAUTH_REDIRECT_URI", "http://127.0.0.1:8000/integrations/github/oauth/callback")
    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="GitHub OAuth client id and secret are required.")
    return client_id, client_secret, redirect_uri


async def _github_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    expected_status: int | tuple[int, ...],
    **kwargs,
) -> dict:
    """Send a GitHub API request and convert non-expected statuses into HTTP errors."""
    log_event("TOOL", "github_api_request", {"method": method, "url": url, "expected_status": expected_status})
    response = await client.request(method, url, **kwargs)
    expected = (expected_status,) if isinstance(expected_status, int) else expected_status
    if response.status_code not in expected:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        log_event("ERROR", "github_api_request_failed", {"method": method, "url": url, "status_code": response.status_code, "detail": detail}, status="fail")
        raise HTTPException(status_code=response.status_code, detail=detail)
    log_event("TOOL", "github_api_request_done", {"method": method, "url": url, "status_code": response.status_code}, status="ok")
    if response.status_code == 204 or not response.content:
        return {}
    return response.json()


async def _github_ref_exists(client: httpx.AsyncClient, owner: str, repo: str, branch: str) -> bool:
    """Check whether a branch ref already exists in the target GitHub repository."""
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/ref/heads/{branch}"
    log_event("TOOL", "github_ref_check", {"owner": owner, "repo": repo, "branch": branch})
    response = await client.get(url)
    if response.status_code == 200:
        log_event("TOOL", "github_ref_check_done", {"owner": owner, "repo": repo, "branch": branch, "exists": True}, status="ok")
        return True
    if response.status_code == 404:
        log_event("TOOL", "github_ref_check_done", {"owner": owner, "repo": repo, "branch": branch, "exists": False}, status="ok")
        return False
    try:
        detail = response.json()
    except ValueError:
        detail = response.text
    log_event("ERROR", "github_ref_check_failed", {"owner": owner, "repo": repo, "branch": branch, "status_code": response.status_code, "detail": detail}, status="fail")
    raise HTTPException(status_code=response.status_code, detail=detail)


def _resolve_github_branch(req: GitHubExportRequest) -> str:
    """Resolve a user-provided branch or generate a unique export branch name."""
    if req.new_branch:
        return req.new_branch
    suffix = uuid.uuid4().hex[:8]
    project_part = req.project_id or "manual"
    return f"protopilot-export-{project_part}-{suffix}"


async def _export_files_to_github(
    *,
    github_token: str,
    owner: str,
    repo: str,
    base_branch: str,
    new_branch: str,
    commit_message: str,
    pull_request_title: str,
    pull_request_body: str | None,
    files: list[dict],
) -> dict:
    """Create blobs, tree, commit, branch, and pull request for generated files."""
    log_event(
        "TOOL",
        "github_export_start",
        {"owner": owner, "repo": repo, "base_branch": base_branch, "new_branch": new_branch, "files_count": len(files)},
    )
    async with httpx.AsyncClient(headers=_github_headers(github_token), timeout=60) as client:
        if await _github_ref_exists(client, owner, repo, new_branch):
            raise HTTPException(status_code=409, detail=f"GitHub branch '{new_branch}' already exists.")

        base_ref = await _github_request(
            client,
            "GET",
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/ref/heads/{base_branch}",
            expected_status=200,
        )
        base_commit_sha = base_ref["object"]["sha"]

        base_commit = await _github_request(
            client,
            "GET",
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/commits/{base_commit_sha}",
            expected_status=200,
        )
        base_tree_sha = base_commit["tree"]["sha"]

        tree_entries = []
        for index, file in enumerate(files, start=1):
            log_event("TOOL", "github_blob_create", {"index": index, "files_count": len(files), "path": file["path"]})
            blob = await _github_request(
                client,
                "POST",
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/blobs",
                expected_status=201,
                json={
                    "content": file["content"],
                    "encoding": "utf-8",
                },
            )
            tree_entries.append({
                "path": file["path"],
                "mode": "100644",
                "type": "blob",
                "sha": blob["sha"],
            })

        log_event("TOOL", "github_tree_create", {"owner": owner, "repo": repo, "entries_count": len(tree_entries)})
        tree = await _github_request(
            client,
            "POST",
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees",
            expected_status=201,
            json={
                "base_tree": base_tree_sha,
                "tree": tree_entries,
            },
        )

        log_event("TOOL", "github_commit_create", {"owner": owner, "repo": repo, "parent": base_commit_sha, "files_count": len(files)})
        commit = await _github_request(
            client,
            "POST",
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/commits",
            expected_status=201,
            json={
                "message": commit_message,
                "tree": tree["sha"],
                "parents": [base_commit_sha],
            },
        )

        log_event("TOOL", "github_branch_create", {"owner": owner, "repo": repo, "branch": new_branch, "commit_sha": commit["sha"]})
        await _github_request(
            client,
            "POST",
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/refs",
            expected_status=201,
            json={
                "ref": f"refs/heads/{new_branch}",
                "sha": commit["sha"],
            },
        )

        log_event("TOOL", "github_pr_create", {"owner": owner, "repo": repo, "head": new_branch, "base": base_branch})
        pull_request = await _github_request(
            client,
            "POST",
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls",
            expected_status=201,
            json={
                "title": pull_request_title,
                "head": new_branch,
                "base": base_branch,
                "body": pull_request_body,
            },
        )

    result = {
        "branch": new_branch,
        "commit_sha": commit["sha"],
        "pull_request_url": pull_request.get("html_url"),
        "files_exported": len(files),
    }
    log_event("TOOL", "github_export_done", {"owner": owner, "repo": repo, **result}, status="ok")
    return result


@router.get("/github/oauth/start", response_model=GitHubOAuthStartResponse)
def start_github_oauth(current_user: dict[str, str] = Depends(get_current_user)):
    """Start GitHub OAuth by storing state and returning the authorization URL."""
    client_id, _client_secret, redirect_uri = _github_oauth_config()
    state = uuid.uuid4().hex
    save_github_oauth_state(state, current_user["username"])
    log_event("TOOL", "github_oauth_start", {"username": current_user["username"], "redirect_uri": redirect_uri})

    query = urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": os.getenv("GITHUB_OAUTH_SCOPE", "repo"),
        "state": state,
    })
    return {"authorization_url": f"{GITHUB_AUTHORIZE_URL}?{query}"}


@router.get("/github/oauth/status", response_model=GitHubConnectionStatus)
def github_oauth_status(current_user: dict[str, str] = Depends(get_current_user)):
    """Return whether the current user has an active GitHub OAuth connection."""
    connection = get_github_connection(current_user["username"])
    if not connection:
        log_event("TOOL", "github_oauth_status", {"username": current_user["username"], "connected": False}, status="ok")
        return {"connected": False, "github_username": None}
    log_event("TOOL", "github_oauth_status", {"username": current_user["username"], "connected": True, "github_username": connection.get("github_username")}, status="ok")
    return {
        "connected": True,
        "github_username": connection.get("github_username"),
    }


@router.get("/github/oauth/callback")
async def github_oauth_callback(code: str, state: str):
    """Handle GitHub OAuth callback, exchange code, and save the user connection."""
    username = consume_github_oauth_state(state)
    if not username:
        log_event("ERROR", "github_oauth_callback_invalid_state", {"state_present": bool(state)}, status="fail")
        raise HTTPException(status_code=400, detail="Invalid or expired GitHub OAuth state.")

    client_id, client_secret, redirect_uri = _github_oauth_config()
    log_event("TOOL", "github_oauth_callback_start", {"username": username, "redirect_uri": redirect_uri})
    async with httpx.AsyncClient(timeout=30) as client:
        token_response = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        token_response.raise_for_status()
        token_payload = token_response.json()

        access_token = token_payload.get("access_token")
        if not access_token:
            log_event("ERROR", "github_oauth_missing_token", {"username": username}, status="fail")
            raise HTTPException(status_code=400, detail="GitHub OAuth did not return an access token.")

        user_response = await client.get(
            f"{GITHUB_API_BASE}/user",
            headers=_github_headers(access_token),
        )
        user_response.raise_for_status()
        github_username = user_response.json().get("login")

    save_github_connection(username, access_token, github_username)
    log_event("TOOL", "github_oauth_callback_done", {"username": username, "github_username": github_username}, status="ok")
    frontend_url = os.getenv("FRONTEND_URL", "http://127.0.0.1:4200")
    return RedirectResponse(f"{frontend_url}/spec-review?github_connected=1")


@router.post("/github/export")
async def export_github(req: GitHubExportRequest, current_user: dict[str, str] = Depends(get_current_user)):
    """Export generated project files to a GitHub branch and open a pull request."""
    try:
        log_event(
            "TOOL",
            "github_export_request",
            {
                "username": current_user["username"],
                "project_id": req.project_id,
                "owner": req.owner,
                "repo": req.repo,
                "base_branch": req.base_branch,
                "has_manual_files": req.files is not None,
            },
        )
        if req.files is not None:
            files = [_model_to_dict(file) for file in req.files]
        elif req.project_id:
            files = build_github_files_from_project(req.project_id)
        else:
            raise HTTPException(status_code=400, detail="Either files or project_id is required.")

        owner = req.owner
        repo = req.repo
        if not owner or not repo:
            log_event("ERROR", "github_export_missing_repo", {"project_id": req.project_id, "owner": owner, "repo": repo}, status="fail")
            raise HTTPException(status_code=400, detail="GitHub owner and repo are required.")

        connection = get_github_connection(current_user["username"])
        if not connection:
            log_event("ERROR", "github_export_not_connected", {"username": current_user["username"]}, status="fail")
            raise HTTPException(status_code=400, detail="Connect your GitHub account before exporting.")
        github_token = connection.get("access_token")
        if not github_token:
            log_event("ERROR", "github_export_missing_token", {"username": current_user["username"]}, status="fail")
            raise HTTPException(status_code=400, detail="Connect your GitHub account before exporting.")

        result = await _export_files_to_github(
            github_token=github_token,
            owner=owner,
            repo=repo,
            base_branch=req.base_branch,
            new_branch=_resolve_github_branch(req),
            commit_message=req.commit_message or "Export ProtoPilot generated code",
            pull_request_title=req.pull_request_title or "Export ProtoPilot generated code",
            pull_request_body=req.pull_request_body,
            files=files,
        )

        response = {"ok": True, **result}
        log_event("TOOL", "github_export_response", {"project_id": req.project_id, "owner": owner, "repo": repo, **result}, status="ok")
        return response

    except HTTPException:
        raise
    except ValueError as e:
        log_event("ERROR", "github_export_validation_error", {"project_id": req.project_id, "error": str(e)}, status="fail")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log_event("ERROR", "github_export_error", {"project_id": req.project_id, "error": str(e)}, status="fail")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jira/create-tasks")
async def create_jira_tasks(req: JiraCreateTasksRequest, _current_user: dict[str, str] = Depends(get_current_user)):
    """Ask the Jira integration agent to design and create an agile backlog from project context."""
    try:
        log_event(
            "TOOL",
            "jira_create_tasks_request",
            {
                "project_id": req.project_id,
                "session_id": req.session_id,
                "jira_project_key": req.jira_project_key or os.getenv("JIRA_PROJECT_KEY"),
                "has_jira_context": req.jira_context is not None,
                "has_product_plan": req.product_plan is not None,
                "has_manual_tasks": req.tasks is not None,
            },
        )
        if req.jira_context is not None:
            jira_context = req.jira_context
        elif req.product_plan is not None:
            jira_context = {"provided_product_plan": req.product_plan}
        elif req.tasks is not None:
            jira_context = {"provided_tasks": req.tasks}
        elif req.project_id:
            jira_context = build_jira_context_from_project(req.project_id)
        else:
            raise HTTPException(status_code=400, detail="Either jira_context, product_plan, tasks, or project_id is required.")

        jira_project_key = req.jira_project_key or os.getenv("JIRA_PROJECT_KEY")

        payload = {
            "jira_project_key": jira_project_key,
            "primary_backlog_source": "project_context.jira_plan_artifact",
            "project_context": jira_context,
        }

        prompt = (
            "Use the provided ProtoPilot spec and artifacts as source material, then design and create a complete Jira agile backlog.\n\n"
            "If project_context.jira_plan_artifact is present, treat it as the primary Jira backlog blueprint. Preserve its tabular values for epics, stories, sprints, tasks/sub-tasks, labels, dates, story points, acceptance criteria, dependencies, QA notes, and demo notes wherever Jira supports them. "
            "Use the broader spec, PRD, user stories, flows, and technical artifacts only to fill gaps or resolve ambiguity. "
            "Do not collapse rich jira_plan.md rows into summary/description-only issues. "
            "Before creating issues, find or create a Jira Software Scrum project/space that supports real Epic, Story, Task, Bug, and Sub-task issue types. "
            "If jira_project_key is provided, validate that it points to a suitable Jira Software Scrum project/space. If it is a Product Discovery/Discovery project or only supports Ideas, do not use it. "
            "Never create Product Discovery spaces or Idea issues for this workflow, and never put issue types in titles as a workaround. "
            "If no suitable Scrum software project/space exists, create one when the available Jira MCP tools and account permissions allow it; otherwise stop and report the exact required configuration. "
            "Create the hierarchy in this order: Epics, then Stories under each Epic, then Sub-tasks under each Story. "
            "Make the Jira project demo-rich: populate acceptance criteria, labels, priorities, severity, story points, t-shirt size, sprint, due dates, dependencies, QA notes, demo notes, components/releases, and estimates wherever Jira supports those fields. "
            "Use one-week sprints for Stories. Put due dates at sprint boundaries for Stories and within the sprint for Sub-tasks so work appears in calendar views. "
            "Create or use clearly named one-week sprints when the Jira project supports sprint creation. "
            "Do not leave supported fields empty when a sensible value can be inferred from the spec or artifacts. "
            "Apply normal agile planning standards: acceptance criteria on stories, practical priority/severity, t-shirt sizing, story points, one-week sprint slices for stories, and 2-3 day maximum sub-task scopes. "
            "Use Jira MCP to inspect available fields/project behavior and adapt to the target Jira project. "
            "If custom fields are unavailable, preserve the values in structured issue description sections and use the closest supported parent/link field. "
            "After creating issues, review them for missing rich fields and update them when Jira allows it. "
            "Avoid duplicate issues by checking for matching titles before creating anything. "
            "Use this payload:\n"
            f"{_json_prompt_payload(payload)}"
        )

        token = await get_oauth_token()
        agent = AGENT_FACTORIES["jira_integration"](token)
        session_id = _safe_session_id(req.session_id, req.project_id, "jira-create-backlog")
        log_event(
            "AGENT",
            "jira_integration_start",
            {
                "project_id": req.project_id,
                "session_id": session_id,
                "jira_project_key": jira_project_key,
                "must_use_scrum_software_project": True,
                "context_keys": list(jira_context.keys()),
            },
        )
        reply = await run_turn(
            agent,
            session_id=session_id,
            message=prompt,
        )

        log_event("AGENT", "jira_integration_done", {"project_id": req.project_id, "session_id": session_id, "reply": reply}, status="ok")
        return {"ok": True, "reply": reply}

    except HTTPException:
        raise
    except ValueError as e:
        log_event("ERROR", "jira_create_tasks_validation_error", {"project_id": req.project_id, "error": str(e)}, status="fail")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log_event("ERROR", "jira_create_tasks_error", {"project_id": req.project_id, "error": str(e)}, status="fail")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/confluence/export-artifacts")
async def export_confluence_artifacts(req: ConfluenceExportRequest, _current_user: dict[str, str] = Depends(get_current_user)):
    """Export saved artifact markdown files to Confluence pages via Atlassian MCP."""
    try:
        log_event(
            "TOOL",
            "confluence_export_request",
            {
                "project_id": req.project_id,
                "session_id": req.session_id,
                "confluence_space_key": req.confluence_space_key or os.getenv("CONFLUENCE_SPACE_KEY"),
                "has_manual_pages": req.pages is not None,
            },
        )
        if req.pages is not None:
            pages = req.pages
        elif req.project_id:
            pages = build_confluence_pages_from_project(req.project_id)
        else:
            raise HTTPException(status_code=400, detail="Either pages or project_id is required.")

        confluence_space_key = req.confluence_space_key or os.getenv("CONFLUENCE_SPACE_KEY")
        payload = {
            "confluence_space_key": confluence_space_key,
            "parent_page_title": req.parent_page_title,
            "pages": pages,
        }

        prompt = (
            "Export these ProtoPilot artifact markdown files to Confluence.\n\n"
            "Use Atlassian MCP to find the target Confluence site and space. "
            "If confluence_space_key is provided, validate and use that space. "
            "If no space key is provided, choose a clearly suitable existing documentation/product space, or create a new project documentation space when MCP permissions allow it. "
            "Create one Confluence page per artifact markdown file. Preserve markdown structure as faithfully as Confluence allows, including headings, tables, lists, code blocks, Mermaid source blocks, and links. "
            "Create or use a parent/index page when parent_page_title is provided or when multiple pages need organization. "
            "Avoid duplicates by checking for existing pages with the same title; update existing pages for this export/sync rather than creating duplicates when possible. "
            "Report created or updated page titles and URLs. "
            "Use this payload:\n"
            f"{_json_prompt_payload(payload)}"
        )

        token = await get_oauth_token()
        agent = AGENT_FACTORIES["jira_integration"](token)
        session_id = _safe_session_id(req.session_id, req.project_id, "confluence-export-artifacts")
        log_event(
            "AGENT",
            "confluence_export_start",
            {
                "project_id": req.project_id,
                "session_id": session_id,
                "confluence_space_key": confluence_space_key,
                "pages_count": len(pages),
            },
        )
        reply = await run_turn(
            agent,
            session_id=session_id,
            message=prompt,
        )

        log_event("AGENT", "confluence_export_done", {"project_id": req.project_id, "session_id": session_id, "reply": reply}, status="ok")
        return {"ok": True, "reply": reply}

    except HTTPException:
        raise
    except ValueError as e:
        log_event("ERROR", "confluence_export_validation_error", {"project_id": req.project_id, "error": str(e)}, status="fail")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log_event("ERROR", "confluence_export_error", {"project_id": req.project_id, "error": str(e)}, status="fail")
        raise HTTPException(status_code=500, detail=str(e))
