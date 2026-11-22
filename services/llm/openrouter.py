"""OpenRouter API Provider (OpenAI-compatible quota fallback)."""
import logging
import os
import requests
from services.llm.base import LLMProvider

logger = logging.getLogger("oralyze.llm.openrouter")


class OpenRouterProvider(LLMProvider):
    name = "openrouter"

    def chat(self, messages: list[dict], max_tokens: int = 1500, temperature: float = 0.3) -> str:
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY not configured")

        model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://mohitraj8503.github.io/Oralyze/",
            "X-Title": "Oralyze AI Viva Examiner"
        }
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": {"type": "json_object"}
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        if resp.status_code != 200:
            logger.warning("[llm] provider=openrouter status=%s reason=%s", resp.status_code, resp.text)
            raise RuntimeError(f"OpenRouter API call failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        choices = data.get("choices") or []
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return ""
