from google.genai import types
from google.adk.agents import LlmAgent
import os
from core.llm import create_litellm
from .instructions import ANGULAR_CODEGEN_INSTRUCTIONS

def create_agent(token: str, tools=None, instructions: str | None = None, username: str | None = None) -> LlmAgent:
    """Create code generation agent for Angular/Java code.
    
    Args:
        token: OAuth token for LLM
        tools: Optional list of available tools
        instructions: Optional custom instructions (uses default if not provided)
        
    Returns:
        LlmAgent for code generation (temperature 0.3)
    """
    llm = create_litellm(token, model=os.getenv("LITELLM_MODEL_CODEGEN"), username=username)
    return LlmAgent(
        model=llm,
        name="code_generation_agent",
        description="Generate production-ready code from specifications",
        instruction=instructions or ANGULAR_CODEGEN_INSTRUCTIONS,
        tools=tools or [],
        generate_content_config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=16384,
        ),
    )
