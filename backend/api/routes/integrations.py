import json
import os
import uuid

from fastapi import APIRouter, HTTPException
import httpx
from pydantic import BaseModel

from agents.registry import AGENT_FACTORIES
from core.auth import get_oauth_token
from core.runner import run_turn
from orchestration.integration_payloads import (
    build_github_files_from_project,
    build_jira_tasks_from_project,
)

router = APIRouter(prefix="/integrations")
GITHUB_API_BASE = "https://api.github.com"


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


class JiraTask(BaseModel):
    title: str
    description: str
    acceptance_criteria: list[str] = []
    priority: str | None = None


class JiraCreateTasksRequest(BaseModel):
    project_id: str | None = None
    session_id: str | None = None
    jira_project_key: str | None = None
    issue_type: str = "Task"
    tasks: list[JiraTask] | None = None


def _model_to_dict(model: BaseModel) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _safe_session_id(_req_session_id: str | None, project_id: str | None, action: str) -> str:
    raw_session_id = f"integration-{action}-{project_id or uuid.uuid4().hex[:8]}"
    safe_chars = []
    for char in raw_session_id:
        safe_chars.append(char if char.isalnum() or char in "-_" else "-")
    return "".join(safe_chars)


def _json_prompt_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def _github_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    expected_status: int | tuple[int, ...],
    **kwargs,
) -> dict:
    response = await client.request(method, url, **kwargs)
    expected = (expected_status,) if isinstance(expected_status, int) else expected_status
    if response.status_code not in expected:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)
    if response.status_code == 204 or not response.content:
        return {}
    return response.json()


async def _github_ref_exists(client: httpx.AsyncClient, owner: str, repo: str, branch: str) -> bool:
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/ref/heads/{branch}"
    response = await client.get(url)
    if response.status_code == 200:
        return True
    if response.status_code == 404:
        return False
    try:
        detail = response.json()
    except ValueError:
        detail = response.text
    raise HTTPException(status_code=response.status_code, detail=detail)


def _resolve_github_branch(req: GitHubExportRequest) -> str:
    if req.new_branch:
        return req.new_branch
    suffix = uuid.uuid4().hex[:8]
    project_part = req.project_id or "manual"
    return f"protopilot-export-{project_part}-{suffix}"


async def _export_files_to_github(
    *,
    owner: str,
    repo: str,
    base_branch: str,
    new_branch: str,
    commit_message: str,
    pull_request_title: str,
    pull_request_body: str | None,
    files: list[dict],
) -> dict:
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        raise HTTPException(status_code=400, detail="GITHUB_TOKEN is required.")

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
        for file in files:
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

    return {
        "branch": new_branch,
        "commit_sha": commit["sha"],
        "pull_request_url": pull_request.get("html_url"),
        "files_exported": len(files),
    }


@router.post("/github/export")
async def export_github(req: GitHubExportRequest):
    try:
        if req.files is not None:
            files = [_model_to_dict(file) for file in req.files]
        elif req.project_id:
            files = build_github_files_from_project(req.project_id)
        else:
            raise HTTPException(status_code=400, detail="Either files or project_id is required.")

        owner = req.owner or os.getenv("GITHUB_OWNER")
        repo = req.repo or os.getenv("GITHUB_REPO")
        if not owner or not repo:
            raise HTTPException(status_code=400, detail="GitHub owner and repo are required.")

        result = await _export_files_to_github(
            owner=owner,
            repo=repo,
            base_branch=req.base_branch,
            new_branch=_resolve_github_branch(req),
            commit_message=req.commit_message or "Export ProtoPilot generated code",
            pull_request_title=req.pull_request_title or "Export ProtoPilot generated code",
            pull_request_body=req.pull_request_body,
            files=files,
        )

        return {"ok": True, **result}

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print("[GITHUB_EXPORT_ERROR]", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jira/create-tasks")
async def create_jira_tasks(req: JiraCreateTasksRequest):
    try:
        if req.tasks is not None:
            tasks = [_model_to_dict(task) for task in req.tasks]
        elif req.project_id:
            tasks = build_jira_tasks_from_project(req.project_id)
        else:
            raise HTTPException(status_code=400, detail="Either tasks or project_id is required.")

        jira_project_key = req.jira_project_key or os.getenv("JIRA_PROJECT_KEY")
        if not jira_project_key:
            raise HTTPException(status_code=400, detail="Jira project key is required.")

        payload = {
            "jira_project_key": jira_project_key,
            "issue_type": req.issue_type,
            "tasks": tasks,
        }

        prompt = (
            "Create Jira issues for these ProtoPilot tasks.\n\n"
            "You must create one Jira issue per task. "
            "Each issue should include title, description, acceptance criteria, and optional priority. "
            "Use this payload:\n"
            f"{_json_prompt_payload(payload)}"
        )

        token = await get_oauth_token()
        agent = AGENT_FACTORIES["jira_integration"](token)
        reply = await run_turn(
            agent,
            session_id=_safe_session_id(req.session_id, req.project_id, "jira-create-tasks"),
            message=prompt,
        )

        return {"ok": True, "reply": reply}

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print("[JIRA_CREATE_TASKS_ERROR]", str(e))
        raise HTTPException(status_code=500, detail=str(e))
