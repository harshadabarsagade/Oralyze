"""Google Gemini API Provider (fallback)."""
import json
import logging
import os
import requests
from services.llm.base import LLMProvider

logger = logging.getLogger("oralyze.llm.gemini")


class GeminiProvider(LLMProvider):
    name = "gemini"

    def chat(self, messages: list[dict], max_tokens: int = 1500, temperature: float = 0.3) -> str:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not configured")

        model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

        # Combine system and user contents
        prompt_parts = []
        for m in messages:
            prompt_parts.append(f"{m.get('role').upper()}:\n{m.get('content')}")
        combined_text = "\n\n".join(prompt_parts)

        payload = {
            "contents": [{"parts": [{"text": combined_text}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json"
            }
        }

        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code != 200:
            logger.warning("[llm] provider=gemini status=%s reason=%s", resp.status_code, resp.text)
            raise RuntimeError(f"Gemini API call failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        candidates = data.get("candidates") or []
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "")
        return ""
