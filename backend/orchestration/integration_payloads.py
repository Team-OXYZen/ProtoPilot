from core.logging_utils import log_event
from orchestration.store import get_project


def _load_project(project_id: str):
    """Load a project or raise a validation error for integration payload creation."""
    if not project_id:
        raise ValueError("project_id is required to build integration payloads.")

    log_event("TOOL", "integration_project_load", {"project_id": project_id})
    proj = get_project(project_id)
    if proj is None:
        log_event("ERROR", "integration_project_missing", {"project_id": project_id}, status="fail")
        raise ValueError(f"Project not found for project_id '{project_id}'.")

    return proj


def _safe_github_path(path: str) -> str:
    """Validate and normalize a generated file path, rejecting unsafe traversals."""
    if not isinstance(path, str) or not path.strip():
        log_event("ERROR", "github_payload_invalid_path", {"path_type": type(path).__name__}, status="fail")
        raise ValueError("Generated code file path must be a non-empty string.")

    safe_path = path.replace("\\", "/").strip()
    if safe_path.startswith("/") or safe_path.startswith("\\") or ".." in safe_path:
        log_event("ERROR", "github_payload_unsafe_path", {"path": path}, status="fail")
        raise ValueError(f"Unsafe generated code file path rejected: {path}")

    return safe_path


def build_github_files_from_project(project_id: str) -> list[dict]:
    """Build sanitized GitHub file payloads from generated Angular and Java files."""
    proj = _load_project(project_id)
    log_event(
        "TOOL",
        "github_payload_build_start",
        {
            "project_id": project_id,
            "angular_files_count": len(proj.angular_code_files or {}),
            "java_files_count": len(proj.java_code_files or {}),
        },
    )
    generated_code_files = {}
    if proj.angular_code_files:
        for path, content in proj.angular_code_files.items():
            generated_code_files[f"frontend/{path}"] = content
    if proj.java_code_files:
        for path, content in proj.java_code_files.items():
            generated_code_files[f"backend/{path}"] = content

    if not generated_code_files:
        log_event("ERROR", "github_payload_no_files", {"project_id": project_id}, status="fail")
        raise ValueError(f"No generated code files found for project_id '{project_id}'.")

    if not isinstance(generated_code_files, dict):
        raise ValueError("Project generated code files must be a dictionary of file paths to file contents.")

    files = []
    for path, content in generated_code_files.items():
        if not isinstance(content, str):
            log_event("ERROR", "github_payload_invalid_content", {"project_id": project_id, "path": path}, status="fail")
            raise ValueError(f"Generated code file content must be a string for path '{path}'.")

        files.append({
            "path": _safe_github_path(path),
            "content": content,
        })

    log_event(
        "TOOL",
        "github_payload_built",
        {
            "project_id": project_id,
            "files_count": len(files),
            "sample_paths": [file["path"] for file in files[:8]],
        },
        status="ok",
    )
    return files


def build_jira_context_from_project(project_id: str) -> dict:
    """Build Jira integration context from saved spec and artifacts without designing the backlog."""
    proj = _load_project(project_id)
    nontech_artifacts = proj.nontech_artifacts_md or {}
    technical_artifacts = proj.technical_artifacts_md or {}
    jira_plan_artifact = (
        nontech_artifacts.get("jira_plan.md")
        or nontech_artifacts.get("Jira Plan.md")
        or nontech_artifacts.get("delivery_plan.md")
        or technical_artifacts.get("jira_plan.md")
    )

    context = {
        "project_id": project_id,
        "project_title": proj.project_title,
        "project_description": proj.project_description,
        "spec": proj.spec or {},
        "jira_plan_artifact": jira_plan_artifact,
        "nontech_artifacts_md": nontech_artifacts,
        "technical_artifacts_md": technical_artifacts,
        "artifacts_summary": proj.artifacts_summary or "",
        "generated_code_file_counts": {
            "angular": len(proj.angular_code_files or {}),
            "java": len(proj.java_code_files or {}),
        },
    }
    log_event(
        "TOOL",
        "jira_context_built",
        {
            "project_id": project_id,
            "has_spec": bool(proj.spec),
            "has_jira_plan_artifact": bool(jira_plan_artifact),
            "nontech_artifacts_count": len(nontech_artifacts),
            "technical_artifacts_count": len(technical_artifacts),
        },
        status="ok",
    )
    return context


def _confluence_page_title(filename: str) -> str:
    """Convert an artifact filename into a clean Confluence page title."""
    stem = filename.rsplit(".", 1)[0]
    known_titles = {
        "PRD": "PRD",
        "api_documentation": "API Documentation",
        "jira_plan": "Jira Plan",
    }
    if stem in known_titles:
        return known_titles[stem]
    return stem.replace("_", " ").replace("-", " ").title()


def build_confluence_pages_from_project(project_id: str) -> list[dict]:
    """Build one Confluence page payload for each saved artifact markdown file."""
    proj = _load_project(project_id)
    artifacts = []
    for artifact_group, artifact_files in (
        ("Product Artifacts", proj.nontech_artifacts_md or {}),
        ("Technical Artifacts", proj.technical_artifacts_md or {}),
    ):
        for filename, content in artifact_files.items():
            if not isinstance(content, str) or not content.strip():
                continue
            title = _confluence_page_title(filename)
            artifacts.append({
                "title": title,
                "filename": filename,
                "artifact_group": artifact_group,
                "markdown": content,
            })

    if not artifacts:
        log_event("ERROR", "confluence_payload_no_artifacts", {"project_id": project_id}, status="fail")
        raise ValueError(f"No artifact markdown files found for project_id '{project_id}'.")

    log_event(
        "TOOL",
        "confluence_payload_built",
        {
            "project_id": project_id,
            "pages_count": len(artifacts),
            "page_titles": [page["title"] for page in artifacts],
        },
        status="ok",
    )
    return artifacts
