from google.genai import types
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams, StreamableHTTPConnectionParams
from mcp import StdioServerParameters
import os
from core.llm import create_litellm
from .instructions import INTEGRATION_AGENT_INSTRUCTIONS

GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/"
ATLASSIAN_MCP_URL = "https://mcp.atlassian.com/v1/mcp"

def create_github_mcp_toolset() -> McpToolset:
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        raise RuntimeError("Missing GITHUB_TOKEN in environment; required to create integration_agent GitHub MCP toolset.")

    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=GITHUB_MCP_URL,
            headers={
                "Authorization": f"Bearer {github_token}",
                "X-MCP-Toolsets": "repos,issues,pull_requests",
                "X-MCP-Readonly": "false",
            },
        ),
    )

def create_atlassian_mcp_toolset() -> McpToolset:
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx",
                args=["mcp-remote", ATLASSIAN_MCP_URL],
            ),
            timeout=30,
        ),
    )

def create_agent(token: str, tools=None) -> LlmAgent:
    llm = create_litellm(
        token,
        model=os.getenv("LITELLM_MODEL_INTEGRATION") or os.getenv("LITELLM_MODEL"),
    )
    agent_tools = list(tools or [])
    agent_tools.append(create_github_mcp_toolset())
    agent_tools.append(create_atlassian_mcp_toolset())

    return LlmAgent(
        model=llm,
        name="integration_agent",
        description="Export generated code to GitHub and create Jira tasks from generated requirements",
        instruction=INTEGRATION_AGENT_INSTRUCTIONS,
        tools=agent_tools,
        generate_content_config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=8192,
        ),
    )
