from google.genai import types
from google.adk.agents import LlmAgent
import os
from core.llm import create_litellm
from .instructions import ANGULAR_CODEGEN_INSTRUCTIONS

def create_agent(token: str, tools=None, instructions: str | None = None) -> LlmAgent:
    llm = create_litellm(token, model=os.getenv("LITELLM_MODEL_CODEGEN"))
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
