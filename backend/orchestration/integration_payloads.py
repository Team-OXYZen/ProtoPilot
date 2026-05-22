from typing import Any

from orchestration.store import get_project


TASK_SOURCE_FIELDS = (
    "features",
    "requirements",
    "functional_requirements",
    "user_stories",
)


def _load_project(project_id: str):
    if not project_id:
        raise ValueError("project_id is required to build integration payloads.")

    proj = get_project(project_id)
    if proj is None:
        raise ValueError(f"Project not found for project_id '{project_id}'.")

    return proj


def _safe_github_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Generated code file path must be a non-empty string.")

    safe_path = path.replace("\\", "/").strip()
    if safe_path.startswith("/") or safe_path.startswith("\\") or ".." in safe_path:
        raise ValueError(f"Unsafe generated code file path rejected: {path}")

    if not safe_path.startswith("generated/"):
        safe_path = f"generated/{safe_path}"

    return safe_path


def build_github_files_from_project(project_id: str) -> list[dict]:
    proj = _load_project(project_id)
    generated_code_files = {}
    if proj.angular_code_files:
        generated_code_files.update(proj.angular_code_files)
    if proj.java_code_files:
        generated_code_files.update(proj.java_code_files)

    if not generated_code_files:
        raise ValueError(f"No generated code files found for project_id '{project_id}'.")

    if not isinstance(generated_code_files, dict):
        raise ValueError("Project generated code files must be a dictionary of file paths to file contents.")

    files = []
    for path, content in generated_code_files.items():
        if not isinstance(content, str):
            raise ValueError(f"Generated code file content must be a string for path '{path}'.")

        files.append({
            "path": _safe_github_path(path),
            "content": content,
        })

    return files


def _normalize_acceptance_criteria(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [value] if value.strip() else []

    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]

    return [str(value)]


def _stringify_task_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _task_from_item(item: Any, source_field: str, index: int) -> dict | None:
    if isinstance(item, str):
        text = item.strip()
        if not text:
            return None
        return {
            "title": text,
            "description": text,
            "acceptance_criteria": [],
        }

    if not isinstance(item, dict):
        text = _stringify_task_value(item)
        if not text:
            return None
        return {
            "title": f"{source_field.replace('_', ' ').title()} {index}",
            "description": text,
            "acceptance_criteria": [],
        }

    title = (
        item.get("title")
        or item.get("summary")
        or item.get("name")
        or item.get("feature")
        or item.get("requirement")
        or item.get("user_story")
        or item.get("story")
        or f"{source_field.replace('_', ' ').title()} {index}"
    )
    description = (
        item.get("description")
        or item.get("details")
        or item.get("body")
        or item.get("text")
        or item.get("value")
        or title
    )
    acceptance_criteria = (
        item.get("acceptance_criteria")
        or item.get("acceptanceCriteria")
        or item.get("criteria")
        or item.get("ac")
    )

    return {
        "title": _stringify_task_value(title),
        "description": _stringify_task_value(description),
        "acceptance_criteria": _normalize_acceptance_criteria(acceptance_criteria),
    }


def _items_from_spec_field(value: Any) -> list[Any]:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        nested_items = []
        for field in TASK_SOURCE_FIELDS:
            nested_items.extend(_items_from_spec_field(value.get(field)))
        if nested_items:
            return nested_items
        return list(value.values())

    return [value]


def _fallback_tasks_from_project(proj) -> list[dict]:
    context = proj.project_description or proj.artifacts_summary or proj.project_title or "Generated ProtoPilot project."
    return [
        {
            "title": "Review product requirements",
            "description": f"Review the available ProtoPilot requirements and artifacts. Context: {context}",
            "acceptance_criteria": [
                "Requirements are reviewed for clarity and completeness.",
                "Open questions or gaps are documented.",
            ],
        },
        {
            "title": "Implement generated prototype",
            "description": "Implement or export the generated prototype code for review.",
            "acceptance_criteria": [
                "Generated prototype files are available for review.",
                "Implementation follows the generated requirements and artifacts.",
            ],
        },
        {
            "title": "QA generated prototype",
            "description": "Validate the generated prototype against the requirements and expected user flows.",
            "acceptance_criteria": [
                "Critical user flows are checked.",
                "Defects and follow-up improvements are documented.",
            ],
        },
    ]


def build_jira_tasks_from_project(project_id: str) -> list[dict]:
    proj = _load_project(project_id)
    spec = proj.spec

    if spec is not None and not isinstance(spec, dict):
        raise ValueError("Project spec must be a dictionary when present.")

    tasks = []
    if spec:
        for field in TASK_SOURCE_FIELDS:
            items = _items_from_spec_field(spec.get(field))
            for index, item in enumerate(items, start=1):
                task = _task_from_item(item, field, index)
                if task:
                    tasks.append(task)

    return tasks or _fallback_tasks_from_project(proj)
