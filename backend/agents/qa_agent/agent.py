import os
from backend.core.llm import create_litellm
from google.genai import types
from google.adk.agents import LlmAgent
from .instructions import QA_AGENT_INSTRUCTIONS

def create_agent(token: str, tools=None) -> LlmAgent:
    llm = create_litellm(token, model=os.getenv("LITELLM_MODEL_CODEGEN"))
    return LlmAgent(
        model=llm,
        name="qa_agent",
        description="Perform quality assurance checks on generated Angular frontend code",
        instruction=QA_AGENT_INSTRUCTIONS,
        tools=tools or [],
        generate_content_config=types.GenerateContentConfig(
            temperature=0.3,          
            max_output_tokens=16384,
        ),
    )
