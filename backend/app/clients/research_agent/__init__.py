from functools import lru_cache

from app.clients.research_agent.base import ResearchAgentClient


@lru_cache
def get_research_agent_client() -> ResearchAgentClient:
    from app.config import settings

    if settings.research_agent_impl == "ollama":
        from app.clients.research_agent.ollama_client import OllamaResearchAgentClient

        return OllamaResearchAgentClient()

    from app.clients.research_agent.mock import MockResearchAgentClient

    return MockResearchAgentClient()
