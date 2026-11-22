"""Groq API Provider (ultra-fast Llama-3 fallback)."""
import logging
import os
import requests
from services.llm.base import LLMProvider

logger = logging.getLogger("oralyze.llm.groq")


class GroqProvider(LLMProvider):
    name = "groq"

    def chat(self, messages: list[dict], max_tokens: int = 1500, temperature: float = 0.3) -> str:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not configured")

        model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": {"type": "json_object"}
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code != 200:
            logger.warning("[llm] provider=groq status=%s reason=%s", resp.status_code, resp.text)
            raise RuntimeError(f"Groq API call failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        choices = data.get("choices") or []
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return ""
