from typing import Callable, Any
from agents.requirements_gathering_agent.agent import create_agent as create_req_agent
from agents.artefacts_generation_agent.agent import create_agent as create_art_agent
from agents.code_generation_agent.agent import create_agent as create_code_agent
from agents.integration_agent.agent import create_agent as create_integration_agent
from agents.qa_agent.agent import create_agent as create_qa_agent

AgentFactory = Callable[..., Any]  # llm + optional kwargs -> LlmAgent

AGENT_FACTORIES: dict[str, AgentFactory] = {
    "requirements": create_req_agent,
    "artifacts": create_art_agent,
    "code_generation": create_code_agent,
    "integration": create_integration_agent,
    "qa": create_qa_agent,
}
