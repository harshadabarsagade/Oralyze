"""IBM watsonx.ai Granite 3.3 8B Instruct provider."""
import logging
import requests
from config import Config
from services.ibm_auth import get_token as get_iam_token
from services.llm.base import LLMProvider

logger = logging.getLogger("oralyze.llm.ibm")


class IBMGraniteProvider(LLMProvider):
    name = "ibm"

    def chat(self, messages: list[dict], max_tokens: int = 1500, temperature: float = 0.3) -> str:
        if Config.MOCK_MODE or not Config.IBM_API_KEY:
            raise RuntimeError("IBM_API_KEY not set or MOCK_MODE is enabled")

        token = get_iam_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        # Convert chat messages to watsonx prompt format
        system_content = ""
        user_content = ""
        for m in messages:
            if m.get("role") == "system":
                system_content = m.get("content", "")
            elif m.get("role") == "user":
                user_content = m.get("content", "")

        url = f"{Config.WATSONX_URL.rstrip('/')}/ml/v1/text/chat?version=2024-05-31"
        payload = {
            "project_id": Config.WATSONX_PROJECT_ID,
            "model_id": Config.GRANITE_MODEL_ID,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ],
            "parameters": {
                "max_new_tokens": max_tokens,
                "temperature": temperature,
                "decoding_method": "greedy"
            }
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=25)
        if resp.status_code != 200:
            logger.warning("[llm] provider=ibm status=%s error=%s", resp.status_code, resp.text)
            raise RuntimeError(f"IBM watsonx call failed with status {resp.status_code}: {resp.text}")

        data = resp.json()
        choices = data.get("choices") or []
        if choices:
            msg = choices[0].get("message") or {}
            return msg.get("content", "")

        results = data.get("results") or []
        if results:
            return results[0].get("generated_text", "")

        return ""
