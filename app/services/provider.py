from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Callable

import httpx

from app.config import settings


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _strict_json_schema(schema: dict) -> dict:
    """Convert a Pydantic schema to the closed, all-fields-required form APIs expect."""
    result = json.loads(json.dumps(schema))

    def visit(node):
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["additionalProperties"] = False
                node["required"] = list(properties)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(result)
    return result


@dataclass
class ModelResult:
    text: str
    usage: dict


class OpenAICompatibleProvider:
    """Minimal provider for OpenAI-compatible chat/embedding endpoints.

    The semantic-memory system is intentionally vendor-agnostic. Any provider exposing compatible
    `/chat/completions` and `/embeddings` routes can be configured via environment variables.
    """

    def __init__(self) -> None:
        self.enabled = getattr(settings,"provider_kind","offline") == "ollama" or bool(settings.api_key)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"}

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float | None:
        raw = response.headers.get("Retry-After")
        if not raw:
            return None
        try:
            return max(0.0, float(raw))
        except ValueError:
            try:
                dt = parsedate_to_datetime(raw)
                return max(0.0, dt.timestamp() - time.time())
            except Exception:
                return None

    def _request_with_retry(
        self,
        client: httpx.Client,
        url: str,
        payload: dict,
        *,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> httpx.Response:
        attempts = settings.max_retries + 1
        last_response: httpx.Response | None = None
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                response = client.post(url, headers=self._headers(), json=payload)
                last_response = response
                if response.status_code not in RETRYABLE_STATUS_CODES:
                    return response
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt >= attempts - 1:
                    raise
            else:
                if attempt >= attempts - 1:
                    return response

            retry_after = self._retry_after_seconds(last_response) if last_response is not None else None
            if retry_after is None:
                # Short bounded exponential backoff with light jitter.
                retry_after = settings.retry_base_seconds * (2 ** attempt) + random.uniform(0.0, 0.25)
            sleep_fn(min(retry_after, 8.0))

        if last_response is not None:
            return last_response
        if last_error is not None:
            raise last_error
        raise RuntimeError("Model request failed before a response was produced")

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise RuntimeError("KIVI_LLM_API_KEY (or OPENAI_API_KEY fallback) is not configured")
        if not settings.base_url.startswith(("http://", "https://")):
            raise RuntimeError(
                "KIVI_LLM_BASE_URL must be an absolute http(s) URL, e.g. "
                "https://api.openai.com/v1"
            )

    def chat_json(self, system: str, user: str, schema: dict | None = None, schema_name: str = "response") -> tuple[dict, dict]:
        if settings.provider_kind == "ollama":
            native_schema=_strict_json_schema(schema) if schema else "json"
            if schema_name=="memory_candidates" and schema:
                native_schema=json.loads(json.dumps(schema))
                candidate=native_schema["$defs"]["MemoryCandidate"]
                candidate["properties"]["scope"]={"$ref":"#/$defs/Scope"}
                native_schema["$defs"]["Scope"]["required"]=["app","context","project","recipient"]
                candidate["required"]=list(dict.fromkeys(candidate.get("required",[])+["subject","scope","evidence_text","certainty","temporal_status","entities","cardinality","change_kind"]))
            with httpx.Client(timeout=180) as client:
                r = self._request_with_retry(client, f"{settings.ollama_url}/api/chat", {
                    "model": settings.llm_model, "stream": False, "think": False,
                    "format": native_schema, "options": {"temperature": 0, "num_ctx": 8192},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                })
                r.raise_for_status()
                data = r.json()
            return json.loads(data["message"]["content"]), {
                "model": settings.llm_model, "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0), "duration_ns": data.get("total_duration"), "prompt_eval_duration_ns":data.get("prompt_eval_duration"), "generation_duration_ns":data.get("eval_duration"),
                "cost_usd": 0, "cost_basis": "local inference; electricity/hardware excluded",
            }
        self._require_enabled()
        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": ({
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": _strict_json_schema(schema)},
            } if schema else {"type": "json_object"}),
        }
        with httpx.Client(timeout=90) as client:
            r = self._request_with_retry(client, f"{settings.base_url}/chat/completions", payload)
            # Some compatible providers accept JSON mode but not strict JSON Schema mode.
            # This fallback is deliberately limited to 400 schema-format incompatibility.
            if schema and r.status_code == 400:
                payload["response_format"] = {"type": "json_object"}
                r = self._request_with_retry(client, f"{settings.base_url}/chat/completions", payload)
            r.raise_for_status()
            data = r.json()
        text = data["choices"][0]["message"]["content"]
        return json.loads(text), data.get("usage", {})

    def chat_text(self, system: str, user: str) -> ModelResult:
        self._require_enabled()
        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        with httpx.Client(timeout=90) as client:
            r = self._request_with_retry(client, f"{settings.base_url}/chat/completions", payload)
            r.raise_for_status()
            data = r.json()
        return ModelResult(data["choices"][0]["message"]["content"], data.get("usage", {}))

    def embed(self, texts: list[str]) -> list[list[float]]:
        if settings.provider_kind == "ollama":
            with httpx.Client(timeout=180) as client:
                r = self._request_with_retry(client, f"{settings.ollama_url}/api/embed", {
                    "model": settings.embedding_model, "input": texts, "truncate": False,
                })
                r.raise_for_status()
                return r.json()["embeddings"]
        self._require_enabled()
        payload = {"model": settings.embedding_model, "input": texts}
        with httpx.Client(timeout=90) as client:
            r = self._request_with_retry(client, f"{settings.base_url}/embeddings", payload)
            r.raise_for_status()
            data = r.json()
        return [item["embedding"] for item in data["data"]]


provider = OpenAICompatibleProvider()
