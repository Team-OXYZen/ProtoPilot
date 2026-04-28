from __future__ import annotations

import json
from typing import Any

from orchestration.store import Stage, get_or_create_project


def _log_tool_event(tool: str, payload: dict[str, Any]) -> None:
    print(f"[TOOL_CALL] {tool} {json.dumps(payload, ensure_ascii=False)}")


def submit_spec(project_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    """
    Save finalized requirements spec and move project to non-technical artifacts.
    """
    proj = get_or_create_project(project_id, req_session_id=project_id)
    before = proj.stage.value
    proj.spec = spec
    proj.stage = Stage.ARTIFACTS_NON_TECH
    _log_tool_event(
        "submit_spec",
        {
            "project_id": project_id,
            "stage_before": before,
            "stage_after": proj.stage.value,
            "spec_keys": list(spec.keys()),
        },
    )
    return {"ok": True, "project_id": project_id, "stage": proj.stage.value}


def load_spec(project_id: str) -> dict[str, Any]:
    """
    Load requirements spec for artifact generation.
    """
    proj = get_or_create_project(project_id, req_session_id=project_id)
    _log_tool_event(
        "load_spec",
        {
            "project_id": project_id,
            "stage": proj.stage.value,
            "has_spec": proj.spec is not None,
        },
    )
    return {"project_id": project_id, "spec": proj.spec or {}}


def save_nontech_artifacts(project_id: str, artifacts_md: dict[str, str]) -> dict[str, Any]:
    """
    Save non-technical artifacts (as dictionary of filename: markdown_content) and wait for product-manager approval.
    """
    proj = get_or_create_project(project_id, req_session_id=project_id)
    before = proj.stage.value
    proj.nontech_artifacts_md = artifacts_md
    proj.stage = Stage.WAIT_APPROVAL
    _log_tool_event(
        "save_nontech_artifacts",
        {
            "project_id": project_id,
            "stage_before": before,
            "stage_after": proj.stage.value,
            "artifact_files": list(artifacts_md.keys()) if artifacts_md else [],
        },
    )
    return {"ok": True, "project_id": project_id, "stage": proj.stage.value}


def save_technical_artifacts(project_id: str, artifacts_md: dict[str, str]) -> dict[str, Any]:
    """
    Save technical artifacts (as dictionary of filename: markdown_content) and move workflow to CODEGEN.
    """
    proj = get_or_create_project(project_id, req_session_id=project_id)
    before = proj.stage.value
    proj.technical_artifacts_md = artifacts_md
    proj.stage = Stage.CODEGEN
    _log_tool_event(
        "save_technical_artifacts",
        {
            "project_id": project_id,
            "stage_before": before,
            "stage_after": proj.stage.value,
            "artifact_files": list(artifacts_md.keys()) if artifacts_md else [],
        },
    )
    return {"ok": True, "project_id": project_id, "stage": proj.stage.value}


def set_project_stage(project_id: str, stage: str) -> dict[str, Any]:
    """
    Force-set project stage. Intended for explicit orchestration transitions.
    """
    proj = get_or_create_project(project_id, req_session_id=project_id)
    before = proj.stage.value
    proj.stage = Stage(stage)
    _log_tool_event(
        "set_project_stage",
        {
            "project_id": project_id,
            "stage_before": before,
            "stage_after": proj.stage.value,
        },
    )
    return {"ok": True, "project_id": project_id, "stage": proj.stage.value}


def load_artifacts(project_id: str) -> dict[str, Any]:
    """
    Load both non-technical and technical artifacts for code generation.
    """
    proj = get_or_create_project(project_id, req_session_id=project_id)
    _log_tool_event(
        "load_artifacts",
        {
            "project_id": project_id,
            "stage": proj.stage.value,
            "has_nontech": proj.nontech_artifacts_md is not None,
            "has_technical": proj.technical_artifacts_md is not None,
        },
    )
    return {
        "project_id": project_id,
        "nontech_artifacts_md": proj.nontech_artifacts_md or {},
        "technical_artifacts_md": proj.technical_artifacts_md or {},
    }


def save_generated_code(project_id: str, files_json: dict[str, str]) -> dict[str, Any]:
    """
    Save generated code files (as dictionary of filepath: file_content) and move to QA stage.
    """
    proj = get_or_create_project(project_id, req_session_id=project_id)
    before = proj.stage.value
    proj.generated_code_files = files_json
    proj.stage = Stage.QA
    _log_tool_event(
        "save_generated_code",
        {
            "project_id": project_id,
            "stage_before": before,
            "stage_after": proj.stage.value,
            "generated_files": list(files_json.keys()) if files_json else [],
        },
    )
    return {"ok": True, "project_id": project_id, "stage": proj.stage.value, "files_count": len(files_json or {})}

def load_generated_code(project_id: str) -> dict[str, Any]:
    """
    Load generated code files for QA review.
    """
    proj = get_or_create_project(project_id, req_session_id=project_id)
    _log_tool_event(
        "load_generated_code",
        {
            "project_id": project_id,
            "stage": proj.stage.value,
            "has_generated_code": proj.generated_code_files is not None,
            "generated_files": list(proj.generated_code_files.keys()) if proj.generated_code_files else [],
        },
    )
    return {
        "project_id": project_id,
        "generated_code_files": proj.generated_code_files or {},
    }