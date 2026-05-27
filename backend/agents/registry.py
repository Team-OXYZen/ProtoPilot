from typing import Callable, Any
from agents.requirements_gathering_agent.agent import create_agent as create_req_agent
from agents.artefacts_generation_agent.agent import create_agent as create_art_agent
from agents.code_generation_agent.agent import create_agent as create_code_agent
<<<<<<< feat/github-jira-integrations
from agents.integration_agent.agent import create_agent as create_integration_agent
from agents.integration_agent.agent import create_jira_agent
=======
from agents.code_review_agent.agent import create_agent as create_code_review_agent
>>>>>>> main
from agents.qa_agent.agent import create_agent as create_qa_agent

AgentFactory = Callable[..., Any]  # llm + optional kwargs -> LlmAgent

AGENT_FACTORIES: dict[str, AgentFactory] = {
    "requirements": create_req_agent,
    "artifacts": create_art_agent,
    "code_generation": create_code_agent,
<<<<<<< feat/github-jira-integrations
    "integration": create_integration_agent,
    "jira_integration": create_jira_agent,
=======
    "code_review": create_code_review_agent,
>>>>>>> main
    "qa": create_qa_agent,
}
