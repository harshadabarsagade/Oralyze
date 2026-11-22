"""LLM Dispatcher with strict fallback order."""
import logging
import os
from services.llm.base import LLMProvider
from services.llm.ibm import IBMGraniteProvider
from services.llm.openrouter import OpenRouterProvider
from services.llm.groq import GroqProvider
from services.llm.gemini import GeminiProvider

logger = logging.getLogger("oralyze.llm")

DEFAULT_FALLBACK_ORDER = ["ibm", "openrouter", "groq", "gemini"]

PROVIDERS: dict[str, type[LLMProvider]] = {
    "ibm": IBMGraniteProvider,
    "openrouter": OpenRouterProvider,
    "groq": GroqProvider,
    "gemini": GeminiProvider
}


def call_llm(messages: list[dict], max_tokens: int = 1500, temperature: float = 0.3) -> tuple[str, str]:
    """Execute LLM call across providers according to fallback priority.
    
    Returns (raw_text, provider_name).
    """
    primary = os.getenv("LLM_PROVIDER", "ibm").strip().lower()
    fallback_order_str = os.getenv("LLM_FALLBACK_ORDER", "ibm,openrouter,groq,gemini")
    fallback_order = [p.strip().lower() for p in fallback_order_str.split(",") if p.strip()]

    if primary in fallback_order:
        fallback_order.remove(primary)
    order = [primary] + fallback_order

    last_error = None
    for provider_name in order:
        cls = PROVIDERS.get(provider_name)
        if not cls:
            continue
        try:
            provider = cls()
            logger.info("[llm] Attempting provider=%s", provider_name)
            output = provider.chat(messages, max_tokens=max_tokens, temperature=temperature)
            if output and output.strip():
                logger.info("[llm] Success with provider=%s", provider_name)
                return output, provider_name
        except Exception as e:
            logger.warning("[llm] provider=%s failed reason=%s", provider_name, e)
            last_error = e
            continue

    raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")
