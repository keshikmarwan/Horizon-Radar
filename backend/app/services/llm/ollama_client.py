"""
llm_client.py — Client HTTP per LLM remoti e locali.

Supporta:
- Ollama locale/remoto (`/api/chat`)
- Provider cloud compatibili OpenAI (OpenRouter, Together, DashScope)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    """Eccezione per errori del client LLM."""
    pass


class LLMClient:
    """
    Client per API remote compatibili OpenAI o Ollama locale.

    Provider supportati:
    - OpenRouter (openrouter.ai) — Qwen2.5-72B, Qwen2.5-32B
    - Together AI (together.ai) — Qwen2.5-72B-Instruct
    - Alibaba Cloud DashScope — Qwen nativo

    Configurazione tramite variabili d'ambiente:
    - LLM_PROVIDER: "ollama" | "openrouter" | "together" | "dashscope" | "openai_compat"
    - LLM_API_KEY: chiave API
    - LLM_MODEL: modello da usare (es. "qwen/qwen-2.5-72b-instruct")
    - LLM_BASE_URL: URL custom (opzionale, per provider compatibili OpenAI)
    - LLM_ENABLED: true/false

    Shortcut compatibili con il brief progetto:
    - OLLAMA_ENABLED=true
    - OLLAMA_HOST=http://127.0.0.1:11434
    - OLLAMA_MODEL=qwen2.5:3b
    """

    PROVIDERS = {
        "ollama": {
            "base_url": "http://127.0.0.1:11434",
            "auth_header": None,
            "model_prefix": "",
        },
        "openrouter": {
            "base_url": "https://openrouter.ai/api/v1",
            "auth_header": "Authorization",
            "model_prefix": "",
        },
        "together": {
            "base_url": "https://api.together.xyz/v1",
            "auth_header": "Authorization",
            "model_prefix": "",
        },
        "dashscope": {
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "auth_header": "Authorization",
            "model_prefix": "",
        },
        "openai_compat": {
            "base_url": None,  # Da configurare via LLM_BASE_URL
            "auth_header": "Authorization",
            "model_prefix": "",
        },
    }

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 120,
        enabled: bool = True,
    ):
        ollama_enabled = os.getenv("OLLAMA_ENABLED", "false").lower() == "true"
        resolved_provider = provider or os.getenv("LLM_PROVIDER") or ("ollama" if ollama_enabled else "openrouter")
        self.provider = resolved_provider.lower()

        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        if self.provider == "ollama":
            self.model = model or os.getenv("OLLAMA_MODEL") or os.getenv("LLM_MODEL", "qwen2.5:3b")
        else:
            self.model = model or os.getenv("LLM_MODEL", "qwen/qwen-2.5-72b-instruct")
        self.timeout = timeout
        self.ollama_think = os.getenv("OLLAMA_THINK", "true").lower() == "true"
        if self.provider == "ollama":
            self.enabled = enabled and os.getenv("OLLAMA_ENABLED", os.getenv("LLM_ENABLED", "false")).lower() == "true"
        else:
            self.enabled = enabled and os.getenv("LLM_ENABLED", "false").lower() == "true"

        # Determina base_url
        provider_config = self.PROVIDERS.get(self.provider, {})
        self.base_url = (
            base_url
            or os.getenv("OLLAMA_HOST")
            or os.getenv("OLLAMA_BASE_URL")
            or os.getenv("LLM_BASE_URL")
            or provider_config.get("base_url")
            or "https://openrouter.ai/api/v1"
        ).rstrip("/")

        if self.provider != "ollama" and not self.api_key:
            self.enabled = False
            logger.warning("LLM_API_KEY non impostata: LLM disabilitato")
        elif not self.enabled:
            logger.info(
                "LLM configurato ma disabilitato: imposta %s=true per attivare le chiamate",
                "OLLAMA_ENABLED" if self.provider == "ollama" else "LLM_ENABLED",
            )
        else:
            logger.info(
                "LLM abilitato: provider=%s model=%s base_url=%s",
                self.provider,
                self.model,
                self.base_url,
            )

        headers = {"Content-Type": "application/json"}
        if self.provider != "ollama" and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout, connect=10.0),
            headers=headers,
        )

    def is_available(self) -> bool:
        """Verifica se il LLM è abilitato e ha API key valida."""
        if not self.enabled:
            return False
        if self.provider != "ollama" and not self.api_key:
            return False
        # Ping leggero (solo check connettività)
        try:
            ping_path = "/api/tags" if self.provider == "ollama" else "/models"
            resp = self._client.get(ping_path, timeout=5.0)
            return resp.status_code in (200, 404)  # 404 ok se endpoint non esiste
        except Exception:
            return True  # Assume available se ha API key

    def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        json_mode: bool = False,
        max_tokens: int = 2048,
        think: Optional[bool] = None,
    ) -> str:
        """
        Esegue una chat completion.

        Args:
            messages: Lista di messaggi {role, content}
            system_prompt: Prompt di sistema opzionale
            temperature: Temperatura per il sampling (0.0-1.0)
            json_mode: Se True, richiede output JSON strutturato
            max_tokens: Token massimi in output

        Returns:
            Risposta testuale del modello
        """
        response = self.chat_with_meta(
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            json_mode=json_mode,
            max_tokens=max_tokens,
            think=think,
        )
        return response["content"]

    def chat_with_meta(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        json_mode: bool = False,
        max_tokens: int = 2048,
        think: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Esegue una chat completion e ritorna testo + meta utili (es. thinking Ollama)."""
        if not self.enabled:
            raise LLMClientError("LLM non è abilitato (LLM_ENABLED=false o API key mancante)")

        messages_with_system = messages.copy()
        if system_prompt:
            messages_with_system.insert(0, {"role": "system", "content": system_prompt})

        if self.provider == "ollama":
            resolved_think = self.ollama_think if think is None else think
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": messages_with_system,
                "stream": False,
                "think": resolved_think,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            }
            if json_mode:
                payload["format"] = "json"
        else:
            resolved_think = False
            payload = {
                "model": self.model,
                "messages": messages_with_system,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            if json_mode:
                # OpenRouter/Together supportano response_format
                payload["response_format"] = {"type": "json_object"}

            # Header extra per OpenRouter
            if self.provider == "openrouter":
                self._client.headers["HTTP-Referer"] = os.getenv("APP_BASE_URL", "http://localhost:3000")
                self._client.headers["X-Title"] = "Horizon Radar"

        try:
            endpoint = "/api/chat" if self.provider == "ollama" else "/chat/completions"
            resp = self._client.post(endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if self.provider == "ollama":
                message = data.get("message", {}) or {}
                content = message.get("content", "") or ""
                thinking = message.get("thinking", "") or ""
            else:
                message = data.get("choices", [{}])[0].get("message", {}) or {}
                content = message.get("content", "") or ""
                thinking = ""

            if not content and not thinking:
                raise LLMClientError("Risposta vuota dal LLM")

            return {
                "content": content,
                "thinking": thinking,
                "provider": self.provider,
                "model": self.model,
                "thinking_enabled": bool(resolved_think),
            }
        except httpx.TimeoutException as exc:
            raise LLMClientError(f"Timeout dopo {self.timeout}s") from exc
        except httpx.HTTPStatusError as exc:
            raise LLMClientError(f"HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
        except Exception as exc:
            raise LLMClientError(f"Errore LLM: {exc}") from exc

    def chat_with_json(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_retries: int = 2,
        max_tokens: int = 2048,
        think: Optional[bool] = None,
    ) -> dict[str, Any]:
        """
        Esegue una chat completion richiedendo output JSON.

        Args:
            messages: Lista di messaggi {role, content}
            system_prompt: Prompt di sistema opzionale
            temperature: Temperatura per il sampling
            max_retries: Numero di tentativi in caso di JSON malformed
            max_tokens: Token massimi in output

        Returns:
            Dizionario parsed dalla risposta JSON
        """
        parsed, _meta = self.chat_with_json_meta(
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_retries=max_retries,
            max_tokens=max_tokens,
            think=think,
        )
        return parsed

    def chat_with_json_meta(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_retries: int = 2,
        max_tokens: int = 2048,
        think: Optional[bool] = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Come chat_with_json, ma ritorna anche metadata della risposta LLM."""
        last_error: Optional[Exception] = None
        last_meta: dict[str, Any] = {}

        for attempt in range(max_retries + 1):
            try:
                response = self.chat_with_meta(
                    messages=messages,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    json_mode=True,
                    max_tokens=max_tokens,
                    think=think,
                )
                last_meta = response
                cleaned = response["content"].strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

                return json.loads(cleaned), last_meta
            except json.JSONDecodeError as exc:
                last_error = exc
                logger.warning(f"Tentativo {attempt + 1}: JSON malformed - {exc}")
                if attempt < max_retries:
                    continue
            except LLMClientError as exc:
                raise exc

        raise LLMClientError(
            f"Impossibile parsare JSON dopo {max_retries + 1} tentativi: {last_error}. "
            f"Thinking presente: {bool(last_meta.get('thinking'))}"
        )


# Singleton globale lazy
_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Restituisce un'istanza singleton di LLMClient."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def is_llm_available() -> bool:
    """Verifica se il LLM è abilitato e raggiungibile."""
    try:
        return get_llm_client().is_available()
    except Exception:
        return False


# Backward compatibility (per chi usa vecchi import)
OllamaClient = LLMClient
OllamaClientError = LLMClientError
get_ollama_client = get_llm_client
is_ollama_available = is_llm_available
