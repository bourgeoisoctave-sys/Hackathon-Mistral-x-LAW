"""Grille, calcul du score (pur), détection type/clauses (LLM mocké), pipeline.prepare."""
import json

import pytest

import analyze
import llm
import pipeline
import scoring
from conftest import make_pdf

GRILLE = scoring.load_grille()
AGO = GRILLE["types_operation"]["AGO_annuelle"]["clauses"]


def _checks(**etats):
    """Toutes les clauses 'presente' sauf celles passées en argument."""
    return [{"id": c["id"], "etat": etats.get(c["id"], "presente"), "extrait": "", "commentaire": ""} for c in AGO]


# --- grille ---------------------------------------------------------------------------
def test_grille_is_well_formed():
    assert GRILLE["type_par_defaut"] in GRILLE["types_operation"]
    assert set(GRILLE["exigences"]) == {"standard", "max"}
    for tid, t in GRILLE["types_operation"].items():
        ids = [c["id"] for c in t["clauses"]]
        assert len(ids) == len(set(ids)), f"ids dupliqués dans {tid}"
        assert 10 <= len(ids) <= 15, f"{tid} : {len(ids)} clauses (attendu 10-15)"
        for c in t["clauses"]:
            assert c["poids"] > 0 and isinstance(c["cle"], bool) and c["pourquoi"] and c["libelle"]
        assert any(c["cle"] for c in t["clauses"])


# --- compute_score ----------------------------------------------------------------------
def test_score_all_present_is_100():
    s = scoring.compute_score(_checks(), AGO, "standard", GRILLE)
    assert s == {"brut": 100, "malus_cles": 0, "final": 100, "cles_manquantes": [], "exigence": "standard"}


def test_missing_key_clause_costs_weight_and_minus_10():
    s = scoring.compute_score(_checks(quorum_feuille_presence="absente"), AGO, "standard", GRILLE)
    total = sum(c["poids"] for c in AGO)
    assert s["brut"] == round(100 * (total - 10) / total)
    assert s["malus_cles"] == -10 and s["cles_manquantes"] == ["quorum_feuille_presence"]
    assert s["final"] == s["brut"] - 10


def test_missing_non_key_clause_has_no_malus():
    s = scoring.compute_score(_checks(quitus="absente"), AGO, "standard", GRILLE)
    assert s["malus_cles"] == 0 and s["brut"] < 100


def test_partial_counts_half_in_standard_and_zero_in_max():
    std = scoring.compute_score(_checks(convocation="partielle"), AGO, "standard", GRILLE)
    mx = scoring.compute_score(_checks(convocation="partielle"), AGO, "max", GRILLE)
    assert std["malus_cles"] == 0 and mx["malus_cles"] == -10  # clé partielle pénalisée en max
    assert std["brut"] > mx["brut"]


def test_score_never_below_zero():
    s = scoring.compute_score(_checks(**{c["id"]: "absente" for c in AGO}), AGO, "max", GRILLE)
    assert s["final"] == 0 and s["brut"] == 0
    assert len(s["cles_manquantes"]) == sum(c["cle"] for c in AGO)


def test_unknown_clause_in_checks_is_treated_absent():
    s = scoring.compute_score([], AGO, "standard", GRILLE)
    assert s["brut"] == 0


# --- normalisation des réponses LLM ---------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [("Présente", "presente"), ("PARTIELLE", "partielle"), ("absente", "absente"), ("bizarre", "absente"), (None, "absente")])
def test_normalise_etat(raw, expected):
    assert scoring._normalise_etat(raw) == expected


def test_check_clauses_fills_missing_ids_as_absent(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda s, u, temperature=0.1: {"clauses": [{"id": "quorum_feuille_presence", "etat": "Présente", "extrait": "Le quorum…"}]})
    out = scoring.check_clauses("texte", AGO)
    assert [c["id"] for c in out] == [c["id"] for c in AGO]
    by = {c["id"]: c for c in out}
    assert by["quorum_feuille_presence"]["etat"] == "presente" and by["quorum_feuille_presence"]["extrait"] == "Le quorum…"
    assert by["convocation"]["etat"] == "absente"


def test_detect_type_valid_and_fallback(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda s, u, temperature=0.1: {"type_operation": "AGE_levee_de_fonds", "justification": "augmentation de capital"})
    t = scoring.detect_type("pv", GRILLE)
    assert t == {"type_operation": "AGE_levee_de_fonds", "justification": "augmentation de capital", "detecte": True}
    monkeypatch.setattr(llm, "chat_json", lambda s, u, temperature=0.1: {"type_operation": "inconnu"})
    t = scoring.detect_type("pv", GRILLE)
    assert t["type_operation"] == GRILLE["type_par_defaut"] and t["detecte"] is False


# --- pipeline.prepare ---------------------------------------------------------------------------
def _mock_llm(monkeypatch):
    def chat_json(system, user, temperature=0.1):
        if system == scoring.SYSTEM_TYPE:
            return {"type_operation": "AGO_annuelle", "justification": "comptes annuels"}
        if system == scoring.SYSTEM_CLAUSES:
            return {"clauses": [{"id": c["id"], "etat": "presente", "extrait": "x"} for c in AGO if c["id"] != "resultat_votes_detaille"]}
        if system == analyze.SYSTEM_DECOMPOSE:
            return {"sections": [{"titre": "Quorum", "extrait": "Le quorum est atteint.", "requetes": ["quorum constate debut de seance"]}]}
        raise AssertionError(f"appel LLM inattendu : {system[:40]}")
    monkeypatch.setattr(llm, "chat_json", chat_json)


def test_prepare_writes_context(indexed, tmp_path, monkeypatch):
    _mock_llm(monkeypatch)
    pv = make_pdf(tmp_path / "pv.pdf", ["PV d'AG. Le quorum est atteint."])
    ctx = pipeline.prepare(pv, exigence="max")

    assert ctx["type_operation"] == "AGO_annuelle" and ctx["type_detecte"] is True
    assert ctx["score"]["cles_manquantes"] == ["resultat_votes_detaille"] and ctx["score"]["malus_cles"] == -10
    assert ctx["clauses_attendues"] == AGO
    assert ctx["sections"][0]["passages"][0]["source"] == "guides_internes/guide.pdf"
    assert set(ctx["sections"][0]["passages"][0]) == {"text", "source", "page", "distance"}

    saved = json.loads((tmp_path / "pv.context.json").read_text(encoding="utf-8"))
    assert saved["score"] == ctx["score"] and saved["pv"] == "pv.pdf"


def test_prepare_without_corpus_gives_empty_passages(tmp_path, monkeypatch):
    _mock_llm(monkeypatch)
    pv = make_pdf(tmp_path / "pv.pdf", ["Texte."])
    ctx = pipeline.prepare(pv, out=tmp_path / "ctx.json")
    assert ctx["sections"][0]["passages"] == []
    assert (tmp_path / "ctx.json").exists()


def test_prepare_rejects_unknown_exigence(tmp_path):
    with pytest.raises(ValueError, match="exigence"):
        pipeline.prepare(tmp_path / "pv.pdf", exigence="ultra")
