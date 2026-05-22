import json
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.registry import AGENT_FACTORIES
from core.auth import get_oauth_token
from core.runner import run_turn
from orchestration.integration_payloads import (
    build_github_files_from_project,
    build_jira_tasks_from_project,
)

router = APIRouter(prefix="/integrations")


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


def _safe_session_id(req_session_id: str | None, project_id: str | None, action: str) -> str:
    raw_session_id = req_session_id or f"integration-{action}-{project_id or 'manual'}"
    safe_chars = []
    for char in raw_session_id:
        safe_chars.append(char if char.isalnum() or char in "-_" else "-")
    return "".join(safe_chars)


def _json_prompt_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


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

        new_branch = req.new_branch
        if not new_branch:
            new_branch = f"protopilot-export-{req.project_id}" if req.project_id else "protopilot-export"

        payload = {
            "owner": owner,
            "repo": repo,
            "base_branch": req.base_branch,
            "new_branch": new_branch,
            "commit_message": req.commit_message or "Export ProtoPilot generated code",
            "pull_request_title": req.pull_request_title or "Export ProtoPilot generated code",
            "pull_request_body": req.pull_request_body,
            "files": files,
        }

        prompt = (
            "Export these ProtoPilot generated files to GitHub.\n\n"
            "You must:\n"
            "1. Create a new branch from base_branch.\n"
            "2. Create or update the provided files.\n"
            "3. Commit the changes.\n"
            "4. Create a pull request.\n"
            "5. Do not push directly to main.\n"
            "6. Keep files under generated/.\n\n"
            "Do not overwrite existing files unless explicitly requested. "
            "Use this payload:\n"
            f"{_json_prompt_payload(payload)}"
        )

        token = await get_oauth_token()
        agent = AGENT_FACTORIES["integration"](token)
        reply = await run_turn(
            agent,
            session_id=_safe_session_id(req.session_id, req.project_id, "github-export"),
            message=prompt,
        )

        return {"ok": True, "reply": reply}

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
        agent = AGENT_FACTORIES["integration"](token)
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
