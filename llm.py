"""Appels Mistral (embeddings + chat) avec reprise sur erreur."""
import hashlib
import json
import math
import re
import time

import config

_client = None


def _get_client():
    global _client
    if _client is None:
        if not config.MISTRAL_API_KEY:
            raise RuntimeError(
                "MISTRAL_API_KEY manquante. Exportez-la (export MISTRAL_API_KEY=...) "
                "ou utilisez FAKE_EMBEDDINGS=1 pour tester l'ingestion hors-ligne."
            )
        try:
            from mistralai.client import Mistral  # SDK >= 3.0
        except ImportError:
            from mistralai import Mistral  # SDK 1.x / 2.x

        _client = Mistral(api_key=config.MISTRAL_API_KEY)
    return _client


def _retry(fn, attempts=5):
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            if i == attempts - 1:
                raise
            wait = 2 ** i
            print(f"  ! erreur API ({exc}); nouvel essai dans {wait}s")
            time.sleep(wait)


# --- Embeddings ----------------------------------------------------------------
def _fake_embed(text: str, dim: int = 256) -> list[float]:
    """Sac de mots haché : suffisant pour tester le pipeline sans API."""
    vec = [0.0] * dim
    for tok in re.findall(r"\w+", text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    if config.FAKE_EMBEDDINGS:
        return [_fake_embed(t) for t in texts]
    client = _get_client()
    out: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        res = _retry(
            lambda b=batch: client.embeddings.create(model=config.EMBED_MODEL, inputs=b)
        )
        out.extend(d.embedding for d in res.data)
    return out


# --- Chat ------------------------------------------------------------------------
def chat(system: str, user: str, temperature: float = 0.2) -> str:
    client = _get_client()
    res = _retry(
        lambda: client.chat.complete(
            model=config.CHAT_MODEL,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
    )
    return res.choices[0].message.content


def chat_json(system: str, user: str, temperature: float = 0.1) -> dict:
    client = _get_client()
    res = _retry(
        lambda: client.chat.complete(
            model=config.CHAT_MODEL,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
    )
    return json.loads(res.choices[0].message.content)
