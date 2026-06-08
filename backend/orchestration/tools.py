from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from core.logging_utils import log_event
from orchestration.store import persist_project, get_project

logger = logging.getLogger(__name__)
MAX_BUILD_OUTPUT_CHARS = 20000
MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(?P<body>.*?)```", re.IGNORECASE | re.DOTALL)
MERMAID_START_RE = re.compile(
    r"^\s*(graph|flowchart|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|journey|gantt|pie|gitGraph|mindmap|timeline|quadrantChart|requirementDiagram|C4Context|C4Container|C4Component|C4Dynamic|block-beta)\b"
)
UNQUOTED_BRACKET_LABEL_WITH_PARENS_RE = re.compile(r"[\[{][^\]\}\n]*[()][^\]\}\n]*[\]\}]")


def _log_tool_event(tool: str, payload: dict[str, Any]) -> None:
    log_event("TOOL", tool, payload, status="ok")


def _log_tool_error(error_msg: str) -> None:
    tool_name = error_msg.split(" failed", 1)[0]
    log_event("TOOL", tool_name, {"error": error_msg}, status="fail")


def _truncate_output(output: str, limit: int = MAX_BUILD_OUTPUT_CHARS) -> str:
    if len(output) <= limit:
        return output
    return output[-limit:]


def _strip_quoted_text(value: str) -> str:
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', value)


def _validate_mermaid_text(content: str) -> str | None:
    stripped = content.strip()
    if not stripped:
        return "Mermaid content is empty."
    if "```" in stripped:
        return "Raw Mermaid files must not include markdown code fences."

    first_line = next(
        (line.strip() for line in stripped.splitlines() if line.strip() and not line.strip().startswith("%%")),
        "",
    )
    if not MERMAID_START_RE.match(first_line):
        return f"Mermaid content must start with a supported diagram type, found: {first_line[:80]!r}."

    if len(re.findall(r'(?<!\\)"', stripped)) % 2:
        return "Mermaid content has unbalanced double quotes."

    unquoted = _strip_quoted_text(stripped)
    if UNQUOTED_BRACKET_LABEL_WITH_PARENS_RE.search(unquoted):
        return "Mermaid content has parentheses inside an unquoted bracket label."

    pairs = {"(": ")", "[": "]", "{": "}"}
    stack: list[str] = []
    for char in unquoted:
        if char in pairs:
            stack.append(pairs[char])
        elif char in pairs.values():
            if not stack or stack.pop() != char:
                return f"Mermaid content has unbalanced {char!r}."
    if stack:
        return f"Mermaid content has unbalanced {stack[-1]!r}."

    return None


def _validate_mermaid_artifact(filename: str, content: str) -> str | None:
    if filename.lower().endswith(".mmd"):
        return _validate_mermaid_text(content)

    for index, match in enumerate(MERMAID_BLOCK_RE.finditer(content), start=1):
        error = _validate_mermaid_text(match.group("body"))
        if error:
            return f"Mermaid block {index} is invalid: {error}"
    return None


def _validate_technical_artifacts(artifacts_md: dict[str, str]) -> dict[str, str]:
    errors = {
        filename: error
        for filename, content in (artifacts_md or {}).items()
        if (error := _validate_mermaid_artifact(filename, content or ""))
    }
    return errors


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
    """Store project specification.
    
    Args:
        project_id: Project identifier
        spec: Dictionary containing project requirements (name, goals, users, etc.)
        
    Returns:
        dict with ok, project_id, and current stage value
    """
    try:
        proj = get_project(project_id)

        proj.spec = spec
        persist_project(project_id)

        _log_tool_event(
            "submit_spec",
            {
                "project_id": project_id,
                "stage": proj.stage.value,
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
    """Retrieve stored project specification.
    
    Args:
        project_id: Project identifier
        
    Returns:
        dict with project_id and spec (empty dict if not set)
    """
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
    """Store non-technical artifacts (specs, requirements docs).
    
    Args:
        project_id: Project identifier
        artifacts_md: Dict mapping filenames to markdown content
        
    Returns:
        dict with ok, project_id, and current stage
    """
    try:
        proj = get_project(project_id)

        proj.nontech_artifacts_md = artifacts_md
        persist_project(project_id)

        _log_tool_event(
            "save_nontech_artifacts",
            {
                "project_id": project_id,
                "stage": proj.stage.value,
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
    """Store technical artifacts (architecture, design docs).
    
    Args:
        project_id: Project identifier
        artifacts_md: Dict mapping filenames to markdown content
        
    Returns:
        dict with ok, project_id, and current stage
    """
    try:
        validation_errors = _validate_technical_artifacts(artifacts_md)
        if validation_errors:
            error_msg = f"save_technical_artifacts failed Mermaid validation: {validation_errors}"
            _log_tool_error(error_msg)
            return {"ok": False, "error": error_msg, "project_id": project_id, "validation_errors": validation_errors}

        proj = get_project(project_id)

        proj.technical_artifacts_md = artifacts_md
        persist_project(project_id)

        _log_tool_event(
            "save_technical_artifacts",
            {
                "project_id": project_id,
                "stage": proj.stage.value,
                "artifact_files": list(artifacts_md.keys()) if artifacts_md else [],
            },
        )

        return {"ok": True, "project_id": project_id, "stage": proj.stage.value}
    except Exception as e:
        error_msg = f"save_technical_artifacts failed: {str(e)}"
        _log_tool_error(error_msg)
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id}


def save_artifacts_summary(project_id: str, summary: str) -> dict[str, Any]:
    """Store executive summary of all artifacts.
    
    Args:
        project_id: Project identifier
        summary: Text summary of project artifacts
        
    Returns:
        dict with ok and project_id
    """
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
    """Retrieve project artifacts summary.
    
    Args:
        project_id: Project identifier
        
    Returns:
        dict with project_id and artifacts_summary (empty string if not set)
    """
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
    """Retrieve all non-technical artifacts for the project.
    
    Args:
        project_id: Project identifier
        
    Returns:
        dict with project_id and nontech_artifacts_md (file dict)
    """
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
    """Retrieve all technical artifacts for the project.
    
    Args:
        project_id: Project identifier
        
    Returns:
        dict with project_id and technical_artifacts_md (file dict)
    """
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
    """Create or update a non-technical artifact file.
    
    Args:
        project_id: Project identifier
        filename: Target file name
        content: File content
        
    Returns:
        dict with ok, project_id, and filename
    """
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
    """Create or update a technical artifact file.
    
    Args:
        project_id: Project identifier
        filename: Target file name
        content: File content
        
    Returns:
        dict with ok, project_id, and filename
    """
    try:
        validation_error = _validate_mermaid_artifact(filename, content or "")
        if validation_error:
            error_msg = f"patch_technical_artifact failed Mermaid validation for {filename}: {validation_error}"
            _log_tool_error(error_msg)
            return {"ok": False, "error": error_msg, "project_id": project_id, "filename": filename}

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
    """List all Angular source code files in the project.
    
    Args:
        project_id: Project identifier
        
    Returns:
        dict with project_id and angular_code_files (list of filenames)
    """
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
    """Retrieve specific Angular source file content.
    
    Args:
        project_id: Project identifier
        filename: Source file name
        
    Returns:
        dict with project_id, filename, and content (None if not found)
    """
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
    """Create or update an Angular source file.
    
    Args:
        project_id: Project identifier
        filename: Target file name
        new_content: Source code content
        
    Returns:
        dict with ok, project_id, and filename
    """
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
    """Remove an Angular source file from project.
    
    Args:
        project_id: Project identifier
        filename: File to delete
        
    Returns:
        dict with ok, project_id, and filename
    """
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
    """Rename an Angular source file.
    
    Args:
        project_id: Project identifier
        old_filename: Current file name
        new_filename: New file name
        
    Returns:
        dict with ok, project_id, old_filename, and new_filename
    """
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
    """Execute npm install and build for generated Angular project.
    
    Args:
        project_id: Project identifier
        
    Returns:
        dict with ok, exit codes, and error_output. Stages: install, build
    """
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

def run_java_build(project_id: str) -> dict[str, Any]:
    """Execute Maven package for the generated Java Spring Boot project.

    Args:
        project_id: Project identifier

    Returns:
        dict with ok, exit code, phase, and error_output.
    """
    try:
        proj = get_project(project_id)
        if not proj or not proj.java_code_files:
            log_event("BUILD", "java_build_missing_files", {"project_id": project_id}, status="fail")
            return {
                "ok": False,
                "project_id": project_id,
                "error": "No Java code files found for this project.",
            }

        if "pom.xml" not in proj.java_code_files:
            log_event("BUILD", "java_build_missing_pom", {"project_id": project_id}, status="fail")
            return {
                "ok": False,
                "project_id": project_id,
                "error": "pom.xml is missing from the generated Java files.",
            }

        with tempfile.TemporaryDirectory(prefix=f"protopilot-java-{project_id}-") as temp_dir:
            project_root = Path(temp_dir)
            log_event(
                "BUILD",
                "java_build_start",
                {"project_id": project_id, "files_count": len(proj.java_code_files), "workspace": str(project_root)},
            )
            for filename, content in proj.java_code_files.items():
                destination = _safe_project_file_path(project_root, filename)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content or "", encoding="utf-8")

            maven = shutil.which("mvn")
            if not maven:
                log_event("BUILD", "maven_missing", {"project_id": project_id}, status="fail")
                return {
                    "ok": False,
                    "project_id": project_id,
                    "phase": "build",
                    "error": "mvn was not found on PATH.",
                    "error_output": "mvn was not found on PATH.",
                }

            log_event("BUILD", "maven_package_start", {"project_id": project_id})
            build_result = _run_command([maven, "-q", "-DskipTests", "package"], project_root, timeout_seconds=240)
            log_event(
                "BUILD",
                "maven_package_done",
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
                "install": None,
                "build": build_result,
                "error_output": "" if build_result["ok"] else build_result["output"],
            }
    except Exception as e:
        error_msg = f"run_java_build failed: {str(e)}"
        log_event("BUILD", "java_build_error", {"project_id": project_id, "error": error_msg}, status="fail")
        logger.error(error_msg, exc_info=True)
        return {"ok": False, "error": error_msg, "project_id": project_id}

def list_java_code_files(project_id: str) -> dict[str, Any]:
    """List all Java source code files in the project.
    
    Args:
        project_id: Project identifier
        
    Returns:
        dict with project_id and java_code_files (list of filenames)
    """
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
    """Retrieve specific Java source file content.
    
    Args:
        project_id: Project identifier
        filename: Source file name
        
    Returns:
        dict with project_id, filename, and content (None if not found)
    """
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
    """Create or update a Java source file.
    
    Args:
        project_id: Project identifier
        filename: Target file name
        new_content: Source code content
        
    Returns:
        dict with ok, project_id, and filename
    """
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
    """Remove a Java source file from project.
    
    Args:
        project_id: Project identifier
        filename: File to delete
        
    Returns:
        dict with ok, project_id, and filename
    """
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
    """Rename a Java source file.
    
    Args:
        project_id: Project identifier
        old_filename: Current file name
        new_filename: New file name
        
    Returns:
        dict with ok, project_id, old_filename, and new_filename
    """
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
