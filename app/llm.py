"""
LLM factory — returns Google Gemini Flash (free tier) or falls back to Ollama.

Usage:
    llm = get_llm()
    response = llm.invoke("Hello")
"""
import logging

from langchain_core.language_models import BaseChatModel

from app.config import settings

logger = logging.getLogger(__name__)


def get_llm() -> BaseChatModel:
    if settings.google_api_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            logger.info("Using Google Gemini 2.0 Flash")
            return ChatGoogleGenerativeAI(
                model="gemini-2.0-flash-lite",
                google_api_key=settings.google_api_key,
                temperature=0.2,
                convert_system_message_to_human=True,
            )
        except Exception as e:
            logger.warning("Gemini init failed: %s — trying HuggingFace", e)

    if settings.hf_token:
        try:
            from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
            logger.info("Using HuggingFace model: %s", settings.hf_model)
            endpoint = HuggingFaceEndpoint(
                repo_id=settings.hf_model,
                huggingfacehub_api_token=settings.hf_token,
                temperature=0.2,
                max_new_tokens=4096,
            )
            return ChatHuggingFace(llm=endpoint)
        except Exception as e:
            logger.warning("HuggingFace init failed: %s — falling back to Ollama", e)

    try:
        from langchain_ollama import ChatOllama
    except ImportError:
        from langchain_community.chat_models.ollama import (
            ChatOllama,  # type: ignore[no-redef]
        )
    logger.info("Using Ollama model: %s", settings.ollama_model)
    return ChatOllama(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        temperature=0.2,
    )
