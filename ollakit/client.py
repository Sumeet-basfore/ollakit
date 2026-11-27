"""Shared Ollama client: availability check, model selection, chat, embed."""

import json

from ollama import Client

from . import config

_client = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = Client()
    try:
        _client.list()
    except Exception as e:
        raise SystemExit(
            f"Cannot reach Ollama at localhost:11434 ({e}). Is `ollama serve` running?"
        )
    return _client


def installed_models() -> list[str]:
    client = get_client()
    return [m.model for m in client.list().models]


def pick_chat_model(explicit: str | None) -> str:
    if explicit:
        cfg = config.load()
        if cfg["chat_model"] != explicit:
            cfg["chat_model"] = explicit
            config.save(cfg)  # remember the operator's choice
        return explicit
    cfg = config.load()
    if cfg["chat_model"]:
        return cfg["chat_model"]
    models = _models_with_size()
    if not models:
        raise SystemExit("No Ollama models installed. Try: ollama pull qwen3:4b")
    local = [(name, size) for name, size in models if ":cloud" not in name]
    if not local:
        local = models
    # Measured on this setup: qwen-family gives the fewest review false
    # positives; prefer it, then the largest local model.
    qwen = [(n, s) for n, s in local if n.lower().startswith("qwen")]
    coder = [(n, s) for n, s in local if "coder" in n.lower() or "code" in n.lower()]
    pool = coder or qwen or local
    model = max(pool, key=lambda pair: pair[1])[0]
    cfg["chat_model"] = model
    config.save(cfg)
    print(f"[ollakit] selected chat model: {model} (set --model to override)")
    return model


def _models_with_size() -> list[tuple[str, int]]:
    client = get_client()
    return [(m.model, m.size or 0) for m in client.list().models]


def pick_embed_model(explicit: str | None) -> str:
    if explicit:
        return explicit
    cfg = config.load()
    if cfg["embed_model"] and cfg["embed_model"] in installed_models():
        return cfg["embed_model"]
    models = installed_models()
    embeds = [m for m in models if "embed" in m.lower() or "bge" in m.lower() or "minilm" in m.lower()]
    if not embeds:
        raise SystemExit(
            "No embedding model installed. Run:\n  ollama pull nomic-embed-text\n"
            "then retry (embeddings never leave your machine)."
        )
    cfg["embed_model"] = embeds[0]
    config.save(cfg)
    return embeds[0]


def chat(model: str, messages: list[dict], json_mode: bool = False) -> str:
    client = get_client()
    kwargs = {"model": model, "messages": messages, "think": False}
    if json_mode:
        kwargs["format"] = "json"
    response = client.chat(**kwargs)
    return response.message.content


def embed(model: str, texts: list[str]) -> list[list[float]]:
    client = get_client()
    response = client.embed(model=model, input=texts)
    return response["embeddings"]


def parse_json(raw: str):
    """Parse model output as JSON, tolerating fences or stray prose."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("[") if "[" in raw else raw.find("{")
        end = max(raw.rfind("]"), raw.rfind("}"))
        if start != -1 and end > start:
            return json.loads(raw[start : end + 1])
        raise
