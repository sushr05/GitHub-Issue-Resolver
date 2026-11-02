import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    google_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "codellama:7b"
    hf_token: str = ""
    hf_model: str = "Qwen/Qwen2.5-Coder-32B-Instruct"

    # GitHub
    github_token: str = ""
    github_repo_owner: str = ""
    github_repo_name: str = ""

    # Paths
    workspace_dir: Path = Path("/tmp/ase_workspace")
    faiss_index_path: Path = Path("./data/faiss_index")
    symbol_index_path: Path = Path("./data/symbol_index.json")

    # Docker
    docker_image_name: str = "ase-test-runner"
    docker_timeout: int = 120

    # App
    log_level: str = "INFO"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Retrieval
    embedding_model: str = "all-MiniLM-L6-v2"
    retrieval_top_k: int = 10

    # LangGraph
    max_retries: int = 3


settings = Settings()


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
