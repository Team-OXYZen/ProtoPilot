import os
from google.adk.agents import LlmAgent
from google.genai import types
from core.llm import create_litellm
from .instructions import REQUIREMENTS_GATHERING_AGENT_INSTRUCTIONS

def create_agent(token: str, tools=None, username: str | None = None) -> LlmAgent:
    """Create requirements gathering agent.
    
    Args:
        token: OAuth token for LLM
        tools: Optional list of available tools
        
    Returns:
        LlmAgent for requirements gathering (temperature 0.7)
    """
    llm = create_litellm(token, model=os.getenv("LITELLM_MODEL_REQUIREMENTS"), username=username)
    return LlmAgent(
        model=llm,
        name="reqs_gathering_agent",
        description="A Technical Product Manager Assistant",
        instruction=REQUIREMENTS_GATHERING_AGENT_INSTRUCTIONS,
        tools=tools or [],
        generate_content_config=types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=4096,
        ),
    )
