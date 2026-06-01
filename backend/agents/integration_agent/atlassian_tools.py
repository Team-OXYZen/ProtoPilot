import httpx
from google.adk.tools import FunctionTool

from core.logging_utils import log_event

_ATLASSIAN_API_BASE = "https://api.atlassian.com"


def _err(tag: str, ctx: dict, status: int, body: str) -> dict:
    log_event("ERROR", tag, {**ctx, "status": status, "body": body[:400]}, status="fail")
    return {"error": f"HTTP {status}: {body}"}


def create_atlassian_function_tools(access_token: str) -> list[FunctionTool]:
    """Return Atlassian REST API tools bound to the user's personal OAuth access token."""

    _h = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    # ── Discovery ─────────────────────────────────────────────────────────────

    async def get_atlassian_accessible_sites() -> dict:
        """Return all Atlassian cloud sites the authenticated user can access.

        Always call this first to get the cloud_id and site_url required by every
        other tool.

        Returns:
            {"sites": [{"id": "<cloud_id>", "url": "https://xyz.atlassian.net",
                        "name": "xyz", "scopes": [...]}]}
        """
        log_event("TOOL", "atlassian_get_sites", {})
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{_ATLASSIAN_API_BASE}/oauth/token/accessible-resources", headers=_h)
            if r.status_code != 200:
                return _err("atlassian_get_sites_failed", {}, r.status_code, r.text)
            sites = r.json()
            log_event("TOOL", "atlassian_get_sites_done", {"count": len(sites)}, status="ok")
            return {"sites": sites}

    # ── Jira ──────────────────────────────────────────────────────────────────

    async def list_jira_projects(cloud_id: str) -> dict:
        """List all Jira Software projects in the given Atlassian cloud site.

        Args:
            cloud_id: Atlassian cloud instance ID from get_atlassian_accessible_sites.

        Returns:
            {"projects": [{"key": "PP", "name": "...", "id": "...", "style": "scrum|kanban"}]}
        """
        log_event("TOOL", "jira_list_projects", {"cloud_id": cloud_id})
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(
                f"{_ATLASSIAN_API_BASE}/ex/jira/{cloud_id}/rest/api/3/project/search",
                headers=_h,
                params={"typeKey": "software", "maxResults": 50},
            )
            if r.status_code != 200:
                return _err("jira_list_projects_failed", {"cloud_id": cloud_id}, r.status_code, r.text)
            projects = [
                {"key": p["key"], "name": p["name"], "id": p["id"],
                 "style": p.get("style", ""), "type": p.get("projectTypeKey", "")}
                for p in r.json().get("values", [])
            ]
            log_event("TOOL", "jira_list_projects_done", {"count": len(projects)}, status="ok")
            return {"projects": projects}

    async def create_jira_project(
        cloud_id: str,
        name: str,
        key: str,
        project_type: str = "scrum",
        description: str = "",
    ) -> dict:
        """Create a new Jira Software project.

        Use this when no suitable Scrum project exists. The key must be 2-10 uppercase
        letters unique within the Jira site.

        Args:
            cloud_id: Atlassian cloud instance ID.
            name: Project display name.
            key: Project key (2-10 uppercase letters, e.g. "PP").
            project_type: "scrum" or "kanban" (default "scrum").
            description: Optional project description.

        Returns:
            {"key": "PP", "id": "..."}
        """
        log_event("TOOL", "jira_create_project", {"cloud_id": cloud_id, "name": name, "key": key})
        template_key = "com.pyxis.greenhopper.jira:gh-scrum-template" if project_type == "scrum" else "com.pyxis.greenhopper.jira:gh-kanban-template"
        body = {
            "name": name,
            "key": key.upper(),
            "projectTypeKey": "software",
            "projectTemplateKey": template_key,
            "description": description,
        }
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{_ATLASSIAN_API_BASE}/ex/jira/{cloud_id}/rest/api/3/project",
                headers=_h,
                json=body,
            )
            if r.status_code not in (200, 201):
                return _err("jira_create_project_failed", {"cloud_id": cloud_id, "key": key}, r.status_code, r.text)
            data = r.json()
            log_event("TOOL", "jira_create_project_done", {"key": data.get("key"), "id": data.get("id")}, status="ok")
            return {"key": data.get("key"), "id": data.get("id")}

    async def get_jira_project_meta(cloud_id: str, project_key: str) -> dict:
        """Return issue types and their fields for a Jira project.

        Call this before creating issues to discover issue types (Epic, Story, Task,
        Sub-task, Bug) and which fields are available.

        Args:
            cloud_id: Atlassian cloud instance ID.
            project_key: Jira project key, e.g. "TES".

        Returns:
            {"issue_types": [{"id": "...", "name": "Epic", "subtask": false}]}
        """
        log_event("TOOL", "jira_get_project_meta", {"cloud_id": cloud_id, "project_key": project_key})
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(
                f"{_ATLASSIAN_API_BASE}/ex/jira/{cloud_id}/rest/api/3/issue/createmeta",
                headers=_h,
                params={"projectKeys": project_key, "expand": "projects.issuetypes.fields"},
            )
            if r.status_code != 200:
                return _err("jira_get_project_meta_failed", {"cloud_id": cloud_id, "project_key": project_key}, r.status_code, r.text)
            projects = r.json().get("projects", [])
            if not projects:
                return {"error": f"Project {project_key} not found or not accessible."}
            issue_types = [
                {"id": it["id"], "name": it["name"], "subtask": it.get("subtask", False)}
                for it in projects[0].get("issuetypes", [])
            ]
            log_event("TOOL", "jira_get_project_meta_done", {"issue_types": [t["name"] for t in issue_types]}, status="ok")
            return {"issue_types": issue_types}

    async def create_jira_issue(
        cloud_id: str,
        project_key: str,
        issue_type: str,
        summary: str,
        description: str = "",
        parent_key: str = "",
        labels: str = "",
        priority: str = "",
        story_points: int = 0,
    ) -> dict:
        """Create a Jira issue: Epic, Story, Task, Sub-task, or Bug.

        For Stories under an Epic, set parent_key to the Epic key (e.g. "PP-1").
        For Sub-tasks, set parent_key to the parent Story/Task key.

        Args:
            cloud_id: Atlassian cloud instance ID.
            project_key: Jira project key.
            issue_type: "Epic", "Story", "Task", "Sub-task", or "Bug".
            summary: Issue title.
            description: Issue body (plain text).
            parent_key: Parent issue key for hierarchy (empty = top-level).
            labels: Comma-separated labels, e.g. "frontend,auth".
            priority: "Highest", "High", "Medium", "Low", or "Lowest".
            story_points: Story point estimate (0 = omit).

        Returns:
            {"key": "PP-5", "id": "..."}
        """
        log_event("TOOL", "jira_create_issue", {
            "cloud_id": cloud_id, "project_key": project_key,
            "issue_type": issue_type, "summary": summary[:60],
        })
        fields: dict = {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": summary,
        }
        if description:
            fields["description"] = {
                "type": "doc", "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
            }
        if parent_key:
            fields["parent"] = {"key": parent_key}
        if labels:
            fields["labels"] = [l.strip() for l in labels.split(",") if l.strip()]
        if priority:
            fields["priority"] = {"name": priority}
        if story_points > 0:
            fields["customfield_10028"] = story_points

        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{_ATLASSIAN_API_BASE}/ex/jira/{cloud_id}/rest/api/3/issue",
                headers=_h,
                json={"fields": fields},
            )
            if r.status_code not in (200, 201):
                return _err("jira_create_issue_failed", {"cloud_id": cloud_id, "project_key": project_key, "issue_type": issue_type}, r.status_code, r.text)
            data = r.json()
            log_event("TOOL", "jira_create_issue_done", {"key": data["key"], "type": issue_type}, status="ok")
            return {"key": data["key"], "id": data["id"]}

    async def get_jira_boards(cloud_id: str, project_key: str) -> dict:
        """List Scrum/Kanban boards for a Jira project.

        Use this to get the board_id needed to create sprints.

        Args:
            cloud_id: Atlassian cloud instance ID.
            project_key: Jira project key.

        Returns:
            {"boards": [{"id": 1, "name": "...", "type": "scrum|kanban"}]}
        """
        log_event("TOOL", "jira_get_boards", {"cloud_id": cloud_id, "project_key": project_key})
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(
                f"{_ATLASSIAN_API_BASE}/ex/jira/{cloud_id}/rest/agile/1.0/board",
                headers=_h,
                params={"projectKeyOrId": project_key},
            )
            if r.status_code != 200:
                return _err("jira_get_boards_failed", {"cloud_id": cloud_id, "project_key": project_key}, r.status_code, r.text)
            boards = [
                {"id": b["id"], "name": b["name"], "type": b.get("type", "")}
                for b in r.json().get("values", [])
            ]
            log_event("TOOL", "jira_get_boards_done", {"count": len(boards)}, status="ok")
            return {"boards": boards}

    async def create_jira_sprint(
        cloud_id: str,
        board_id: int,
        name: str,
        goal: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> dict:
        """Create a new sprint on a Scrum board.

        Args:
            cloud_id: Atlassian cloud instance ID.
            board_id: Board ID from get_jira_boards.
            name: Sprint name, e.g. "Sprint 1".
            goal: Sprint goal description.
            start_date: ISO-8601 datetime, e.g. "2024-06-03T00:00:00.000Z".
            end_date: ISO-8601 datetime, e.g. "2024-06-09T00:00:00.000Z".

        Returns:
            {"id": 42, "name": "Sprint 1", "state": "future"}
        """
        log_event("TOOL", "jira_create_sprint", {"cloud_id": cloud_id, "board_id": board_id, "name": name})
        body: dict = {"name": name, "originBoardId": board_id}
        if goal:
            body["goal"] = goal
        if start_date:
            body["startDate"] = start_date
        if end_date:
            body["endDate"] = end_date
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{_ATLASSIAN_API_BASE}/ex/jira/{cloud_id}/rest/agile/1.0/sprint",
                headers=_h,
                json=body,
            )
            if r.status_code not in (200, 201):
                return _err("jira_create_sprint_failed", {"cloud_id": cloud_id, "board_id": board_id}, r.status_code, r.text)
            data = r.json()
            log_event("TOOL", "jira_create_sprint_done", {"id": data["id"], "name": data["name"]}, status="ok")
            return {"id": data["id"], "name": data["name"], "state": data.get("state", "")}

    async def move_issues_to_sprint(cloud_id: str, sprint_id: int, issue_keys: str) -> dict:
        """Move issues into a sprint.

        Args:
            cloud_id: Atlassian cloud instance ID.
            sprint_id: Sprint ID from create_jira_sprint.
            issue_keys: Comma-separated issue keys, e.g. "PP-1,PP-2,PP-3".

        Returns:
            {"moved": true, "count": 3}
        """
        keys = [k.strip() for k in issue_keys.split(",") if k.strip()]
        log_event("TOOL", "jira_move_to_sprint", {"cloud_id": cloud_id, "sprint_id": sprint_id, "count": len(keys)})
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{_ATLASSIAN_API_BASE}/ex/jira/{cloud_id}/rest/agile/1.0/sprint/{sprint_id}/issue",
                headers=_h,
                json={"issues": keys},
            )
            if r.status_code not in (200, 201, 204):
                return _err("jira_move_to_sprint_failed", {"cloud_id": cloud_id, "sprint_id": sprint_id}, r.status_code, r.text)
            log_event("TOOL", "jira_move_to_sprint_done", {"sprint_id": sprint_id, "count": len(keys)}, status="ok")
            return {"moved": True, "count": len(keys)}

    # ── Confluence (v2 API — requires granular scopes) ────────────────────────

    async def list_confluence_spaces(cloud_id: str) -> dict:
        """List Confluence spaces the user can access.

        Uses Confluence REST API v2. Always call this to get the numeric space id
        required by find_confluence_page, create_confluence_page, and
        update_confluence_page.

        Args:
            cloud_id: Atlassian cloud instance ID.

        Returns:
            {"spaces": [{"key": "MS", "id": "123456", "name": "My Software Team", "type": "global"}]}
        """
        log_event("TOOL", "confluence_list_spaces", {"cloud_id": cloud_id})
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(
                f"{_ATLASSIAN_API_BASE}/ex/confluence/{cloud_id}/wiki/api/v2/spaces",
                headers=_h,
                params={"limit": 50},
            )
            if r.status_code != 200:
                return _err("confluence_list_spaces_failed", {"cloud_id": cloud_id}, r.status_code, r.text)
            spaces = [
                {"key": s.get("key", ""), "id": str(s.get("id", "")), "name": s.get("name", ""), "type": s.get("type", "")}
                for s in r.json().get("results", [])
            ]
            log_event("TOOL", "confluence_list_spaces_done", {"count": len(spaces), "keys": [s["key"] for s in spaces]}, status="ok")
            return {"spaces": spaces}

    async def create_confluence_space(
        cloud_id: str,
        name: str,
        key: str,
        description: str = "",
    ) -> dict:
        """Create a new Confluence global space using the v2 API.

        Use this when no suitable space exists. The key must be unique, uppercase
        letters and numbers only (e.g. "PP").

        Args:
            cloud_id: Atlassian cloud instance ID.
            name: Space display name, e.g. "ProtoPilot Projects".
            key: Space key (uppercase letters/numbers, e.g. "PP").
            description: Optional space description (plain text).

        Returns:
            {"key": "PP", "id": "123456", "name": "ProtoPilot Projects"}
        """
        log_event("TOOL", "confluence_create_space", {"cloud_id": cloud_id, "name": name, "key": key})
        body: dict = {
            "key": key.upper(),
            "name": name,
            "type": "global",
        }
        if description:
            body["description"] = description
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{_ATLASSIAN_API_BASE}/ex/confluence/{cloud_id}/wiki/api/v2/spaces",
                headers=_h,
                json=body,
            )
            if r.status_code not in (200, 201):
                return _err("confluence_create_space_failed", {"cloud_id": cloud_id, "key": key}, r.status_code, r.text)
            data = r.json()
            log_event("TOOL", "confluence_create_space_done", {"key": data.get("key"), "name": data.get("name")}, status="ok")
            return {"key": data.get("key"), "id": str(data.get("id", "")), "name": data.get("name")}

    async def find_confluence_page(cloud_id: str, space_id: str, title: str) -> dict:
        """Search for a Confluence page by title within a space (v2 API).

        Always call list_confluence_spaces first to get the numeric space_id.
        Call this before creating a page to avoid duplicates — if found, use
        update_confluence_page instead.

        Args:
            cloud_id: Atlassian cloud instance ID.
            space_id: Numeric space ID from list_confluence_spaces (e.g. "123456").
            title: Exact page title to search for.

        Returns:
            {"found": true, "page_id": "...", "version": 3, "title": "..."} or {"found": false}
        """
        log_event("TOOL", "confluence_find_page", {"cloud_id": cloud_id, "space_id": space_id, "title": title[:60]})
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(
                f"{_ATLASSIAN_API_BASE}/ex/confluence/{cloud_id}/wiki/api/v2/pages",
                headers=_h,
                params={"space-id": space_id, "title": title, "limit": 1},
            )
            if r.status_code != 200:
                return _err("confluence_find_page_failed", {"cloud_id": cloud_id, "space_id": space_id}, r.status_code, r.text)
            results = r.json().get("results", [])
            if not results:
                log_event("TOOL", "confluence_find_page_done", {"found": False}, status="ok")
                return {"found": False}
            page_id = str(results[0]["id"])
            # Fetch full page to get accurate version number (v2 list omits version)
            rv = await c.get(
                f"{_ATLASSIAN_API_BASE}/ex/confluence/{cloud_id}/wiki/api/v2/pages/{page_id}",
                headers=_h,
            )
            if rv.status_code != 200:
                return _err("confluence_find_page_version_failed", {"cloud_id": cloud_id, "page_id": page_id}, rv.status_code, rv.text)
            detail = rv.json()
            ver = detail.get("version", {}).get("number", 1)
            log_event("TOOL", "confluence_find_page_done", {"found": True, "page_id": page_id, "version": ver}, status="ok")
            return {"found": True, "page_id": page_id, "title": detail["title"], "version": ver}

    async def create_confluence_page(
        cloud_id: str,
        space_id: str,
        title: str,
        body_storage: str,
        parent_page_id: str = "",
        site_url: str = "",
        space_key: str = "",
    ) -> dict:
        """Create a new Confluence page using Confluence storage format (v2 API).

        Always call list_confluence_spaces first to get the numeric space_id.

        Storage format quick reference (HTML-like XML):
          <h1>Heading 1</h1>  <h2>Heading 2</h2>  <h3>Heading 3</h3>
          <p>Paragraph. <strong>Bold</strong>. <em>Italic</em>. <code>mono</code>.</p>
          <ul><li>Bullet</li></ul>
          <ol><li>Numbered</li></ol>
          <table><tbody>
            <tr><th>Col1</th><th>Col2</th></tr>
            <tr><td>Cell1</td><td>Cell2</td></tr>
          </tbody></table>
          <ac:structured-macro ac:name="code">
            <ac:parameter ac:name="language">python</ac:parameter>
            <ac:plain-text-body>print("hello")</ac:plain-text-body>
          </ac:structured-macro>

        Args:
            cloud_id: Atlassian cloud instance ID.
            space_id: Numeric space ID from list_confluence_spaces (e.g. "123456").
            title: Page title.
            body_storage: Page content in Confluence storage format (XML).
            parent_page_id: Optional parent page ID for nesting.
            site_url: Site URL (e.g. "https://xyz.atlassian.net") for the response URL.
            space_key: Space key (e.g. "PP") used only for constructing the response URL.

        Returns:
            {"page_id": "...", "title": "...", "url": "https://..."}
        """
        log_event("TOOL", "confluence_create_page", {"cloud_id": cloud_id, "space_id": space_id, "title": title[:60]})
        body: dict = {
            "spaceId": space_id,
            "status": "current",
            "title": title,
            "body": {"representation": "storage", "value": body_storage},
        }
        if parent_page_id:
            body["parentId"] = parent_page_id
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{_ATLASSIAN_API_BASE}/ex/confluence/{cloud_id}/wiki/api/v2/pages",
                headers=_h,
                json=body,
            )
            if r.status_code not in (200, 201):
                return _err("confluence_create_page_failed", {"cloud_id": cloud_id, "space_id": space_id, "title": title[:60]}, r.status_code, r.text)
            data = r.json()
            page_id = str(data["id"])
            sk = space_key or space_id
            url = f"{site_url.rstrip('/')}/wiki/spaces/{sk}/pages/{page_id}" if site_url else f"/wiki/pages/{page_id}"
            log_event("TOOL", "confluence_create_page_done", {"page_id": page_id, "title": title[:60]}, status="ok")
            return {"page_id": page_id, "title": data["title"], "url": url}

    async def update_confluence_page(
        cloud_id: str,
        page_id: str,
        title: str,
        body_storage: str,
        current_version: int,
        site_url: str = "",
        space_key: str = "",
    ) -> dict:
        """Update an existing Confluence page using storage format (v2 API).

        Args:
            cloud_id: Atlassian cloud instance ID.
            page_id: Page ID from find_confluence_page.
            title: Page title (can remain unchanged).
            body_storage: New page content in Confluence storage format (XML).
            current_version: Current version number from find_confluence_page.
            site_url: Site URL for constructing the response URL.
            space_key: Space key used only for constructing the response URL.

        Returns:
            {"updated": true, "page_id": "...", "new_version": 4, "url": "https://..."}
        """
        log_event("TOOL", "confluence_update_page", {"cloud_id": cloud_id, "page_id": page_id, "title": title[:60]})
        body = {
            "id": page_id,
            "status": "current",
            "title": title,
            "version": {"number": current_version + 1, "message": "Updated by ProtoPilot"},
            "body": {"representation": "storage", "value": body_storage},
        }
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.put(
                f"{_ATLASSIAN_API_BASE}/ex/confluence/{cloud_id}/wiki/api/v2/pages/{page_id}",
                headers=_h,
                json=body,
            )
            if r.status_code not in (200, 201):
                return _err("confluence_update_page_failed", {"cloud_id": cloud_id, "page_id": page_id}, r.status_code, r.text)
            data = r.json()
            new_ver = data.get("version", {}).get("number", current_version + 1)
            url = f"{site_url.rstrip('/')}/wiki/pages/{data['id']}" if site_url else f"/wiki/pages/{data['id']}"
            log_event("TOOL", "confluence_update_page_done", {"page_id": data["id"], "new_version": new_ver}, status="ok")
            return {"updated": True, "page_id": str(data["id"]), "new_version": new_ver, "url": url}

    return [
        FunctionTool(func=get_atlassian_accessible_sites),
        FunctionTool(func=list_jira_projects),
        FunctionTool(func=create_jira_project),
        FunctionTool(func=get_jira_project_meta),
        FunctionTool(func=create_jira_issue),
        FunctionTool(func=get_jira_boards),
        FunctionTool(func=create_jira_sprint),
        FunctionTool(func=move_issues_to_sprint),
        FunctionTool(func=list_confluence_spaces),
        FunctionTool(func=create_confluence_space),
        FunctionTool(func=find_confluence_page),
        FunctionTool(func=create_confluence_page),
        FunctionTool(func=update_confluence_page),
    ]
