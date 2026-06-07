import os

from google.adk.agents import LlmAgent
from google.genai import types

from core.llm import create_litellm
from .instructions import CODE_REVIEW_AGENT_INSTRUCTIONS


def create_agent(token: str, tools=None, username: str | None = None) -> LlmAgent:
    """Create code review and build verification agent.
    
    Args:
        token: OAuth token for LLM
        tools: Optional list of available tools
        
    Returns:
        LlmAgent for code review, UX audit, and build repair (temperature 0.1)
    """
    llm = create_litellm(token, model=os.getenv("LITELLM_MODEL_CODE_REVIEW") or os.getenv("LITELLM_MODEL_CODEGEN"), username=username)
    return LlmAgent(
        model=llm,
        name="code_review_agent",
        description="Build, review, and repair generated Angular frontend code",
        instruction=CODE_REVIEW_AGENT_INSTRUCTIONS,
        tools=tools or [],
        generate_content_config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=16384,
        ),
    )
