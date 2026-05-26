from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from core.logging_utils import log_event
from orchestration.store import Stage, get_or_create_project, persist_project, get_project

logger = logging.getLogger(__name__)
MAX_BUILD_OUTPUT_CHARS = 20000


def _log_tool_event(tool: str, payload: dict[str, Any]) -> None:
    log_event("TOOL", tool, payload, status="ok")


def _log_tool_error(error_msg: str) -> None:
    tool_name = error_msg.split(" failed", 1)[0]
    log_event("TOOL", tool_name, {"error": error_msg}, status="fail")


def _truncate_output(output: str, limit: int = MAX_BUILD_OUTPUT_CHARS) -> str:
    if len(output) <= limit:
        return output
    return output[-limit:]


def _safe_project_file_path(root: Path, filename: str) -> Path:
    file_path = Path(filename)
    if file_path.is_absolute() or ".." in file_path.parts:
        raise ValueError(f"Unsafe generated file path: {filename}")
    resolved = (root / file_path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"Unsafe generated file path: {filename}")
    return resolved


def _run_command(command: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            env={**os.environ, "CI": "true"},
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        return {
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "output": _truncate_output(output),
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "exit_code": 127,
            "output": f"Command not found: {command[0]}",
        }
    except subprocess.TimeoutExpired as exc:
        output = ((exc.stdout or "") if isinstance(exc.stdout, str) else "") + ((exc.stderr or "") if isinstance(exc.stderr, str) else "")
        return {
            "ok": False,
            "exit_code": 124,
            "output": _truncate_output(f"Command timed out after {timeout_seconds} seconds.\n{output}"),
        }


def submit_spec(project_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
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
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id}


def load_spec(project_id: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)

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
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "spec": {}}


def save_nontech_artifacts(project_id: str, artifacts_md: dict[str, str]) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
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
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id}


def save_technical_artifacts(project_id: str, artifacts_md: dict[str, str]) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
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
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id}


def set_project_stage(project_id: str, stage: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
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
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id}


def save_artifacts_summary(project_id: str, summary: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
        proj.artifacts_summary = summary
        persist_project(project_id)
        _log_tool_event("save_artifacts_summary", {"project_id": project_id, "summary_length": len(summary)})
        return {"ok": True, "project_id": project_id}
    except Exception as e:
        error_msg = f"save_artifacts_summary failed: {str(e)}"
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id}


def load_artifacts_summary(project_id: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
        _log_tool_event("load_artifacts_summary", {"project_id": project_id, "has_summary": proj.artifacts_summary is not None})
        return {"project_id": project_id, "artifacts_summary": proj.artifacts_summary or ""}
    except Exception as e:
        error_msg = f"load_artifacts_summary failed: {str(e)}"
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "artifacts_summary": ""}


def load_nontech_artifacts(project_id: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
        _log_tool_event("load_nontech_artifacts", {"project_id": project_id})
        return {"project_id": project_id, "nontech_artifacts_md": proj.nontech_artifacts_md or {}}
    except Exception as e:
        error_msg = f"load_nontech_artifacts failed: {str(e)}"
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "nontech_artifacts_md": {}}


def load_technical_artifacts(project_id: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
        _log_tool_event("load_technical_artifacts", {"project_id": project_id})
        return {"project_id": project_id, "technical_artifacts_md": proj.technical_artifacts_md or {}}
    except Exception as e:
        error_msg = f"load_technical_artifacts failed: {str(e)}"
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "technical_artifacts_md": {}}


def patch_nontech_artifact(project_id: str, filename: str, content: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
        if not proj.nontech_artifacts_md:
            proj.nontech_artifacts_md = {}
        proj.nontech_artifacts_md[filename] = content
        persist_project(project_id)
        _log_tool_event("patch_nontech_artifact", {"project_id": project_id, "filename": filename})
        return {"ok": True, "project_id": project_id, "filename": filename}
    except Exception as e:
        error_msg = f"patch_nontech_artifact failed for {filename}: {str(e)}"
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "filename": filename}


def patch_technical_artifact(project_id: str, filename: str, content: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
        if not proj.technical_artifacts_md:
            proj.technical_artifacts_md = {}
        proj.technical_artifacts_md[filename] = content
        persist_project(project_id)
        _log_tool_event("patch_technical_artifact", {"project_id": project_id, "filename": filename})
        return {"ok": True, "project_id": project_id, "filename": filename}
    except Exception as e:
        error_msg = f"patch_technical_artifact failed for {filename}: {str(e)}"
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "filename": filename}


def load_artifacts(project_id: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)

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
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "nontech_artifacts_md": {}, "technical_artifacts_md": {}}


# ── Angular code file tools ────────────────────────────────────────────────

def list_angular_code_files(project_id: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
        file_list = list(proj.angular_code_files.keys()) if proj.angular_code_files else []
        _log_tool_event("list_angular_code_files", {"project_id": project_id, "files_count": len(file_list), "files": file_list})
        return {"project_id": project_id, "angular_code_files": file_list}
    except Exception as e:
        error_msg = f"list_angular_code_files failed: {str(e)}"
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "angular_code_files": []}


def load_angular_code_file(project_id: str, filename: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
        file_content = proj.angular_code_files.get(filename) if proj.angular_code_files else None
        _log_tool_event("load_angular_code_file", {"project_id": project_id, "filename": filename, "file_exists": file_content is not None})
        return {"project_id": project_id, "filename": filename, "content": file_content}
    except Exception as e:
        error_msg = f"load_angular_code_file failed for {filename}: {str(e)}"
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "filename": filename, "content": None}


def patch_angular_code_file(project_id: str, filename: str, new_content: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
        if not proj.angular_code_files:
            proj.angular_code_files = {}
        before_content = proj.angular_code_files.get(filename)
        proj.angular_code_files[filename] = new_content
        persist_project(project_id)
        _log_tool_event("patch_angular_code_file", {"project_id": project_id, "filename": filename, "file_exists_before": before_content is not None})
        return {"ok": True, "project_id": project_id, "filename": filename}
    except Exception as e:
        error_msg = f"patch_angular_code_file failed for {filename}: {str(e)}"
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "filename": filename}


def delete_angular_code_file(project_id: str, filename: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
        if not proj.angular_code_files or filename not in proj.angular_code_files:
            log_event("TOOL", "delete_angular_code_file", {"project_id": project_id, "filename": filename, "error": "File not found"}, status="fail")
            return {"ok": False, "error": "File not found", "project_id": project_id, "filename": filename}
        del proj.angular_code_files[filename]
        persist_project(project_id)
        _log_tool_event("delete_angular_code_file", {"project_id": project_id, "filename": filename})
        return {"ok": True, "project_id": project_id, "filename": filename}
    except Exception as e:
        error_msg = f"delete_angular_code_file failed for {filename}: {str(e)}"
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "filename": filename}


def rename_angular_code_file(project_id: str, old_filename: str, new_filename: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
        if not proj.angular_code_files or old_filename not in proj.angular_code_files:
            log_event("TOOL", "rename_angular_code_file", {"project_id": project_id, "old_filename": old_filename, "new_filename": new_filename, "error": "File not found"}, status="fail")
            return {"ok": False, "error": "File not found", "project_id": project_id, "filename": old_filename}
        proj.angular_code_files[new_filename] = proj.angular_code_files.pop(old_filename)
        persist_project(project_id)
        _log_tool_event("rename_angular_code_file", {"project_id": project_id, "old_filename": old_filename, "new_filename": new_filename})
        return {"ok": True, "project_id": project_id, "old_filename": old_filename, "new_filename": new_filename}
    except Exception as e:
        error_msg = f"rename_angular_code_file failed: {str(e)}"
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "old_filename": old_filename, "new_filename": new_filename}


def run_angular_build(project_id: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
        if not proj or not proj.angular_code_files:
            log_event("BUILD", "angular_build_missing_files", {"project_id": project_id}, status="fail")
            return {
                "ok": False,
                "project_id": project_id,
                "error": "No Angular code files found for this project.",
            }

        if "package.json" not in proj.angular_code_files:
            log_event("BUILD", "angular_build_missing_package", {"project_id": project_id}, status="fail")
            return {
                "ok": False,
                "project_id": project_id,
                "error": "package.json is missing from the generated Angular files.",
            }

        with tempfile.TemporaryDirectory(prefix=f"protopilot-angular-{project_id}-") as temp_dir:
            project_root = Path(temp_dir)
            log_event(
                "BUILD",
                "angular_build_start",
                {"project_id": project_id, "files_count": len(proj.angular_code_files), "workspace": str(project_root)},
            )
            for filename, content in proj.angular_code_files.items():
                destination = _safe_project_file_path(project_root, filename)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content or "", encoding="utf-8")

            package_manager = shutil.which("npm")
            if not package_manager:
                log_event("BUILD", "npm_missing", {"project_id": project_id}, status="fail")
                return {
                    "ok": False,
                    "project_id": project_id,
                    "error": "npm was not found on PATH.",
                }

            log_event("BUILD", "npm_install_start", {"project_id": project_id})
            install_result = _run_command([package_manager, "install", "--no-audit", "--no-fund"], project_root, timeout_seconds=180)
            if not install_result["ok"]:
                log_event(
                    "BUILD",
                    "run_angular_build",
                    {
                        "project_id": project_id,
                        "phase": "install",
                        "exit_code": install_result["exit_code"],
                        "output": install_result["output"],
                    },
                    status="fail",
                )
                return {
                    "ok": False,
                    "project_id": project_id,
                    "phase": "install",
                    "install": install_result,
                    "build": None,
                    "error_output": install_result["output"],
                }

            log_event("BUILD", "npm_install_done", {"project_id": project_id, "exit_code": install_result["exit_code"]}, status="ok")
            log_event("BUILD", "npm_build_start", {"project_id": project_id})
            build_result = _run_command([package_manager, "run", "build"], project_root, timeout_seconds=180)
            log_event(
                "BUILD",
                "npm_build_done",
                {
                    "project_id": project_id,
                    "phase": "build",
                    "exit_code": build_result["exit_code"],
                    "output": "" if build_result["ok"] else build_result["output"],
                },
                status="ok" if build_result["ok"] else "fail",
            )
            return {
                "ok": build_result["ok"],
                "project_id": project_id,
                "phase": "build",
                "install": install_result,
                "build": build_result,
                "error_output": "" if build_result["ok"] else build_result["output"],
            }
    except Exception as e:
        error_msg = f"run_angular_build failed: {str(e)}"
        log_event("BUILD", "angular_build_error", {"project_id": project_id, "error": error_msg}, status="fail")
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id}


# ── Java code file tools ───────────────────────────────────────────────────

def list_java_code_files(project_id: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
        file_list = list(proj.java_code_files.keys()) if proj.java_code_files else []
        _log_tool_event("list_java_code_files", {"project_id": project_id, "files_count": len(file_list), "files": file_list})
        return {"project_id": project_id, "java_code_files": file_list}
    except Exception as e:
        error_msg = f"list_java_code_files failed: {str(e)}"
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "java_code_files": []}


def load_java_code_file(project_id: str, filename: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
        file_content = proj.java_code_files.get(filename) if proj.java_code_files else None
        _log_tool_event("load_java_code_file", {"project_id": project_id, "filename": filename, "file_exists": file_content is not None})
        return {"project_id": project_id, "filename": filename, "content": file_content}
    except Exception as e:
        error_msg = f"load_java_code_file failed for {filename}: {str(e)}"
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "filename": filename, "content": None}


def patch_java_code_file(project_id: str, filename: str, new_content: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
        if not proj.java_code_files:
            proj.java_code_files = {}
        before_content = proj.java_code_files.get(filename)
        proj.java_code_files[filename] = new_content
        persist_project(project_id)
        _log_tool_event("patch_java_code_file", {"project_id": project_id, "filename": filename, "file_exists_before": before_content is not None})
        return {"ok": True, "project_id": project_id, "filename": filename}
    except Exception as e:
        error_msg = f"patch_java_code_file failed for {filename}: {str(e)}"
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "filename": filename}


def delete_java_code_file(project_id: str, filename: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
        if not proj.java_code_files or filename not in proj.java_code_files:
            log_event("TOOL", "delete_java_code_file", {"project_id": project_id, "filename": filename, "error": "File not found"}, status="fail")
            return {"ok": False, "error": "File not found", "project_id": project_id, "filename": filename}
        del proj.java_code_files[filename]
        persist_project(project_id)
        _log_tool_event("delete_java_code_file", {"project_id": project_id, "filename": filename})
        return {"ok": True, "project_id": project_id, "filename": filename}
    except Exception as e:
        error_msg = f"delete_java_code_file failed for {filename}: {str(e)}"
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "filename": filename}


def rename_java_code_file(project_id: str, old_filename: str, new_filename: str) -> dict[str, Any]:
    try:
        proj = get_project(project_id)
        if not proj.java_code_files or old_filename not in proj.java_code_files:
            log_event("TOOL", "rename_java_code_file", {"project_id": project_id, "old_filename": old_filename, "new_filename": new_filename, "error": "File not found"}, status="fail")
            return {"ok": False, "error": "File not found", "project_id": project_id, "filename": old_filename}
        proj.java_code_files[new_filename] = proj.java_code_files.pop(old_filename)
        persist_project(project_id)
        _log_tool_event("rename_java_code_file", {"project_id": project_id, "old_filename": old_filename, "new_filename": new_filename})
        return {"ok": True, "project_id": project_id, "old_filename": old_filename, "new_filename": new_filename}
    except Exception as e:
        error_msg = f"rename_java_code_file failed: {str(e)}"
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id, "old_filename": old_filename, "new_filename": new_filename}
