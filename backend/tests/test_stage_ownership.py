import unittest
from unittest.mock import patch

from orchestration.orchestrator import Orchestrator
from orchestration.store import ProjectState, Stage, _PROJECTS
from orchestration.tools import save_nontech_artifacts, save_technical_artifacts, submit_spec


class StageOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        _PROJECTS.clear()
        _PROJECTS["stage-project"] = ProjectState(
            project_id="stage-project",
            req_session_id="session-1",
            user_id="alice",
            stage=Stage.REQ,
        )

    @patch("orchestration.tools.persist_project")
    def test_spec_tool_does_not_advance_stage(self, persist_project) -> None:
        result = submit_spec("stage-project", {"project_name": "Planner"})

        self.assertTrue(result["ok"])
        self.assertEqual(_PROJECTS["stage-project"].stage, Stage.REQ)
        persist_project.assert_called_once_with("stage-project")

    @patch("orchestration.tools.persist_project")
    def test_artifact_tools_do_not_advance_stage(self, persist_project) -> None:
        project = _PROJECTS["stage-project"]
        project.stage = Stage.ARTIFACTS_NON_TECH

        nontech_result = save_nontech_artifacts("stage-project", {"Product_Brief.md": "# Brief"})
        self.assertTrue(nontech_result["ok"])
        self.assertEqual(project.stage, Stage.ARTIFACTS_NON_TECH)

        project.stage = Stage.TECH_ARTIFACTS
        technical_result = save_technical_artifacts(
            "stage-project",
            {"Technical_Architecture_Diagram.mmd": "flowchart TD\nA[\"App\"] --> B[\"API\"]"},
        )
        self.assertTrue(technical_result["ok"])
        self.assertEqual(project.stage, Stage.TECH_ARTIFACTS)
        self.assertEqual(persist_project.call_count, 2)

    @patch("orchestration.orchestrator.persist_project")
    def test_orchestrator_helper_advances_and_persists_stage(self, persist_project) -> None:
        project = _PROJECTS["stage-project"]

        Orchestrator()._set_stage(project, Stage.ARTIFACTS_NON_TECH, "test_transition")

        self.assertEqual(project.stage, Stage.ARTIFACTS_NON_TECH)
        persist_project.assert_called_once_with("stage-project")


if __name__ == "__main__":
    unittest.main()
