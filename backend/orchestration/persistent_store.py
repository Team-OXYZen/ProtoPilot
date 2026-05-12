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
                user_id TEXT NOT NULL,
                req_session_id TEXT NOT NULL,
                project_title TEXT,
                project_description TEXT,
                stage TEXT NOT NULL,
                spec TEXT,
                nontech_artifacts_md TEXT,
                technical_artifacts_md TEXT,
                generated_code_files TEXT,
                artifacts_summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        try:
            conn.execute("ALTER TABLE projects ADD COLUMN artifacts_summary TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                stage TEXT,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_messages_project_id
            ON chat_messages(project_id, id)
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
                user_id,
                req_session_id,
                project_title,
                project_description,
                stage,
                spec,
                nontech_artifacts_md,
                technical_artifacts_md,
                generated_code_files,
                artifacts_summary,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(project_id) DO UPDATE SET
                user_id = excluded.user_id,
                req_session_id = excluded.req_session_id,
                project_title = excluded.project_title,
                project_description = excluded.project_description,
                stage = excluded.stage,
                spec = excluded.spec,
                nontech_artifacts_md = excluded.nontech_artifacts_md,
                technical_artifacts_md = excluded.technical_artifacts_md,
                generated_code_files = excluded.generated_code_files,
                artifacts_summary = excluded.artifacts_summary,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                proj.project_id,
                proj.user_id,
                proj.req_session_id,
                proj.project_title,
                proj.project_description,
                proj.stage.value,
                _to_json(proj.spec),
                _to_json(proj.nontech_artifacts_md),
                _to_json(proj.technical_artifacts_md),
                _to_json(proj.generated_code_files),
                proj.artifacts_summary,
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
                user_id,
                req_session_id,
                project_title,
                project_description,
                stage,
                spec,
                nontech_artifacts_md,
                technical_artifacts_md,
                generated_code_files,
                artifacts_summary
            FROM projects
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()

    if row is None:
        return None

    return ProjectState(
        project_id=row[0],
        user_id=row[1],
        req_session_id=row[2],
        project_title=row[3],
        project_description=row[4],
        stage=Stage(row[5]),
        spec=_from_json(row[6]),
        nontech_artifacts_md=_from_json(row[7]),
        technical_artifacts_md=_from_json(row[8]),
        generated_code_files=_from_json(row[9]),
        artifacts_summary=row[10],
    )


def list_projects() -> list[dict[str, Any]]:
    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT
                project_id,
                user_id,
                req_session_id,
                project_title,
                project_description,
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
            "user_id": row[1],
            "req_session_id": row[2],
            "project_title": row[3],
            "project_description": row[4],
            "stage": row[5],
            "created_at": row[6],
            "updated_at": row[7],
        }
        for row in rows
    ]

def set_project_stage(project_id: str, stage: Stage) -> None:
    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE projects
            SET stage = ?, updated_at = CURRENT_TIMESTAMP
            WHERE project_id = ?
            """,
            (stage.value, project_id),
        )
        conn.commit()


def save_chat_message(
    project_id: str,
    session_id: str,
    role: str,
    content: Any,
    stage: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    init_db()

    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO chat_messages (
                project_id,
                session_id,
                role,
                stage,
                content,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                session_id,
                role,
                stage,
                content,
                json.dumps(metadata, ensure_ascii=False) if metadata else None,
            ),
        )
        conn.commit()


def list_chat_messages(project_id: str) -> list[dict[str, Any]]:
    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                project_id,
                session_id,
                role,
                stage,
                content,
                metadata,
                created_at
            FROM chat_messages
            WHERE project_id = ?
            ORDER BY id ASC
            """,
            (project_id,),
        ).fetchall()

    return [
        {
            "id": row[0],
            "project_id": row[1],
            "session_id": row[2],
            "role": row[3],
            "stage": row[4],
            "content": row[5],
            "metadata": json.loads(row[6]) if row[6] else None,
            "created_at": row[7],
        }
        for row in rows
    ]
