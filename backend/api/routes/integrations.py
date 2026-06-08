import json
import os
import re
import uuid
from typing import Any
from html import escape
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import httpx
from pydantic import BaseModel

from agents.registry import AGENT_FACTORIES
from core.auth import get_current_user, get_oauth_token
from core.logging_utils import log_event
from core.runner import run_turn
from core.user_store import (
    consume_atlassian_oauth_state,
    consume_github_oauth_state,
    delete_atlassian_connection,
    delete_github_connection,
    get_atlassian_connection,
    get_github_connection,
    save_atlassian_connection,
    save_atlassian_oauth_state,
    save_github_connection,
    save_github_oauth_state,
    resolve_user_preference,
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

ATLASSIAN_AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
ATLASSIAN_API_BASE = "https://api.atlassian.com"
ATLASSIAN_TOKEN_URL = "https://auth.atlassian.com/oauth/token"
ATLASSIAN_ME_URL = "https://api.atlassian.com/me"
ATLASSIAN_OAUTH_SCOPE = (
    "read:me offline_access "
    "read:jira-user read:jira-work write:jira-work manage:jira-project manage:jira-configuration "
    "read:space:confluence write:space:confluence "
    "read:page:confluence write:page:confluence "
    "read:content:confluence write:content:confluence "
    "read:user:confluence "
)


class GitHubFile(BaseModel):
    path: str
    content: str


class GitHubExportRequest(BaseModel):
    project_id: str | None = None
    session_id: str | None = None
    owner: str | None = None
    repo: str | None = None
    base_branch: str | None = None
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


class AtlassianOAuthStartResponse(BaseModel):
    authorization_url: str


class AtlassianConnectionStatus(BaseModel):
    connected: bool
    atlassian_username: str | None = None


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


def _atlassian_headers(token: str) -> dict[str, str]:
    """Create Atlassian API headers without logging or exposing the token."""
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _github_headers(token: str) -> dict[str, str]:
    """Create GitHub API headers without logging or exposing the token."""
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _atlassian_oauth_config(username: str | None = None) -> tuple[str, str, str]:
    """Read Atlassian OAuth configuration and fail fast when it is incomplete."""
    client_id = resolve_user_preference(username, "ATLASSIAN_CLIENT_ID", "ATLASSIAN_CLIENT_ID") if username else os.getenv("ATLASSIAN_CLIENT_ID")
    client_secret = resolve_user_preference(username, "ATLASSIAN_CLIENT_SECRET", "ATLASSIAN_CLIENT_SECRET") if username else os.getenv("ATLASSIAN_CLIENT_SECRET")
    backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
    redirect_uri = os.getenv("ATLASSIAN_OAUTH_REDIRECT_URI", f"{backend_url}/integrations/atlassian/oauth/callback")
    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="Atlassian OAuth client_id and client_secret are required. Set ATLASSIAN_CLIENT_ID and ATLASSIAN_CLIENT_SECRET.")
    return client_id, client_secret, redirect_uri


def _github_oauth_config(username: str | None = None) -> tuple[str, str, str]:
    """Read GitHub OAuth configuration and fail fast when it is incomplete."""
    client_id = resolve_user_preference(username, "GITHUB_CLIENT_ID", "GITHUB_CLIENT_ID") if username else os.getenv("GITHUB_CLIENT_ID")
    client_secret = resolve_user_preference(username, "GITHUB_CLIENT_SECRET", "GITHUB_CLIENT_SECRET") if username else os.getenv("GITHUB_CLIENT_SECRET")
    backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
    redirect_uri = os.getenv("GITHUB_OAUTH_REDIRECT_URI", f"{backend_url}/integrations/github/oauth/callback")
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


async def _atlassian_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    expected_status: int | tuple[int, ...],
    **kwargs,
) -> dict:
    """Send an Atlassian API request and convert failures into HTTP errors."""
    log_event("TOOL", "atlassian_api_request", {"method": method, "url": url, "expected_status": expected_status})
    response = await client.request(method, url, **kwargs)
    expected = (expected_status,) if isinstance(expected_status, int) else expected_status
    if response.status_code not in expected:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        log_event("ERROR", "atlassian_api_request_failed", {"method": method, "url": url, "status_code": response.status_code, "detail": detail}, status="fail")
        raise HTTPException(status_code=response.status_code, detail=detail)
    log_event("TOOL", "atlassian_api_request_done", {"method": method, "url": url, "status_code": response.status_code}, status="ok")
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


def _cdata(text: str) -> str:
    """Wrap text for Confluence plain-text macro bodies."""
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def _split_markdown_table_row(line: str) -> list[str]:
    """Split a simple markdown table row into cells."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _flush_list(items: list[str], ordered: bool, chunks: list[str]) -> None:
    if not items:
        return
    tag = "ol" if ordered else "ul"
    chunks.append(f"<{tag}>" + "".join(f"<li>{escape(item)}</li>" for item in items) + f"</{tag}>")
    items.clear()


def _markdown_to_confluence_storage(markdown: str) -> str:
    """Convert common markdown structures to Confluence storage XML."""
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    chunks: list[str] = []
    list_items: list[str] = []
    list_ordered = False
    table_rows: list[list[str]] = []
    in_code = False
    code_language = ""
    code_lines: list[str] = []

    def flush_table() -> None:
        if not table_rows:
            return
        body_rows = []
        for row_index, row in enumerate(table_rows):
            cell_tag = "th" if row_index == 0 else "td"
            body_rows.append("<tr>" + "".join(f"<{cell_tag}>{escape(cell)}</{cell_tag}>" for cell in row) + "</tr>")
        chunks.append("<table><tbody>" + "".join(body_rows) + "</tbody></table>")
        table_rows.clear()

    def flush_code() -> None:
        language_param = f'<ac:parameter ac:name="language">{escape(code_language)}</ac:parameter>' if code_language else ""
        chunks.append(
            '<ac:structured-macro ac:name="code">'
            f"{language_param}"
            f"<ac:plain-text-body>{_cdata(chr(10).join(code_lines))}</ac:plain-text-body>"
            "</ac:structured-macro>"
        )
        code_lines.clear()

    for raw_line in lines:
        line = raw_line.rstrip()
        fence = re.match(r"^```([A-Za-z0-9_-]+)?\s*$", line)
        if fence:
            if in_code:
                flush_code()
                in_code = False
                code_language = ""
            else:
                _flush_list(list_items, list_ordered, chunks)
                flush_table()
                in_code = True
                code_language = fence.group(1) or ""
            continue

        if in_code:
            code_lines.append(raw_line)
            continue

        if not line.strip():
            _flush_list(list_items, list_ordered, chunks)
            flush_table()
            continue

        table_separator = re.match(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", line)
        if table_separator:
            continue
        if "|" in line and line.strip().startswith("|"):
            _flush_list(list_items, list_ordered, chunks)
            table_rows.append(_split_markdown_table_row(line))
            continue
        flush_table()

        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            _flush_list(list_items, list_ordered, chunks)
            level = len(heading.group(1))
            chunks.append(f"<h{level}>{escape(heading.group(2).strip())}</h{level}>")
            continue

        unordered = re.match(r"^\s*[-*]\s+(.+)$", line)
        if unordered:
            if list_items and list_ordered:
                _flush_list(list_items, list_ordered, chunks)
            list_ordered = False
            list_items.append(unordered.group(1).strip())
            continue

        ordered = re.match(r"^\s*\d+\.\s+(.+)$", line)
        if ordered:
            if list_items and not list_ordered:
                _flush_list(list_items, list_ordered, chunks)
            list_ordered = True
            list_items.append(ordered.group(1).strip())
            continue

        _flush_list(list_items, list_ordered, chunks)
        chunks.append(f"<p>{escape(line.strip())}</p>")

    if in_code:
        flush_code()
    _flush_list(list_items, list_ordered, chunks)
    flush_table()
    return "".join(chunks) or "<p></p>"


def _default_confluence_space_key(project_id: str | None) -> str:
    """Build a short Confluence space key fallback."""
    source = project_id or "ProtoPilot"
    letters = re.sub(r"[^A-Za-z0-9]", "", source).upper()
    return (letters[:10] or "PP")


async def _find_confluence_page(client: httpx.AsyncClient, cloud_id: str, space_id: str, title: str) -> dict:
    page_list = await _atlassian_request(
        client,
        "GET",
        f"{ATLASSIAN_API_BASE}/ex/confluence/{cloud_id}/wiki/api/v2/pages",
        expected_status=200,
        params={"space-id": space_id, "title": title, "limit": 1},
    )
    results = page_list.get("results", [])
    if not results:
        return {"found": False}
    page_id = str(results[0]["id"])
    page_detail = await _atlassian_request(
        client,
        "GET",
        f"{ATLASSIAN_API_BASE}/ex/confluence/{cloud_id}/wiki/api/v2/pages/{page_id}",
        expected_status=200,
    )
    return {
        "found": True,
        "page_id": page_id,
        "title": page_detail["title"],
        "version": page_detail.get("version", {}).get("number", 1),
    }


async def _create_confluence_page(
    client: httpx.AsyncClient,
    cloud_id: str,
    space_id: str,
    title: str,
    body_storage: str,
    parent_page_id: str = "",
) -> dict:
    body: dict[str, Any] = {
        "spaceId": space_id,
        "status": "current",
        "title": title,
        "body": {"representation": "storage", "value": body_storage},
    }
    if parent_page_id:
        body["parentId"] = parent_page_id
    return await _atlassian_request(
        client,
        "POST",
        f"{ATLASSIAN_API_BASE}/ex/confluence/{cloud_id}/wiki/api/v2/pages",
        expected_status=(200, 201),
        json=body,
    )


async def _update_confluence_page(
    client: httpx.AsyncClient,
    cloud_id: str,
    page_id: str,
    title: str,
    body_storage: str,
    current_version: int,
) -> dict:
    return await _atlassian_request(
        client,
        "PUT",
        f"{ATLASSIAN_API_BASE}/ex/confluence/{cloud_id}/wiki/api/v2/pages/{page_id}",
        expected_status=(200, 201),
        json={
            "id": page_id,
            "status": "current",
            "title": title,
            "version": {"number": current_version + 1, "message": "Updated by ProtoPilot"},
            "body": {"representation": "storage", "value": body_storage},
        },
    )


async def _export_pages_to_confluence(
    *,
    atlassian_token: str,
    pages: list[dict[str, Any]],
    confluence_space_key: str | None,
    parent_page_title: str | None,
    project_id: str | None,
) -> dict:
    """Create or update every provided page directly through the Confluence API."""
    log_event("TOOL", "confluence_direct_export_start", {"project_id": project_id, "pages_count": len(pages), "space_key": confluence_space_key})
    async with httpx.AsyncClient(headers=_atlassian_headers(atlassian_token), timeout=60) as client:
        sites = await _atlassian_request(
            client,
            "GET",
            f"{ATLASSIAN_API_BASE}/oauth/token/accessible-resources",
            expected_status=200,
        )
        if not isinstance(sites, list) or not sites:
            raise HTTPException(status_code=400, detail="No accessible Atlassian sites found for this account.")
        site = sites[0]
        cloud_id = site["id"]
        site_url = site.get("url", "")

        spaces_payload = await _atlassian_request(
            client,
            "GET",
            f"{ATLASSIAN_API_BASE}/ex/confluence/{cloud_id}/wiki/api/v2/spaces",
            expected_status=200,
            params={"limit": 250},
        )
        spaces = spaces_payload.get("results", [])
        requested_key = (confluence_space_key or "").strip().upper()
        space = None
        if requested_key:
            space = next((s for s in spaces if str(s.get("key", "")).upper() == requested_key), None)
            if not space:
                raise HTTPException(status_code=400, detail=f"Confluence space '{requested_key}' was not found or is not accessible.")
        elif spaces:
            space = next((s for s in spaces if s.get("type") == "global"), spaces[0])
        else:
            requested_key = _default_confluence_space_key(project_id)
            space = await _atlassian_request(
                client,
                "POST",
                f"{ATLASSIAN_API_BASE}/ex/confluence/{cloud_id}/wiki/api/v2/spaces",
                expected_status=(200, 201),
                json={"key": requested_key, "name": f"{project_id or 'ProtoPilot'} Documentation", "type": "global"},
            )

        space_id = str(space["id"])
        space_key = str(space.get("key") or requested_key or space_id)
        parent_page_id = ""
        if parent_page_title:
            parent = await _find_confluence_page(client, cloud_id, space_id, parent_page_title)
            index_body = "<p>ProtoPilot exported project documents.</p>"
            if parent.get("found"):
                parent_page_id = parent["page_id"]
                await _update_confluence_page(client, cloud_id, parent_page_id, parent_page_title, index_body, int(parent["version"]))
            else:
                created_parent = await _create_confluence_page(client, cloud_id, space_id, parent_page_title, index_body)
                parent_page_id = str(created_parent["id"])

        exported_pages = []
        seen_titles: set[str] = set()
        for index, page in enumerate(pages, start=1):
            title = str(page.get("title") or page.get("filename") or f"ProtoPilot Document {index}").strip()
            if title in seen_titles:
                suffix_source = str(page.get("filename") or page.get("artifact_group") or index).strip()
                suffix = re.sub(r"\.[A-Za-z0-9]+$", "", suffix_source).replace("_", " ").replace("-", " ").title()
                title = f"{title} ({suffix or index})"
            while title in seen_titles:
                title = f"{title} {index}"
            seen_titles.add(title)
            markdown = str(page.get("markdown") or page.get("content") or "")
            if not markdown.strip():
                continue
            body_storage = _markdown_to_confluence_storage(markdown)
            existing = await _find_confluence_page(client, cloud_id, space_id, title)
            if existing.get("found"):
                updated = await _update_confluence_page(client, cloud_id, existing["page_id"], title, body_storage, int(existing["version"]))
                page_id = str(updated["id"])
                action = "updated"
            else:
                created = await _create_confluence_page(client, cloud_id, space_id, title, body_storage, parent_page_id)
                page_id = str(created["id"])
                action = "created"
            url = f"{site_url.rstrip('/')}/wiki/spaces/{space_key}/pages/{page_id}" if site_url else f"/wiki/pages/{page_id}"
            exported_pages.append({"title": title, "page_id": page_id, "url": url, "action": action})
            log_event("TOOL", "confluence_direct_page_done", {"index": index, "pages_count": len(pages), "title": title[:60], "action": action}, status="ok")

    result = {
        "ok": True,
        "space_key": space_key,
        "pages_requested": len(pages),
        "pages_exported": len(exported_pages),
        "pages": exported_pages,
        "reply": f"Exported {len(exported_pages)} of {len(pages)} documents to Confluence.",
    }
    log_event("TOOL", "confluence_direct_export_done", {"project_id": project_id, "space_key": space_key, "pages_exported": len(exported_pages), "pages_requested": len(pages)}, status="ok")
    return result


@router.get("/github/oauth/start", response_model=GitHubOAuthStartResponse)
def start_github_oauth(current_user: dict[str, str] = Depends(get_current_user)):
    """Start GitHub OAuth by storing state and returning the authorization URL."""
    client_id, _client_secret, redirect_uri = _github_oauth_config(current_user["username"])
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

    client_id, client_secret, redirect_uri = _github_oauth_config(username)
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
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:4200")
    return HTMLResponse(f"""<!DOCTYPE html>
<html><body><script>
  if (window.opener) {{
    window.opener.postMessage('github_connected', '{frontend_url}');
    window.close();
  }} else {{
    window.location.href = '{frontend_url}/spec-review?github_connected=1';
  }}
</script></body></html>
""")


@router.delete("/github/oauth/disconnect")
def disconnect_github(current_user: dict[str, str] = Depends(get_current_user)):
    """Remove the stored GitHub OAuth token for the current user."""
    delete_github_connection(current_user["username"])
    log_event("TOOL", "github_oauth_disconnect", {"username": current_user["username"]}, status="ok")
    return {"disconnected": True}


@router.get("/atlassian/oauth/start", response_model=AtlassianOAuthStartResponse)
def start_atlassian_oauth(current_user: dict[str, str] = Depends(get_current_user)):
    """Start Atlassian OAuth by storing state and returning the authorization URL."""
    client_id, _client_secret, redirect_uri = _atlassian_oauth_config(current_user["username"])
    state = uuid.uuid4().hex
    save_atlassian_oauth_state(state, current_user["username"])
    log_event("TOOL", "atlassian_oauth_start", {"username": current_user["username"], "redirect_uri": redirect_uri})

    params = urlencode({
        "audience": "api.atlassian.com",
        "client_id": client_id,
        "scope": ATLASSIAN_OAUTH_SCOPE,
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
        "prompt": "consent",
    })
    return {"authorization_url": f"{ATLASSIAN_AUTHORIZE_URL}?{params}"}


@router.get("/atlassian/oauth/status", response_model=AtlassianConnectionStatus)
def atlassian_oauth_status(current_user: dict[str, str] = Depends(get_current_user)):
    """Return whether the current user has an active Atlassian OAuth connection."""
    connection = get_atlassian_connection(current_user["username"])
    if not connection:
        log_event("TOOL", "atlassian_oauth_status", {"username": current_user["username"], "connected": False}, status="ok")
        return {"connected": False, "atlassian_username": None}
    log_event("TOOL", "atlassian_oauth_status", {"username": current_user["username"], "connected": True, "atlassian_username": connection.get("atlassian_username")}, status="ok")
    return {
        "connected": True,
        "atlassian_username": connection.get("atlassian_username"),
    }


@router.get("/atlassian/oauth/callback")
async def atlassian_oauth_callback(code: str, state: str):
    """Handle Atlassian OAuth callback, exchange code, and save the user connection."""
    username = consume_atlassian_oauth_state(state)
    if not username:
        log_event("ERROR", "atlassian_oauth_callback_invalid_state", {"state_present": bool(state)}, status="fail")
        raise HTTPException(status_code=400, detail="Invalid or expired Atlassian OAuth state.")

    client_id, client_secret, redirect_uri = _atlassian_oauth_config(username)
    log_event("TOOL", "atlassian_oauth_callback_start", {"username": username, "redirect_uri": redirect_uri})
    async with httpx.AsyncClient(timeout=30) as client:
        token_response = await client.post(
            ATLASSIAN_TOKEN_URL,
            headers={"Content-Type": "application/json"},
            json={
                "grant_type": "authorization_code",
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
            log_event("ERROR", "atlassian_oauth_missing_token", {"username": username}, status="fail")
            raise HTTPException(status_code=400, detail="Atlassian OAuth did not return an access token.")

        refresh_token = token_payload.get("refresh_token")

        me_response = await client.get(
            ATLASSIAN_ME_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        atlassian_username: str | None = None
        if me_response.status_code == 200:
            me_data = me_response.json()
            atlassian_username = me_data.get("email") or me_data.get("name") or me_data.get("account_id")

    save_atlassian_connection(username, access_token, refresh_token, atlassian_username)
    log_event("TOOL", "atlassian_oauth_callback_done", {"username": username, "atlassian_username": atlassian_username}, status="ok")
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:4200")
    return HTMLResponse(f"""<!DOCTYPE html>
<html><body><script>
  if (window.opener) {{
    window.opener.postMessage('atlassian_connected', '{frontend_url}');
    window.close();
  }} else {{
    window.location.href = '{frontend_url}/spec-review?atlassian_connected=1';
  }}
</script></body></html>
""")


@router.delete("/atlassian/oauth/disconnect")
def disconnect_atlassian(current_user: dict[str, str] = Depends(get_current_user)):
    """Remove the stored Atlassian OAuth token for the current user."""
    delete_atlassian_connection(current_user["username"])
    log_event("TOOL", "atlassian_oauth_disconnect", {"username": current_user["username"]}, status="ok")
    return {"disconnected": True}


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

        owner = req.owner or resolve_user_preference(current_user["username"], "GITHUB_OWNER")
        repo = req.repo or resolve_user_preference(current_user["username"], "GITHUB_REPO")
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
            base_branch=req.base_branch or os.getenv("GITHUB_BASE_BRANCH", "main") or "main",
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
async def create_jira_tasks(req: JiraCreateTasksRequest, current_user: dict[str, str] = Depends(get_current_user)):
    """Ask the Jira integration agent to design and create an agile backlog from project context."""
    try:
        log_event(
            "TOOL",
            "jira_create_tasks_request",
            {
                "project_id": req.project_id,
                "session_id": req.session_id,
                "jira_project_key": req.jira_project_key or resolve_user_preference(current_user["username"], "JIRA_PROJECT_KEY", "JIRA_PROJECT_KEY"),
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

        atlassian_connection = get_atlassian_connection(current_user["username"])
        if not atlassian_connection:
            log_event("ERROR", "jira_create_tasks_not_connected", {"username": current_user["username"]}, status="fail")
            raise HTTPException(status_code=400, detail="Connect your Atlassian account before creating a Jira plan.")
        atlassian_token = atlassian_connection["access_token"]

        jira_project_key = req.jira_project_key or resolve_user_preference(current_user["username"], "JIRA_PROJECT_KEY", "JIRA_PROJECT_KEY")

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
            "If no suitable Scrum software project/space exists, call create_jira_project to create one; if that fails due to permissions, stop and report the exact required configuration. "
            "Create the hierarchy in this order: Epics, then Stories under each Epic, then Sub-tasks under each Story. "
            "Make the Jira project demo-rich: populate acceptance criteria, labels, priorities, severity, story points, t-shirt size, sprint, due dates, dependencies, QA notes, demo notes, components/releases, and estimates wherever Jira supports those fields. "
            "Use one-week sprints for Stories. Put due dates at sprint boundaries for Stories and within the sprint for Sub-tasks so work appears in calendar views. "
            "Create or use clearly named one-week sprints when the Jira project supports sprint creation. "
            "Do not leave supported fields empty when a sensible value can be inferred from the spec or artifacts. "
            "Apply normal agile planning standards: acceptance criteria on stories, practical priority/severity, t-shirt sizing, story points, one-week sprint slices for stories, and 2-3 day maximum sub-task scopes. "
            "Call get_jira_project_meta to inspect available issue types and fields, then adapt to the target Jira project. "
            "If custom fields are unavailable, preserve the values in structured issue description sections and use the closest supported parent/link field. "
            "After creating issues, review them for missing rich fields and update them when Jira allows it. "
            "Avoid duplicate issues by checking for matching titles before creating anything. "
            "Use this payload:\n"
            f"{_json_prompt_payload(payload)}"
        )

        token = await get_oauth_token(current_user["username"])
        agent = AGENT_FACTORIES["integration"](token, toolsets=("atlassian",), atlassian_token=atlassian_token, username=current_user["username"])
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
async def export_confluence_artifacts(req: ConfluenceExportRequest, current_user: dict[str, str] = Depends(get_current_user)):
    """Export saved artifact markdown files to Confluence pages via Atlassian REST API."""
    try:
        log_event(
            "TOOL",
            "confluence_export_request",
            {
                "project_id": req.project_id,
                "session_id": req.session_id,
                "confluence_space_key": req.confluence_space_key or resolve_user_preference(current_user["username"], "CONFLUENCE_SPACE_KEY", "CONFLUENCE_SPACE_KEY"),
                "has_manual_pages": req.pages is not None,
            },
        )
        if req.pages is not None:
            pages = req.pages
        elif req.project_id:
            pages = build_confluence_pages_from_project(req.project_id)
        else:
            raise HTTPException(status_code=400, detail="Either pages or project_id is required.")

        atlassian_connection = get_atlassian_connection(current_user["username"])
        if not atlassian_connection:
            log_event("ERROR", "confluence_export_not_connected", {"username": current_user["username"]}, status="fail")
            raise HTTPException(status_code=400, detail="Connect your Atlassian account before exporting to Confluence.")
        atlassian_token = atlassian_connection["access_token"]

        confluence_space_key = req.confluence_space_key or resolve_user_preference(current_user["username"], "CONFLUENCE_SPACE_KEY", "CONFLUENCE_SPACE_KEY")
        session_id = _safe_session_id(req.session_id, req.project_id, "confluence-export-artifacts")
        log_event(
            "TOOL",
            "confluence_export_start",
            {
                "project_id": req.project_id,
                "session_id": session_id,
                "confluence_space_key": confluence_space_key,
                "pages_count": len(pages),
            },
        )
        result = await _export_pages_to_confluence(
            atlassian_token=atlassian_token,
            pages=pages,
            confluence_space_key=confluence_space_key,
            parent_page_title=req.parent_page_title or resolve_user_preference(current_user["username"], "CONFLUENCE_PARENT_PAGE_TITLE", "CONFLUENCE_PARENT_PAGE_TITLE"),
            project_id=req.project_id,
        )

        log_event("TOOL", "confluence_export_done", {"project_id": req.project_id, "session_id": session_id, **result}, status="ok")
        return result

    except HTTPException:
        raise
    except ValueError as e:
        log_event("ERROR", "confluence_export_validation_error", {"project_id": req.project_id, "error": str(e)}, status="fail")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log_event("ERROR", "confluence_export_error", {"project_id": req.project_id, "error": str(e)}, status="fail")
        raise HTTPException(status_code=500, detail=str(e))
