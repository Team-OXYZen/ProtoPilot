import os
from google.genai import types
from google.adk.agents import LlmAgent
from core.llm import create_litellm
from .instructions import ARTEFACTS_GENERATION_AGENT_INSTRUCTIONS

def create_agent(token: str, tools=None, phase: str = "non_tech", username: str | None = None) -> LlmAgent:
    """Create artifacts generation agent for non-technical or technical artifacts.
    
    Args:
        token: OAuth token for LLM
        tools: Optional list of available tools
        phase: Artifact type - 'non_tech' (specs) or 'technical' (architecture)
        
    Returns:
        LlmAgent for artifact generation (temperature 0.2)
    """
    llm = create_litellm(token, model=os.getenv("LITELLM_MODEL_ARTIFACTS"), username=username)
    phase_instruction = (
        f"\n\nCurrent phase: {phase}\n"
        "Current project_id is provided in user message context.\n"
    )
    return LlmAgent(
        model=llm,
        name="artifacts_agent",
        description="Generate MVP artifacts from requirements JSON",
        instruction=ARTEFACTS_GENERATION_AGENT_INSTRUCTIONS + phase_instruction,
        tools=tools or [],
        generate_content_config=types.GenerateContentConfig(
            temperature=0.2,          
            max_output_tokens=12288,
        ),
    )
