"""FastAPI dependency injection."""
from functools import lru_cache

from app.agents.indexing_agent import RepositoryIndexingAgent
from app.config import Settings, settings
from app.docker_runner.runner import DockerTestRunner
from app.vectorstore.faiss_store import FAISSStore


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return settings


@lru_cache(maxsize=1)
def get_faiss_store() -> FAISSStore:
    store = FAISSStore(model_name=settings.embedding_model)
    try:
        store.load(settings.faiss_index_path)
    except FileNotFoundError:
        pass
    return store


@lru_cache(maxsize=1)
def get_indexing_agent() -> RepositoryIndexingAgent:
    return RepositoryIndexingAgent()


@lru_cache(maxsize=1)
def get_test_runner() -> DockerTestRunner:
    return DockerTestRunner()
