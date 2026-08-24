"""Model provider protocol. Local Ollama by default — the whole pipeline
reproduces for $0. A Gemini free-tier client is included for anyone who wants
cloud inference instead; neither is required to run the test suite."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass
class ModelResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ModelProvider(Protocol):
    def complete(self, system: str, user: str) -> ModelResponse: ...


@dataclass
class OllamaProvider:
    model: str = "qwen2.5-coder:3b"
    host: str = "http://localhost:11434"
    timeout: float = 120.0

    def complete(self, system: str, user: str) -> ModelResponse:
        resp = httpx.post(
            f"{self.host}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"temperature": 0.1},
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return ModelResponse(text=data["message"]["content"])


@dataclass
class GeminiProvider:
    model: str = "gemini-2.5-flash"
    api_key: str | None = None
    timeout: float = 60.0

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not set and no api_key provided")

    def complete(self, system: str, user: str) -> ModelResponse:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.1},
        }
        resp = httpx.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        return ModelResponse(
            text=text,
            prompt_tokens=usage.get("promptTokenCount", 0),
            completion_tokens=usage.get("candidatesTokenCount", 0),
        )


def parse_provider(spec: str) -> ModelProvider:
    """spec like 'ollama:qwen2.5-coder:3b' or 'gemini:gemini-2.5-flash'."""
    kind, _, model = spec.partition(":")
    if kind == "ollama":
        return OllamaProvider(model=model or "qwen2.5-coder:3b")
    if kind == "gemini":
        return GeminiProvider(model=model or "gemini-2.5-flash")
    raise ValueError(f"unknown provider spec: {spec!r}")


def extract_json(text: str) -> dict:
    """Models wrap JSON in prose or code fences fairly often; find the object."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object found in model output: {text[:200]!r}")
    return json.loads(text[start : end + 1])
