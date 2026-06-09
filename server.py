#!/usr/bin/env python3
"""Zero-dependency local API wrapper for Ollama."""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_CHAT_MODEL = os.getenv("DEFAULT_CHAT_MODEL", "gemma4:e4b")
DEFAULT_EMBED_MODEL = os.getenv("DEFAULT_EMBED_MODEL", "bge-m3:latest")
REQUEST_TIMEOUT = float(os.getenv("OLLAMA_REQUEST_TIMEOUT", "600"))
CORS_ORIGIN = os.getenv("CORS_ORIGIN", "*")
URL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def json_dumps(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def ollama_request(path: str, payload: Any | None = None, method: str = "POST") -> Any:
    data = json_dumps(payload) if payload is not None else None
    request = urllib.request.Request(
        f"{OLLAMA_HOST}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )

    try:
        with URL_OPENER.open(request, timeout=REQUEST_TIMEOUT) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot connect to Ollama at {OLLAMA_HOST}: {exc.reason}") from exc

    if not body:
        return {}

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama returned invalid JSON: {body[:500]}") from exc


def ollama_stream(path: str, payload: Any):
    request = urllib.request.Request(
        f"{OLLAMA_HOST}{path}",
        data=json_dumps(payload),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return URL_OPENER.open(request, timeout=REQUEST_TIMEOUT)


def normalize_messages(messages: Any) -> list[dict[str, Any]]:
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty list")

    normalized: list[dict[str, Any]] = []
    for item in messages:
        if not isinstance(item, dict):
            raise ValueError("each message must be an object")
        role = item.get("role")
        content = item.get("content")
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("message.role must be one of system, user, assistant, tool")
        if content is None:
            raise ValueError("message.content is required")
        normalized.append(dict(item))
    return normalized


def usage_from_ollama(payload: dict[str, Any]) -> dict[str, int]:
    prompt_tokens = int(payload.get("prompt_eval_count") or 0)
    completion_tokens = int(payload.get("eval_count") or 0)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def openai_model_list(tags: dict[str, Any]) -> dict[str, Any]:
    data = []
    for model in tags.get("models", []):
        data.append(
            {
                "id": model.get("name") or model.get("model"),
                "object": "model",
                "created": int(time.time()),
                "owned_by": "ollama",
            }
        )
    return {"object": "list", "data": data}


def openai_chat_payload(body: dict[str, Any], stream: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": body.get("model") or DEFAULT_CHAT_MODEL,
        "messages": normalize_messages(body.get("messages")),
        "stream": stream,
    }
    for key in ("format", "options", "keep_alive", "tools"):
        if key in body:
            payload[key] = body[key]
    return payload


def openai_chat_response(ollama_payload: dict[str, Any], model: str) -> dict[str, Any]:
    message = ollama_payload.get("message") or {}
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": message.get("role", "assistant"),
                    "content": message.get("content", ""),
                },
                "finish_reason": ollama_payload.get("done_reason") or "stop",
            }
        ],
        "usage": usage_from_ollama(ollama_payload),
    }


def openai_embedding_response(ollama_payload: dict[str, Any], model: str) -> dict[str, Any]:
    embeddings = ollama_payload.get("embeddings")
    if embeddings is None and "embedding" in ollama_payload:
        embeddings = [ollama_payload["embedding"]]
    if embeddings is None:
        embeddings = []

    prompt_tokens = int(ollama_payload.get("prompt_eval_count") or 0)
    return {
        "object": "list",
        "model": model,
        "data": [
            {"object": "embedding", "index": index, "embedding": embedding}
            for index, embedding in enumerate(embeddings)
        ],
        "usage": {"prompt_tokens": prompt_tokens, "total_tokens": prompt_tokens},
    }


class OllamaApiHandler(BaseHTTPRequestHandler):
    server_version = "LocalOllamaAPI/1.0"

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path == "/":
                self.send_json(
                    {
                        "name": "local-ollama-api",
                        "ollama_host": OLLAMA_HOST,
                        "defaults": {
                            "chat_model": DEFAULT_CHAT_MODEL,
                            "embedding_model": DEFAULT_EMBED_MODEL,
                        },
                        "endpoints": [
                            "GET /health",
                            "GET /models",
                            "POST /chat",
                            "POST /generate",
                            "POST /embeddings",
                            "GET /v1/models",
                            "POST /v1/chat/completions",
                            "POST /v1/embeddings",
                        ],
                    }
                )
                return

            if path == "/health":
                tags = ollama_request("/api/tags", method="GET")
                self.send_json(
                    {
                        "status": "ok",
                        "ollama_host": OLLAMA_HOST,
                        "model_count": len(tags.get("models", [])),
                    }
                )
                return

            if path == "/models":
                tags = ollama_request("/api/tags", method="GET")
                self.send_json(
                    {
                        "object": "list",
                        "defaults": {
                            "chat_model": DEFAULT_CHAT_MODEL,
                            "embedding_model": DEFAULT_EMBED_MODEL,
                        },
                        "data": tags.get("models", []),
                    }
                )
                return

            if path == "/v1/models":
                self.send_json(openai_model_list(ollama_request("/api/tags", method="GET")))
                return

            self.send_error_json(404, "not_found", f"Unknown endpoint: {path}")
        except Exception as exc:  # noqa: BLE001
            self.send_error_json(502, "ollama_error", str(exc))

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            body = self.read_json()

            if path == "/chat":
                payload = openai_chat_payload(body, stream=False)
                ollama_payload = ollama_request("/api/chat", payload)
                message = ollama_payload.get("message") or {}
                self.send_json(
                    {
                        "model": payload["model"],
                        "role": message.get("role", "assistant"),
                        "content": message.get("content", ""),
                        "finish_reason": ollama_payload.get("done_reason") or "stop",
                        "usage": usage_from_ollama(ollama_payload),
                    }
                )
                return

            if path == "/generate":
                model = body.get("model") or DEFAULT_CHAT_MODEL
                prompt = body.get("prompt")
                if not isinstance(prompt, str) or not prompt:
                    raise ValueError("prompt must be a non-empty string")
                payload = {"model": model, "prompt": prompt, "stream": bool(body.get("stream", False))}
                for key in ("system", "template", "context", "format", "options", "keep_alive", "suffix", "images"):
                    if key in body:
                        payload[key] = body[key]
                if payload["stream"]:
                    self.proxy_ndjson_stream("/api/generate", payload)
                    return
                self.send_json(ollama_request("/api/generate", payload))
                return

            if path == "/embeddings":
                self.handle_embeddings(body)
                return

            if path == "/v1/chat/completions":
                if bool(body.get("stream", False)):
                    self.handle_openai_chat_stream(body)
                    return
                payload = openai_chat_payload(body, stream=False)
                self.send_json(openai_chat_response(ollama_request("/api/chat", payload), payload["model"]))
                return

            if path == "/v1/embeddings":
                self.handle_embeddings(body)
                return

            if path == "/ollama/chat":
                payload = dict(body)
                payload.setdefault("model", DEFAULT_CHAT_MODEL)
                if bool(payload.get("stream", False)):
                    self.proxy_ndjson_stream("/api/chat", payload)
                    return
                self.send_json(ollama_request("/api/chat", payload))
                return

            if path == "/ollama/generate":
                payload = dict(body)
                payload.setdefault("model", DEFAULT_CHAT_MODEL)
                if bool(payload.get("stream", False)):
                    self.proxy_ndjson_stream("/api/generate", payload)
                    return
                self.send_json(ollama_request("/api/generate", payload))
                return

            self.send_error_json(404, "not_found", f"Unknown endpoint: {path}")
        except ValueError as exc:
            self.send_error_json(400, "bad_request", str(exc))
        except Exception as exc:  # noqa: BLE001
            self.send_error_json(502, "ollama_error", str(exc))

    def handle_embeddings(self, body: dict[str, Any]) -> None:
        model = body.get("model") or DEFAULT_EMBED_MODEL
        input_value = body.get("input")
        if input_value is None:
            input_value = body.get("prompt")
        if not isinstance(input_value, (str, list)):
            raise ValueError("input must be a string or a list of strings")

        payload: dict[str, Any] = {"model": model, "input": input_value}
        for key in ("truncate", "options", "keep_alive"):
            if key in body:
                payload[key] = body[key]
        self.send_json(openai_embedding_response(ollama_request("/api/embed", payload), model))

    def handle_openai_chat_stream(self, body: dict[str, Any]) -> None:
        payload = openai_chat_payload(body, stream=True)
        stream_id = f"chatcmpl-{uuid.uuid4().hex}"
        created = int(time.time())

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        with ollama_stream("/api/chat", payload) as response:
            sent_role = False
            for raw_line in response:
                if not raw_line.strip():
                    continue
                chunk = json.loads(raw_line.decode("utf-8"))
                message = chunk.get("message") or {}
                content = message.get("content") or ""

                if content or not sent_role:
                    delta: dict[str, str] = {}
                    if not sent_role:
                        delta["role"] = "assistant"
                        sent_role = True
                    if content:
                        delta["content"] = content
                    self.write_sse(
                        {
                            "id": stream_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": payload["model"],
                            "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                        }
                    )

                if chunk.get("done"):
                    self.write_sse(
                        {
                            "id": stream_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": payload["model"],
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {},
                                    "finish_reason": chunk.get("done_reason") or "stop",
                                }
                            ],
                        }
                    )
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                    break

    def proxy_ndjson_stream(self, path: str, payload: dict[str, Any]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        with ollama_stream(path, payload) as response:
            for raw_line in response:
                self.wfile.write(raw_line)
                self.wfile.flush()

    def write_sse(self, payload: dict[str, Any]) -> None:
        self.wfile.write(b"data: ")
        self.wfile.write(json_dumps(payload))
        self.wfile.write(b"\n\n")
        self.wfile.flush()

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw_body = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json_dumps(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: int, code: str, message: str) -> None:
        self.send_json({"error": {"code": code, "message": message}}, status=status)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local API wrapper for Ollama.")
    parser.add_argument("--host", default=os.getenv("API_HOST", "127.0.0.1"))
    parser.add_argument("--port", default=int(os.getenv("API_PORT", "8000")), type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), OllamaApiHandler)
    print(f"Local Ollama API: http://{args.host}:{args.port}")
    print(f"Ollama upstream:  {OLLAMA_HOST}")
    print(f"Chat model:       {DEFAULT_CHAT_MODEL}")
    print(f"Embedding model:  {DEFAULT_EMBED_MODEL}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
