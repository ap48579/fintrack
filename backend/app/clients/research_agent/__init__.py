from functools import lru_cache

from app.clients.research_agent.base import ResearchAgentClient
from app.config import settings


@lru_cache
def get_research_agent_client() -> ResearchAgentClient:
    if settings.research_agent_impl == "anthropic":
        from app.clients.research_agent.anthropic_client import AnthropicResearchAgentClient

        return AnthropicResearchAgentClient()
    if settings.research_agent_impl == "ollama":
        from app.clients.research_agent.ollama_client import OllamaResearchAgentClient

        return OllamaResearchAgentClient()
    from app.clients.research_agent.mock import MockResearchAgentClient

    return MockResearchAgentClient()
