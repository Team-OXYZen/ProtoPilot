import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["APP_DB_PATH"] = str(Path(_TEMP_DIR.name) / "app.db")
os.environ["USERS_DB_PATH"] = str(Path(_TEMP_DIR.name) / "users.db")
os.environ["HOME"] = _TEMP_DIR.name

from api.server import app
from core.auth import verify_password
from core.user_store import get_password_hash
from orchestration.persistent_store import save_chat_message
from orchestration.store import _PROJECTS


def tearDownModule() -> None:
    _TEMP_DIR.cleanup()


class ProjectAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        _PROJECTS.clear()
        Path(os.environ["APP_DB_PATH"]).unlink(missing_ok=True)
        Path(os.environ["USERS_DB_PATH"]).unlink(missing_ok=True)
        self.client = TestClient(app)

    def _signup(self, username: str) -> str:
        response = self.client.post(
            "/auth/signup",
            json={"username": username, "password": "pass123"},
        )

        self.assertEqual(response.status_code, 201)
        return response.json()["access_token"]

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _create_project(self, token: str, username: str, project_id: str) -> None:
        response = self.client.post(
            "/projects",
            headers=self._auth_headers(token),
            json={
                "user_id": username,
                "project_id": project_id,
                "session_id": f"{project_id}-session",
                "project_title": f"{username} project",
                "project_description": "private",
            },
        )

        self.assertEqual(response.status_code, 200)

    def test_project_reads_are_limited_to_authenticated_owner(self) -> None:
        alice_token = self._signup("alice")
        bob_token = self._signup("bob")

        self._create_project(alice_token, "alice", "alice-project")
        self._create_project(bob_token, "bob", "bob-project")
        save_chat_message("alice-project", "alice-session", "user", "private message")

        alice_projects = self.client.get(
            "/projects",
            headers=self._auth_headers(alice_token),
            params={"user_id": "alice"},
        )
        bob_project_detail = self.client.get(
            "/projects/alice-project",
            headers=self._auth_headers(bob_token),
            params={"user_id": "bob"},
        )
        bob_project_messages = self.client.get(
            "/projects/alice-project/messages",
            headers=self._auth_headers(bob_token),
            params={"user_id": "bob"},
        )
        mismatched_user_filter = self.client.get(
            "/projects",
            headers=self._auth_headers(alice_token),
            params={"user_id": "bob"},
        )

        self.assertEqual(alice_projects.status_code, 200)
        self.assertEqual(
            [project["project_id"] for project in alice_projects.json()["projects"]],
            ["alice-project"],
        )
        self.assertEqual(bob_project_detail.status_code, 404)
        self.assertEqual(bob_project_messages.status_code, 404)
        self.assertEqual(mismatched_user_filter.status_code, 403)

    def test_existing_project_id_cannot_be_taken_over(self) -> None:
        alice_token = self._signup("alice")
        bob_token = self._signup("bob")

        self._create_project(alice_token, "alice", "shared-project-id")

        takeover_attempt = self.client.post(
            "/projects",
            headers=self._auth_headers(bob_token),
            json={
                "user_id": "bob",
                "project_id": "shared-project-id",
                "session_id": "bob-session",
                "project_title": "Bob project",
            },
        )

        self.assertEqual(takeover_attempt.status_code, 404)

    def test_signup_persists_users_in_dedicated_database(self) -> None:
        self._signup("alice")

        password_hash = get_password_hash("alice")
        login_response = self.client.post(
            "/auth/login",
            json={"username": "alice", "password": "pass123"},
        )

        self.assertTrue(Path(os.environ["USERS_DB_PATH"]).exists())
        self.assertIsNotNone(password_hash)
        self.assertTrue(verify_password("pass123", password_hash or ""))
        self.assertEqual(login_response.status_code, 200)

    def test_user_preferences_are_persisted_and_reject_secret_like_keys(self) -> None:
        alice_token = self._signup("alice")
        headers = self._auth_headers(alice_token)

        save_response = self.client.put(
            "/preferences",
            headers=headers,
            json={
                "preferences": {
                    "jira_project_key": "PROTO",
                    "CONFLUENCE_SPACE_KEY": "DOCS",
                    "GITHUB_OWNER": "team",
                    "GITHUB_REPO": "demo",
                }
            },
        )
        read_response = self.client.get("/preferences", headers=headers)
        secret_response = self.client.put(
            "/preferences",
            headers=headers,
            json={"preferences": {"LITELLM_API_KEY": "do-not-store"}},
        )

        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(read_response.json()["preferences"]["JIRA_PROJECT_KEY"], "PROTO")
        self.assertEqual(read_response.json()["preferences"]["CONFLUENCE_SPACE_KEY"], "DOCS")
        self.assertEqual(secret_response.status_code, 400)
