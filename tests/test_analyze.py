"""Analyse d'un PV : lecture, analyse de section (LLM mocké), rapport, pipeline complet."""
import json
import sys

import pytest

import analyze
import llm
from conftest import make_pdf

PASSAGES = [
    {"text": "Le quorum doit etre constate.", "meta": {"source": "guides_internes/guide.pdf", "page": 1, "categorie": "guides_internes"}, "distance": 0.1},
    {"text": "Chaque resolution indique les voix.", "meta": {"source": "guides_internes/guide.pdf", "page": 2, "categorie": "guides_internes"}, "distance": 0.3},
]


# --- read_pdf -----------------------------------------------------------------------
def test_read_pdf_concatenates_pages(tmp_path):
    pdf = make_pdf(tmp_path / "pv.pdf", ["Page A.", "Page B."])
    text = analyze.read_pdf(pdf)
    assert "Page A." in text and "Page B." in text


def test_read_pdf_scan_exits(tmp_path):
    with pytest.raises(SystemExit, match="scanné"):
        analyze.read_pdf(make_pdf(tmp_path / "scan.pdf", ["", ""]))


# --- analyze_section --------------------------------------------------------------------
def test_analyze_section_numbers_passages_for_llm(monkeypatch):
    seen = {}

    def fake_chat_json(system, user, temperature=0.1):
        seen["system"], seen["user"] = system, user
        return {"statut": "conforme", "couverture": "bonne", "constats": [], "recommandations": []}

    monkeypatch.setattr(llm, "chat_json", fake_chat_json)
    section = {"titre": "Quorum", "extrait": "Le quorum est atteint.", "requetes": []}
    res = analyze.analyze_section(section, PASSAGES)

    assert seen["system"] == analyze.SYSTEM_SECTION
    assert "SECTION DU PV : Quorum" in seen["user"]
    assert "[1] (guides_internes/guide.pdf, p.1)\nLe quorum doit etre constate." in seen["user"]
    assert "[2] (guides_internes/guide.pdf, p.2)" in seen["user"]
    assert res["_passages"] is PASSAGES  # conservé pour la résolution des citations


def test_analyze_section_without_passages(monkeypatch):
    seen = {}
    monkeypatch.setattr(llm, "chat_json", lambda s, u, temperature=0.1: seen.update(user=u) or {"couverture": "aucune"})
    analyze.analyze_section({"titre": "X", "extrait": "..."}, [])
    assert "(aucun passage pertinent trouvé dans la base)" in seen["user"]


# --- build_report --------------------------------------------------------------------------
def test_build_report_maps_citations_and_ignores_bad_indexes():
    section = {"titre": "Votes", "extrait": "..."}
    result = {
        "statut": "a_ameliorer",
        "couverture": "partielle",
        "constats": ["Le décompte des voix manque."],
        "recommandations": [
            {"action": "Indiquer pour/contre/abstentions.", "justification": "Règle interne.", "sources": [2, 1]},
            {"action": "Sans source valide.", "justification": "…", "sources": [0, 99, "x"]},
        ],
        "reformulation_proposee": "La résolution est adoptée par 10 voix pour, 2 contre.",
        "_passages": PASSAGES,
    }
    md = analyze.build_report("pv.pdf", "Synthèse ici.", [(section, result)])

    assert md.startswith("# Analyse du PV d'AG — pv.pdf")
    assert "Synthèse ici." in md
    assert "| Votes | À améliorer | partielle |" in md  # STATUT_LABEL appliqué
    assert "- Le décompte des voix manque." in md
    assert "Sources : guides_internes/guide.pdf, p.2 ; guides_internes/guide.pdf, p.1" in md
    # Recommandation 2 : indexes invalides → pas de ligne "Sources".
    rec2 = md.split("**Recommandation 2.**")[1].split("**Reformulation")[0]
    assert "Sources" not in rec2
    assert "> La résolution est adoptée par 10 voix pour, 2 contre." in md
    assert md.rstrip().endswith("à valider par le service juridique.*")


def test_build_report_unknown_status_is_kept_verbatim():
    md = analyze.build_report("x.pdf", "s", [({"titre": "T", "extrait": ""}, {"statut": "bizarre", "_passages": []})])
    assert "| T | bizarre |" in md


# --- pipeline complet (LLM mocké, retrieval réel hors-ligne) --------------------------------
SECTIONS = [
    {"titre": "Quorum", "extrait": "Le quorum est atteint.", "requetes": ["quorum constate debut de seance"]},
    {"titre": "Votes", "extrait": "La résolution est adoptée.", "requetes": ["resolution nombre de voix pour contre abstentions"]},
]


def _mock_llm(monkeypatch, calls):
    def chat_json(system, user, temperature=0.1):
        calls.append(("json", system, user))
        if system == analyze.SYSTEM_DECOMPOSE:
            return {"sections": SECTIONS}
        return {
            "statut": "a_ameliorer", "couverture": "bonne",
            "constats": ["Constat."],
            "recommandations": [{"action": "Agir.", "justification": "Parce que.", "sources": [1]}],
            "reformulation_proposee": "",
        }

    def chat(system, user, temperature=0.2):
        calls.append(("text", system, user))
        return "Synthèse factice."

    monkeypatch.setattr(llm, "chat_json", chat_json)
    monkeypatch.setattr(llm, "chat", chat)


def test_main_end_to_end(indexed, tmp_path, monkeypatch, capsys):
    pv = make_pdf(tmp_path / "pv.pdf", ["PV d'AG. Le quorum est atteint. La resolution est adoptee."])
    out = tmp_path / "rapport.md"
    calls = []
    _mock_llm(monkeypatch, calls)
    monkeypatch.setattr(sys, "argv", ["analyze.py", str(pv), "-o", str(out), "--json"])

    analyze.main()

    md = out.read_text(encoding="utf-8")
    assert "## Quorum" in md and "## Votes" in md
    # Le guide est un document court : une seule unité, citée par les deux sections.
    assert md.count("Sources : guides_internes/guide.pdf, p.1") == 2
    assert "Synthèse factice." in md
    # 1 décomposition + 1 analyse par section + 1 synthèse.
    kinds = [c[0] for c in calls]
    assert kinds == ["json", "json", "json", "text"]
    assert "PV d'AG." in calls[0][2]  # le PV complet part à la décomposition

    raw = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert [r["section"]["titre"] for r in raw] == ["Quorum", "Votes"]
    assert "_passages" not in raw[0]["analyse"]
    assert "Rapport écrit" in capsys.readouterr().out


def test_main_default_output_path(indexed, tmp_path, monkeypatch):
    pv = make_pdf(tmp_path / "mon_pv.pdf", ["Texte."])
    _mock_llm(monkeypatch, [])
    monkeypatch.setattr(sys, "argv", ["analyze.py", str(pv)])
    analyze.main()
    assert (tmp_path / "mon_pv.analyse.md").exists()


def test_main_empty_db_exits(tmp_path, monkeypatch):
    pv = make_pdf(tmp_path / "pv.pdf", ["Texte."])
    monkeypatch.setattr(sys, "argv", ["analyze.py", str(pv)])
    with pytest.raises(SystemExit, match="Base vide"):
        analyze.main()


def test_main_no_sections_exits(indexed, tmp_path, monkeypatch):
    pv = make_pdf(tmp_path / "pv.pdf", ["Texte."])
    monkeypatch.setattr(llm, "chat_json", lambda s, u, temperature=0.1: {"sections": []})
    monkeypatch.setattr(sys, "argv", ["analyze.py", str(pv)])
    with pytest.raises(SystemExit, match="aucune section"):
        analyze.main()
