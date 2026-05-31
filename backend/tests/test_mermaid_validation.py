import unittest
from unittest.mock import patch

from orchestration.store import ProjectState, _PROJECTS
from orchestration.tools import patch_technical_artifact, save_technical_artifacts


class MermaidValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        _PROJECTS.clear()
        _PROJECTS["diagram-project"] = ProjectState(
            project_id="diagram-project",
            req_session_id="session-1",
            user_id="alice",
            technical_artifacts_md={"Technical_Architecture_Diagram.mmd": "flowchart TD\nA[\"App\"] --> B[\"API\"]"},
        )

    @patch("orchestration.tools.persist_project")
    def test_patch_technical_artifact_rejects_invalid_mermaid(self, _persist_project) -> None:
        result = patch_technical_artifact(
            "diagram-project",
            "Technical_Architecture_Diagram.mmd",
            "flowchart TD\nA[\"Frontend\" --> B[\"Backend\"]",
        )

        self.assertFalse(result["ok"])
        self.assertIn("Mermaid validation", result["error"])
        self.assertEqual(
            _PROJECTS["diagram-project"].technical_artifacts_md["Technical_Architecture_Diagram.mmd"],
            "flowchart TD\nA[\"App\"] --> B[\"API\"]",
        )
        _persist_project.assert_not_called()

    @patch("orchestration.tools.persist_project")
    def test_patch_technical_artifact_accepts_valid_mermaid(self, persist_project) -> None:
        result = patch_technical_artifact(
            "diagram-project",
            "Technical_Architecture_Diagram.mmd",
            "flowchart TD\nFrontend[\"Angular Frontend\"] --> Backend[\"Spring Boot Backend\"]",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            _PROJECTS["diagram-project"].technical_artifacts_md["Technical_Architecture_Diagram.mmd"],
            "flowchart TD\nFrontend[\"Angular Frontend\"] --> Backend[\"Spring Boot Backend\"]",
        )
        persist_project.assert_called_once_with("diagram-project")

    @patch("orchestration.tools.persist_project")
    def test_patch_technical_artifact_rejects_unquoted_parentheses(self, _persist_project) -> None:
        result = patch_technical_artifact(
            "diagram-project",
            "Technical_Architecture_Diagram.mmd",
            "flowchart TD\nA[Frontend (Angular)] --> B[Backend]",
        )

        self.assertFalse(result["ok"])
        self.assertIn("parentheses inside an unquoted bracket label", result["error"])
        _persist_project.assert_not_called()

    @patch("orchestration.tools.persist_project")
    def test_patch_technical_artifact_allows_parentheses_inside_quoted_labels(self, persist_project) -> None:
        result = patch_technical_artifact(
            "diagram-project",
            "Technical_Architecture_Diagram.mmd",
            "flowchart TD\nA[\"Frontend (Angular)\"] --> B[\"Backend\"]",
        )

        self.assertTrue(result["ok"])
        persist_project.assert_called_once_with("diagram-project")

    @patch("orchestration.tools.persist_project")
    def test_patch_technical_artifact_allows_structural_parentheses(self, persist_project) -> None:
        result = patch_technical_artifact(
            "diagram-project",
            "Technical_Architecture_Diagram.mmd",
            "flowchart TD\nA(Service) --> B((Database))",
        )

        self.assertTrue(result["ok"])
        persist_project.assert_called_once_with("diagram-project")

    @patch("orchestration.tools.persist_project")
    def test_save_technical_artifacts_validates_mermaid_blocks_in_markdown(self, _persist_project) -> None:
        result = save_technical_artifacts(
            "diagram-project",
            {
                "architecture.md": "# Architecture\n```mermaid\nflowchart TD\nA[\"Open\"] --> B[\"Closed\"\n```",
                "api.md": "# API",
            },
        )

        self.assertFalse(result["ok"])
        self.assertIn("architecture.md", result["validation_errors"])
        _persist_project.assert_not_called()


if __name__ == "__main__":
    unittest.main()
