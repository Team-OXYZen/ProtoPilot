import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from orchestration.store import ProjectState, Stage


DB_PATH = Path(os.getenv("APP_DB_PATH", "./app.db"))


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                req_session_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                spec TEXT,
                nontech_artifacts_md TEXT,
                technical_artifacts_md TEXT,
                generated_code_files TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def _to_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _from_json(value: str | None) -> Any:
    if not value:
        return None
    return json.loads(value)


def save_project(proj: ProjectState) -> None:
    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO projects (
                project_id,
                req_session_id,
                stage,
                spec,
                nontech_artifacts_md,
                technical_artifacts_md,
                generated_code_files,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(project_id) DO UPDATE SET
                req_session_id = excluded.req_session_id,
                stage = excluded.stage,
                spec = excluded.spec,
                nontech_artifacts_md = excluded.nontech_artifacts_md,
                technical_artifacts_md = excluded.technical_artifacts_md,
                generated_code_files = excluded.generated_code_files,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                proj.project_id,
                proj.req_session_id,
                proj.stage.value,
                _to_json(proj.spec),
                _to_json(proj.nontech_artifacts_md),
                _to_json(proj.technical_artifacts_md),
                _to_json(proj.generated_code_files),
            ),
        )
        conn.commit()


def load_project(project_id: str) -> ProjectState | None:
    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT
                project_id,
                req_session_id,
                stage,
                spec,
                nontech_artifacts_md,
                technical_artifacts_md,
                generated_code_files
            FROM projects
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()

    if row is None:
        return None

    return ProjectState(
        project_id=row[0],
        req_session_id=row[1],
        stage=Stage(row[2]),
        spec=_from_json(row[3]),
        nontech_artifacts_md=_from_json(row[4]),
        technical_artifacts_md=_from_json(row[5]),
        generated_code_files=_from_json(row[6]),
    )


def list_projects() -> list[dict[str, Any]]:
    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT
                project_id,
                req_session_id,
                stage,
                created_at,
                updated_at
            FROM projects
            ORDER BY updated_at DESC
            """
        ).fetchall()

    return [
        {
            "project_id": row[0],
            "req_session_id": row[1],
            "stage": row[2],
            "created_at": row[3],
            "updated_at": row[4],
        }
        for row in rows
    ]