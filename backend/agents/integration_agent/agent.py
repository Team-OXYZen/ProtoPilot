from google.genai import types
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams, StreamableHTTPConnectionParams
from mcp import StdioServerParameters
import os

from core.logging_utils import log_event
from core.llm import create_litellm
from .instructions import INTEGRATION_AGENT_INSTRUCTIONS

GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/"
ATLASSIAN_MCP_URL = "https://mcp.atlassian.com/v1/mcp"

def create_github_mcp_toolset() -> McpToolset:
    """Create the GitHub MCP toolset using a server-side token from the environment."""
    log_event("TOOL", "github_mcp_toolset_create", {"url": GITHUB_MCP_URL})
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        log_event("ERROR", "github_mcp_missing_token", {"env_var": "GITHUB_TOKEN"}, status="fail")
        raise RuntimeError("Missing GITHUB_TOKEN in environment; required to create integration_agent GitHub MCP toolset.")

    toolset = McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=GITHUB_MCP_URL,
            headers={
                "Authorization": f"Bearer {github_token}",
                "X-MCP-Toolsets": "repos,issues,pull_requests",
                "X-MCP-Readonly": "false",
            },
        ),
    )
    log_event("TOOL", "github_mcp_toolset_ready", {"toolsets": "repos,issues,pull_requests"}, status="ok")
    return toolset

def create_atlassian_mcp_toolset() -> McpToolset:
    """Create the Atlassian MCP toolset used for Jira issue operations."""
    log_event("TOOL", "atlassian_mcp_toolset_create", {"url": ATLASSIAN_MCP_URL, "command": "npx mcp-remote"})
    toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx",
                args=["mcp-remote", ATLASSIAN_MCP_URL],
            ),
            timeout=30,
        ),
    )
    log_event("TOOL", "atlassian_mcp_toolset_ready", {"timeout": 30}, status="ok")
    return toolset

def create_agent(token: str, tools=None, toolsets: tuple[str, ...] = ("github", "atlassian")) -> LlmAgent:
    """Create an integration agent with the requested MCP toolsets attached."""
    model_name = os.getenv("LITELLM_MODEL_INTEGRATION") or os.getenv("LITELLM_MODEL")
    log_event(
        "AGENT",
        "integration_agent_create",
        {"toolsets": list(toolsets), "extra_tools_count": len(tools or []), "model": model_name},
    )
    llm = create_litellm(
        token,
        model=model_name,
    )
    agent_tools = list(tools or [])
    if "github" in toolsets:
        agent_tools.append(create_github_mcp_toolset())
    if "atlassian" in toolsets:
        agent_tools.append(create_atlassian_mcp_toolset())

    agent = LlmAgent(
        model=llm,
        name="integration_agent",
        description="Export generated code to GitHub and coordinate Atlassian Jira/Confluence delivery work",
        instruction=INTEGRATION_AGENT_INSTRUCTIONS,
        tools=agent_tools,
        generate_content_config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=8192,
        ),
    )
    log_event("AGENT", "integration_agent_ready", {"tools_count": len(agent_tools), "toolsets": list(toolsets)}, status="ok")
    return agent
