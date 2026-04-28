import os
import logging
from google.adk.models.lite_llm import LiteLlm

logger = logging.getLogger(__name__)

def create_litellm(oauth_token: str, model: str | None = None) -> LiteLlm:
    litellm_api_key = os.getenv("LITELLM_API_KEY", "")
    resolved_model = model or os.getenv("LITELLM_MODEL", "")
    api_base = os.getenv("LITELLM_API_BASE", "")

    if not (litellm_api_key and resolved_model and api_base):
        raise RuntimeError("Missing LITELLM_API_KEY / LITELLM_MODEL / LITELLM_API_BASE in .env")

    logger.info("[LiteLLM] Using model: %s", resolved_model)
    return LiteLlm(
        model=resolved_model,
        api_base=api_base,
        api_key=litellm_api_key,
        extra_headers={
            "Authorization": f"Bearer {oauth_token}",
            "x-litellm-api-key": litellm_api_key,
        },
    )

    # Groq LLM for testing, not used in production
    # return LiteLlm(
    #     model="groq/llama-3.3-70b-versatile",
    #     api_key=os.environ.get("GROQ_API_KEY")
    # )