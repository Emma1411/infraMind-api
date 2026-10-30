from functools import lru_cache

from openai import AsyncOpenAI

from config.settings import get_settings


class LLMNotConfigured(RuntimeError):
    """La clé d'API de l'IA est absente."""


@lru_cache
def get_llm_client() -> AsyncOpenAI:
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise LLMNotConfigured("DEEPSEEK_API_KEY manquante dans le fichier .env")
    return AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        timeout=60.0,
    )