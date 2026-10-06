"""Couche Mistral : embeddings factices, reprise sur erreur, et un test réel optionnel."""
import math

import pytest

import config
import llm


# --- embeddings factices ----------------------------------------------------------
def test_fake_embed_is_unit_norm_and_deterministic():
    a = llm._fake_embed("Le quorum est constaté.")
    b = llm._fake_embed("Le quorum est constaté.")
    assert a == b and len(a) == 256
    assert math.isclose(math.sqrt(sum(x * x for x in a)), 1.0, rel_tol=1e-9)


def test_fake_embed_empty_text_is_zero_vector():
    assert all(x == 0.0 for x in llm._fake_embed(""))


def test_embed_offline_returns_one_vector_per_text():
    out = llm.embed(["a", "b", "c"])
    assert len(out) == 3 and all(len(v) == 256 for v in out)


# --- reprise sur erreur -----------------------------------------------------------
def test_retry_backs_off_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return "ok"

    assert llm._retry(flaky, attempts=5) == "ok"
    assert calls["n"] == 3
    assert sleeps == [1, 2]  # 2**0, 2**1


def test_retry_gives_up_after_attempts(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)

    def always_fails():
        raise ValueError("non")

    with pytest.raises(ValueError):
        llm._retry(always_fails, attempts=3)
    assert sleeps == [1, 2]


def test_client_requires_api_key(monkeypatch):
    monkeypatch.setattr(config, "MISTRAL_API_KEY", "")
    monkeypatch.setattr(llm, "_client", None)
    with pytest.raises(RuntimeError, match="MISTRAL_API_KEY"):
        llm._get_client()


# --- API réelle (opt-in : pytest -m real_api) --------------------------------------
@pytest.mark.real_api
@pytest.mark.skipif(not config.MISTRAL_API_KEY, reason="MISTRAL_API_KEY absente")
def test_real_api_embed_and_chat_json(monkeypatch):
    monkeypatch.setattr(config, "FAKE_EMBEDDINGS", False)
    vecs = llm.embed(["Le quorum est constaté.", "Résultat des votes."])
    assert len(vecs) == 2 and len(vecs[0]) == 1024
    out = llm.chat_json("Réponds uniquement en JSON.", 'Renvoie exactement {"ok": true}.')
    assert isinstance(out, dict) and out
