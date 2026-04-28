from __future__ import annotations

import json
from typing import Any

from orchestration.store import Stage, get_or_create_project
from core.spec_schema import VersionedSpec


def _log_tool_event(tool: str, payload: dict[str, Any]) -> None:
    print(f"[TOOL_CALL] {tool} {json.dumps(payload, ensure_ascii=False)}")


def submit_spec(project_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    proj = get_or_create_project(project_id, req_session_id=project_id)
    before = proj.stage.value

    try:
        versioned_spec = VersionedSpec(data=spec)
    except Exception as e:
        raise ValueError(f"Spec validation failed: {str(e)}")

    proj.spec = versioned_spec.model_dump()

    proj.stage = Stage.ARTIFACTS_NON_TECH

    _log_tool_event(
        "submit_spec",
        {
            "project_id": project_id,
            "stage_before": before,
            "stage_after": proj.stage.value,
            "spec_version": proj.spec.get("version"),
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
    return {
    "project_id": project_id,
    "spec": proj.spec or {},
    "spec_version": (proj.spec or {}).get("version"),
}


def save_nontech_artifacts(project_id: str, artifacts_md: str) -> dict[str, Any]:
    """
    Save non-technical artifacts and wait for product-manager approval.
    """
    proj = get_or_create_project(project_id, req_session_id=project_id)
    before = proj.stage.value
    proj.nontech_artifacts_md = {
    "content": artifacts_md,
    "based_on_spec_version": (proj.spec or {}).get("version"),
}
    proj.stage = Stage.WAIT_APPROVAL
    _log_tool_event(
        "save_nontech_artifacts",
        {
            "project_id": project_id,
            "stage_before": before,
            "stage_after": proj.stage.value,
            "artifacts_len": len(artifacts_md or ""),
        },
    )
    return {"ok": True, "project_id": project_id, "stage": proj.stage.value}


def save_technical_artifacts(project_id: str, artifacts_md: str) -> dict[str, Any]:
    """
    Save technical artifacts and move workflow to CODEGEN.
    """
    proj = get_or_create_project(project_id, req_session_id=project_id)
    before = proj.stage.value
    proj.technical_artifacts_md = {
    "content": artifacts_md,
    "based_on_spec_version": (proj.spec or {}).get("version"),
}
    proj.stage = Stage.CODEGEN
    _log_tool_event(
        "save_technical_artifacts",
        {
            "project_id": project_id,
            "stage_before": before,
            "stage_after": proj.stage.value,
            "artifacts_len": len(artifacts_md or ""),
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
