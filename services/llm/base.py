"""Base interface for LLM providers."""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def chat(self, messages: list[dict], max_tokens: int = 1500, temperature: float = 0.3) -> str:
        """Send chat messages and return raw text response."""
        pass
