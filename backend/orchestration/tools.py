from __future__ import annotations

import json
import logging
from typing import Any

from orchestration.store import Stage, get_or_create_project, persist_project

logger = logging.getLogger(__name__)


def _log_tool_event(tool: str, payload: dict[str, Any]) -> None:
    print(f"[TOOL_CALL] {tool}\n {json.dumps(payload, ensure_ascii=False)}")


def submit_spec(project_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        before = proj.stage.value

        proj.spec = spec
        proj.stage = Stage.ARTIFACTS_NON_TECH
        persist_project(project_id)

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
    except Exception as e:
        error_msg = f"submit_spec failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id}


def load_spec(project_id: str) -> dict[str, Any]:
    try:
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
    except Exception as e:
        error_msg = f"load_spec failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "spec": {}}


def save_nontech_artifacts(project_id: str, artifacts_md: dict[str, str]) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        before = proj.stage.value

        proj.nontech_artifacts_md = artifacts_md
        proj.stage = Stage.WAIT_APPROVAL
        persist_project(project_id)

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
    except Exception as e:
        error_msg = f"save_nontech_artifacts failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id}


def save_technical_artifacts(project_id: str, artifacts_md: dict[str, str]) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        before = proj.stage.value

        proj.technical_artifacts_md = artifacts_md
        proj.stage = Stage.CODEGEN
        persist_project(project_id)

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
    except Exception as e:
        error_msg = f"save_technical_artifacts failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id}


def set_project_stage(project_id: str, stage: str) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        before = proj.stage.value

        proj.stage = Stage(stage)
        persist_project(project_id)

        _log_tool_event(
            "set_project_stage",
            {
                "project_id": project_id,
                "stage_before": before,
                "stage_after": proj.stage.value,
            },
        )

        return {"ok": True, "project_id": project_id, "stage": proj.stage.value}
    except Exception as e:
        error_msg = f"set_project_stage failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id}


def save_artifacts_summary(project_id: str, summary: str) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        proj.artifacts_summary = summary
        persist_project(project_id)
        _log_tool_event("save_artifacts_summary", {"project_id": project_id, "summary_length": len(summary)})
        return {"ok": True, "project_id": project_id}
    except Exception as e:
        error_msg = f"save_artifacts_summary failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id}


def load_artifacts_summary(project_id: str) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        _log_tool_event("load_artifacts_summary", {"project_id": project_id, "has_summary": proj.artifacts_summary is not None})
        return {"project_id": project_id, "artifacts_summary": proj.artifacts_summary or ""}
    except Exception as e:
        error_msg = f"load_artifacts_summary failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "artifacts_summary": ""}


def load_nontech_artifacts(project_id: str) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        _log_tool_event("load_nontech_artifacts", {"project_id": project_id})
        return {"project_id": project_id, "nontech_artifacts_md": proj.nontech_artifacts_md or {}}
    except Exception as e:
        error_msg = f"load_nontech_artifacts failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "nontech_artifacts_md": {}}


def load_technical_artifacts(project_id: str) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        _log_tool_event("load_technical_artifacts", {"project_id": project_id})
        return {"project_id": project_id, "technical_artifacts_md": proj.technical_artifacts_md or {}}
    except Exception as e:
        error_msg = f"load_technical_artifacts failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "technical_artifacts_md": {}}


def patch_nontech_artifact(project_id: str, filename: str, content: str) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        if not proj.nontech_artifacts_md:
            proj.nontech_artifacts_md = {}
        proj.nontech_artifacts_md[filename] = content
        persist_project(project_id)
        _log_tool_event("patch_nontech_artifact", {"project_id": project_id, "filename": filename})
        return {"ok": True, "project_id": project_id, "filename": filename}
    except Exception as e:
        error_msg = f"patch_nontech_artifact failed for {filename}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "filename": filename}


def patch_technical_artifact(project_id: str, filename: str, content: str) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        if not proj.technical_artifacts_md:
            proj.technical_artifacts_md = {}
        proj.technical_artifacts_md[filename] = content
        persist_project(project_id)
        _log_tool_event("patch_technical_artifact", {"project_id": project_id, "filename": filename})
        return {"ok": True, "project_id": project_id, "filename": filename}
    except Exception as e:
        error_msg = f"patch_technical_artifact failed for {filename}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "filename": filename}


def load_artifacts(project_id: str) -> dict[str, Any]:
    try:
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
    except Exception as e:
        error_msg = f"load_artifacts failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "nontech_artifacts_md": {}, "technical_artifacts_md": {}}


# ── Angular code file tools ────────────────────────────────────────────────

def list_angular_code_files(project_id: str) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        file_list = list(proj.angular_code_files.keys()) if proj.angular_code_files else []
        _log_tool_event("list_angular_code_files", {"project_id": project_id, "files_count": len(file_list), "files": file_list})
        return {"project_id": project_id, "angular_code_files": file_list}
    except Exception as e:
        error_msg = f"list_angular_code_files failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "angular_code_files": []}


def load_angular_code_file(project_id: str, filename: str) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        file_content = proj.angular_code_files.get(filename) if proj.angular_code_files else None
        _log_tool_event("load_angular_code_file", {"project_id": project_id, "filename": filename, "file_exists": file_content is not None})
        return {"project_id": project_id, "filename": filename, "content": file_content}
    except Exception as e:
        error_msg = f"load_angular_code_file failed for {filename}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "filename": filename, "content": None}


def patch_angular_code_file(project_id: str, filename: str, new_content: str) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        if not proj.angular_code_files:
            proj.angular_code_files = {}
        before_content = proj.angular_code_files.get(filename)
        proj.angular_code_files[filename] = new_content
        persist_project(project_id)
        _log_tool_event("patch_angular_code_file", {"project_id": project_id, "filename": filename, "file_exists_before": before_content is not None})
        return {"ok": True, "project_id": project_id, "filename": filename}
    except Exception as e:
        error_msg = f"patch_angular_code_file failed for {filename}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "filename": filename}


def delete_angular_code_file(project_id: str, filename: str) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        if not proj.angular_code_files or filename not in proj.angular_code_files:
            return {"ok": False, "error": "File not found", "project_id": project_id, "filename": filename}
        del proj.angular_code_files[filename]
        persist_project(project_id)
        _log_tool_event("delete_angular_code_file", {"project_id": project_id, "filename": filename})
        return {"ok": True, "project_id": project_id, "filename": filename}
    except Exception as e:
        error_msg = f"delete_angular_code_file failed for {filename}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "filename": filename}


def rename_angular_code_file(project_id: str, old_filename: str, new_filename: str) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        if not proj.angular_code_files or old_filename not in proj.angular_code_files:
            return {"ok": False, "error": "File not found", "project_id": project_id, "filename": old_filename}
        proj.angular_code_files[new_filename] = proj.angular_code_files.pop(old_filename)
        persist_project(project_id)
        _log_tool_event("rename_angular_code_file", {"project_id": project_id, "old_filename": old_filename, "new_filename": new_filename})
        return {"ok": True, "project_id": project_id, "old_filename": old_filename, "new_filename": new_filename}
    except Exception as e:
        error_msg = f"rename_angular_code_file failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "old_filename": old_filename, "new_filename": new_filename}


# ── Java code file tools ───────────────────────────────────────────────────

def list_java_code_files(project_id: str) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        file_list = list(proj.java_code_files.keys()) if proj.java_code_files else []
        _log_tool_event("list_java_code_files", {"project_id": project_id, "files_count": len(file_list), "files": file_list})
        return {"project_id": project_id, "java_code_files": file_list}
    except Exception as e:
        error_msg = f"list_java_code_files failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "java_code_files": []}


def load_java_code_file(project_id: str, filename: str) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        file_content = proj.java_code_files.get(filename) if proj.java_code_files else None
        _log_tool_event("load_java_code_file", {"project_id": project_id, "filename": filename, "file_exists": file_content is not None})
        return {"project_id": project_id, "filename": filename, "content": file_content}
    except Exception as e:
        error_msg = f"load_java_code_file failed for {filename}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "filename": filename, "content": None}


def patch_java_code_file(project_id: str, filename: str, new_content: str) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        if not proj.java_code_files:
            proj.java_code_files = {}
        before_content = proj.java_code_files.get(filename)
        proj.java_code_files[filename] = new_content
        persist_project(project_id)
        _log_tool_event("patch_java_code_file", {"project_id": project_id, "filename": filename, "file_exists_before": before_content is not None})
        return {"ok": True, "project_id": project_id, "filename": filename}
    except Exception as e:
        error_msg = f"patch_java_code_file failed for {filename}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "filename": filename}


def delete_java_code_file(project_id: str, filename: str) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        if not proj.java_code_files or filename not in proj.java_code_files:
            return {"ok": False, "error": "File not found", "project_id": project_id, "filename": filename}
        del proj.java_code_files[filename]
        persist_project(project_id)
        _log_tool_event("delete_java_code_file", {"project_id": project_id, "filename": filename})
        return {"ok": True, "project_id": project_id, "filename": filename}
    except Exception as e:
        error_msg = f"delete_java_code_file failed for {filename}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "filename": filename}


def rename_java_code_file(project_id: str, old_filename: str, new_filename: str) -> dict[str, Any]:
    try:
        proj = get_or_create_project(project_id, req_session_id=project_id)
        if not proj.java_code_files or old_filename not in proj.java_code_files:
            return {"ok": False, "error": "File not found", "project_id": project_id, "filename": old_filename}
        proj.java_code_files[new_filename] = proj.java_code_files.pop(old_filename)
        persist_project(project_id)
        _log_tool_event("rename_java_code_file", {"project_id": project_id, "old_filename": old_filename, "new_filename": new_filename})
        return {"ok": True, "project_id": project_id, "old_filename": old_filename, "new_filename": new_filename}
    except Exception as e:
        error_msg = f"rename_java_code_file failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "old_filename": old_filename, "new_filename": new_filename}
