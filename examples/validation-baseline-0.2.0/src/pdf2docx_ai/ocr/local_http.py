"""Hardened loopback transport for user-managed local inference servers."""
from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit, urlunsplit

import httpx

from .base import OCRUnavailableError


def local_base_url(url: str) -> str:
    parts = urlsplit(url)
    try:
        is_local = ipaddress.ip_address(parts.hostname or "").is_loopback
        port = parts.port
    except ValueError:
        is_local = False
        port = None
    if (parts.scheme != "http" or not is_local or parts.username or parts.password
            or parts.query or parts.fragment or parts.path.rstrip("/") not in {"", "/v1", "/api"}):
        raise ValueError("OCR URL must be a numeric loopback HTTP URL, e.g. http://127.0.0.1:11434/v1")
    netloc = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    if port:
        netloc += f":{port}"
    return urlunsplit(("http", netloc, "", "", ""))


class LocalHTTP:
    def __init__(self, url: str, timeout: float = 180):
        self.base_url = local_base_url(url)
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def client(self):
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout, follow_redirects=False, trust_env=False)
        return self._client

    def json(self, method: str, path: str, payload: dict | None = None, timeout: float | None = None) -> dict:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Invalid local inference path")
        try:
            response = self.client.request(method, self.base_url + path, json=payload,
                                           timeout=timeout or self.timeout)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Inference response must be a JSON object")
            if data.get("error"):
                raise OCRUnavailableError(str(data["error"])[:500])
            return data
        except (httpx.HTTPError, ValueError) as exc:
            raise OCRUnavailableError(f"Local inference at {self.base_url} failed: {exc}") from exc

    def close(self):
        if self._client:
            self._client.close()
            self._client = None


def normalize_tag(name: str) -> str:
    return name.removesuffix(":latest")


def probe_model(transport: LocalHTTP, model: str) -> dict:
    """Prefer Ollama tags, then the OpenAI model list; never pull a missing model."""
    errors = []
    for path, key, id_key, runtime in (("/api/tags", "models", "name", "ollama"),
                                       ("/v1/models", "data", "id", "openai")):
        try:
            data = transport.json("GET", path, timeout=min(transport.timeout, 2))
            models = [str(item.get(id_key, "")) for item in data.get(key, [])]
            available = normalize_tag(model) in {normalize_tag(m) for m in models}
            return {"available": available, "runtime": runtime, "model": model,
                    "models": models, "endpoint": transport.base_url,
                    "code": "ready" if available else "model_missing",
                    "reason": None if available else f"Server raggiungibile, ma il modello '{model}' non è installato su {transport.base_url}."}
        except OCRUnavailableError as exc:
            errors.append(str(exc))
    return {"available": False, "model": model, "endpoint": transport.base_url,
            "code": "server_unreachable",
            "reason": f"Nessun server OCR compatibile raggiungibile su {transport.base_url}. Avvia il server locale con il modello '{model}' oppure scegli Apple Vision/Automatico.",
            "diagnostics": list(dict.fromkeys(errors))}

