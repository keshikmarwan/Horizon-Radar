"""
LLM services — Client Ollama e utility per integrazione Qwen2.5.
"""

from .ollama_client import (
    OllamaClient,
    OllamaClientError,
    get_ollama_client,
    is_ollama_available,
)

__all__ = [
    "OllamaClient",
    "OllamaClientError",
    "get_ollama_client",
    "is_ollama_available",
]
