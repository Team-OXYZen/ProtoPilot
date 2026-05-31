import unittest

from orchestration.integration_payloads import build_confluence_pages_from_project, build_jira_context_from_project
from orchestration.store import ProjectState, _PROJECTS


class JiraContextPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        _PROJECTS.clear()

    def test_builds_context_from_spec_and_artifacts_without_designing_backlog(self) -> None:
        _PROJECTS["plan-project"] = ProjectState(
            project_id="plan-project",
            req_session_id="session-1",
            user_id="alice",
            project_title="Support Desk",
            spec={
                "project_name": "Support Desk",
                "problem_statement": "Help agents resolve tickets faster.",
                "functional_requirements": ["Agents can triage support tickets."],
            },
            nontech_artifacts_md={
                "PRD.md": "# PRD\nSupport desk requirements.",
                "user_stories.md": "# User Stories\nAs an agent, I can triage tickets.",
                "jira_plan.md": "# Jira Plan\nUse capability-based epics.",
            },
            technical_artifacts_md={
                "api_documentation.md": "# API\nGET /tickets",
            },
        )

        context = build_jira_context_from_project("plan-project")

        self.assertEqual(context["project_title"], "Support Desk")
        self.assertEqual(context["spec"]["project_name"], "Support Desk")
        self.assertIn("user_stories.md", context["nontech_artifacts_md"])
        self.assertIn("api_documentation.md", context["technical_artifacts_md"])
        self.assertEqual(context["jira_plan_artifact"], "# Jira Plan\nUse capability-based epics.")
        self.assertNotIn("epics", context)

    def test_builds_confluence_pages_from_all_artifacts(self) -> None:
        _PROJECTS["docs-project"] = ProjectState(
            project_id="docs-project",
            req_session_id="session-1",
            user_id="alice",
            project_title="Support Desk",
            nontech_artifacts_md={
                "PRD.md": "# PRD\nSupport desk requirements.",
                "user_flows.md": "# User Flows\nAgent triage flow.",
            },
            technical_artifacts_md={
                "api_documentation.md": "# API\nGET /tickets",
            },
        )

        pages = build_confluence_pages_from_project("docs-project")

        self.assertEqual(len(pages), 3)
        self.assertEqual(
            [(page["filename"], page["artifact_group"]) for page in pages],
            [
                ("PRD.md", "Product Artifacts"),
                ("user_flows.md", "Product Artifacts"),
                ("api_documentation.md", "Technical Artifacts"),
            ],
        )
        self.assertEqual(pages[0]["title"], "PRD")
        self.assertEqual(pages[2]["title"], "API Documentation")


if __name__ == "__main__":
    unittest.main()
