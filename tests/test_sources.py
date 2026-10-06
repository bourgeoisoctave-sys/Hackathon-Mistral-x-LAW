"""Normalisation de format (sources.py) : eml, txt, pdf, nettoyage et préfixe de citation."""
from pathlib import Path

import ingest
import pipeline
import sources
from conftest import make_pdf

EML = b"""From: Me Claire Dupont <c.dupont@ex.fr>
To: stagiaire@ex.fr
Date: Mon, 14 Sep 2026 09:12:00 +0200
Subject: Suppression du DPS
Content-Type: text/plain; charset="utf-8"

Il faut la suppression du DPS au profit d'Alpha.

> Le 11 sept., Marc a ecrit :
> Les historiques peuvent-ils souscrire ?
"""


def test_load_eml(tmp_path):
    root = tmp_path / "d"
    f = root / "mails" / "a.eml"
    f.parent.mkdir(parents=True)
    f.write_bytes(EML)
    [doc] = sources.load(f, root, dossier="novatech")
    m = doc["meta"]
    assert m["source_type"] == "mail" and m["dossier"] == "novatech" and m["categorie"] == "mails"
    assert m["date"] == "2026-09-14" and "Dupont" in m["auteur"] and m["titre"] == "Suppression du DPS"
    assert doc["text"].startswith("Objet : Suppression du DPS") and "au profit d'Alpha" in doc["text"]
    assert all(isinstance(v, (str, int, float, bool)) for v in m.values())  # contrainte Chroma


def test_load_transcript_and_note(tmp_path):
    root = tmp_path / "d"
    (root / "reunions").mkdir(parents=True)
    t = root / "reunions" / "2026-09-11_call_alpha.txt"
    t.write_text("Sophie : il nous faut le DPS supprime.", encoding="utf-8")
    n = root / "memo.md"
    n.write_text("Memo interne.", encoding="utf-8")
    [doc] = sources.load(t, root)
    assert doc["meta"]["source_type"] == "reunion" and doc["meta"]["date"] == "2026-09-11"
    [doc] = sources.load(n, root)
    assert doc["meta"]["source_type"] == "note" and doc["meta"]["date"] == "" and doc["meta"]["categorie"] == "general"


def test_load_pdf_one_doc_per_page(tmp_path):
    pdf = make_pdf(tmp_path / "g.pdf", ["Page un.", "", "Page trois."])
    docs = sources.load(pdf, tmp_path)
    assert [d["meta"]["page"] for d in docs] == [1, 3]
    assert all(d["meta"]["source_type"] == "document" for d in docs)


def test_unknown_extension_and_empty_file(tmp_path):
    (tmp_path / "x.pptx").write_text("x")
    (tmp_path / "vide.txt").write_text("   ")
    assert sources.load(tmp_path / "x.pptx", tmp_path) == []
    assert sources.load(tmp_path / "vide.txt", tmp_path) == []
    assert sources.iter_files(tmp_path) == [tmp_path / "vide.txt"]


def test_clean_chunk_removes_quotes_and_fillers():
    raw = "Il faut, euh, le DPS supprimé.\n> ancien mail cité\nHum, d'accord."
    assert sources.clean_chunk(raw) == "Il faut, le DPS supprimé.\nd'accord."
    assert sources.clean_chunk("> tout cité\n> encore") == ""


def test_label_by_source_type():
    base = {"page": 2, "titre": "guide", "date": "", "auteur": ""}
    assert sources.label({**base, "source_type": "document"}) == "guide (p.2)"
    assert sources.label({**base, "source_type": "mail", "auteur": "Me X", "date": "2026-09-14", "titre": "DPS"}) == "Mail de Me X, 2026-09-14 — DPS"
    assert sources.label({**base, "source_type": "reunion", "date": "2026-09-11", "titre": "call"}) == "Réunion 2026-09-11 — call"


# --- ingestion d'un dossier mixte + contexte oral par clause -------------------------------
def test_ingest_dossier_and_contexte_dossier(tmp_path):
    root = tmp_path / "dossier"
    (root / "mails").mkdir(parents=True)
    (root / "reunions").mkdir()
    (root / "mails" / "a.eml").write_bytes(EML)
    (root / "reunions" / "2026-09-11_call.txt").write_text(
        "Sophie Martin : suppression du droit preferentiel de souscription au profit d'Alpha Capital, beneficiaire denomme.", encoding="utf-8")
    make_pdf(root / "guide.pdf", ["Le quorum doit etre constate."])
    ingest.ingest(root, dossier="novatech")
    col = ingest.get_collection()
    types = {m["source_type"] for m in col.get(include=["metadatas"])["metadatas"]}
    assert types == {"mail", "reunion", "document"}
    # Les lignes citées « > » ne sont pas stockées.
    assert not any(">" in d for d in col.get(include=["documents"])["documents"])

    clauses = [{"id": "suppression_dps", "libelle": "Suppression du droit preferentiel de souscription au profit de beneficiaires denommes"},
               {"id": "quorum", "libelle": "Quorum constate"}]
    oral = pipeline.contexte_dossier(col, clauses, "novatech")
    assert set(oral) == {"suppression_dps", "quorum"}
    assert oral["suppression_dps"], "aucune trace orale trouvée pour le DPS"
    assert {p["source_type"] for p in oral["suppression_dps"]} <= {"mail", "reunion", "note"}  # jamais le guide PDF
    assert oral["suppression_dps"][0]["citation"].startswith(("Réunion 2026-09-11", "Mail de"))
    # Un autre dossier ne voit rien.
    assert all(v == [] for v in pipeline.contexte_dossier(col, clauses, "autre").values())


# --- .docx : modèle, PV de formation (bandeau retiré), fil d'emails ---------------------------
def _docx(path: Path, paragraphs: list[str]) -> Path:
    import docx
    d = docx.Document()
    for p in paragraphs:
        d.add_paragraph(p)
    path.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(path))
    return path


def test_docx_training_banner_is_stripped(tmp_path):
    f = _docx(tmp_path / "V1 - PV TECHNOV - A EVITER.docx", [
        "DOSSIER DE FORMATION — PV TECHNOV AGE • Niveau : À éviter • Note auteur : 1,2 / 5",
        "⚠️ Exemple pédagogique — ne pas reproduire.",
        "TECHNOV", "PROCÈS-VERBAL AG DU 15/03/2026", "Résolution 1 — Il est décidé d'augmenter le capital.",
    ])
    [doc] = sources.load(f, tmp_path)
    assert "DOSSIER DE FORMATION" not in doc["text"] and "pédagogique" not in doc["text"]
    assert doc["text"].startswith("TECHNOV") and "Résolution 1" in doc["text"]
    assert doc["meta"]["source_type"] == "document"


def test_docx_email_thread_is_split_into_mails(tmp_path):
    f = _docx(tmp_path / "Emails pédagogiques - PV 01 Augmentation de capital.docx", [
        "Échanges internes — PV n°1", "De : Antoine Berthier (Avocat associé)", "À : Léa Marchand", "Objet : RE: Draft PV v1",
        "Léa, erreur de calcul sur le capital social : 50 000 + 8 000 = 58 000, pas 60 000. Refais le calcul trois fois.",
        "De : Léa Marchand", "À : Antoine Berthier", "Objet : RE: Draft PV v1",
        "Merci Antoine, je corrige le montant et j'ajoute la vérification du quorum avec les chiffres.",
    ])
    docs = sources.load(f, tmp_path, dossier="technov")
    assert len(docs) == 2
    assert all(d["meta"]["source_type"] == "mail" and d["meta"]["dossier"] == "technov" for d in docs)
    assert docs[0]["meta"]["auteur"].startswith("Antoine Berthier") and docs[0]["meta"]["titre"] == "RE: Draft PV v1"
    assert "58 000" in docs[0]["text"] and docs[0]["text"].startswith("Objet : RE: Draft PV v1")
    assert docs[1]["meta"]["page"] == 2  # un mail = une « page », pour une citation stable
    assert sources.label(docs[0]["meta"]).startswith("Mail de Antoine Berthier")


# --- historiques synthétiques : lien V1/V2/mails ↔ PDF final -----------------------------------
def test_history_pieces_are_linked_to_final_pdf(tmp_path):
    root = tmp_path / "historiques"
    d = root / "OVH - Actes du 09-12-2025"
    (d / "mails").mkdir(parents=True)
    (d / "V1.txt").write_text("[DOCUMENT SYNTHÉTIQUE — version V1 reconstituée de « OVH - Actes du 09-12-2025.pdf » "
                              "pour l'entraînement ; jamais déposée ni signée]\n\nPremier jet.", encoding="utf-8")
    (d / "mails" / "01.eml").write_bytes(b"From: A <a@cabinet.example>\nSubject: RE: Draft\n"
                                         b"X-Source-PDF: PDF/OVH - Actes du 09-12-2025.pdf\nX-Version-Cible: v1\n\nCorrige le quorum.\n")
    v1 = sources.load(d / "V1.txt", root)[0]
    assert v1["text"] == "Premier jet."
    assert (v1["meta"]["source_type"], v1["meta"]["version"], v1["meta"]["acte_id"]) == ("version", "V1", "OVH - Actes du 09-12-2025")
    mail = sources.load(d / "mails" / "01.eml", root)[0]
    assert (mail["meta"]["source_type"], mail["meta"]["version"], mail["meta"]["acte_id"]) == ("mail", "v1", "OVH - Actes du 09-12-2025")
    assert sources.label(v1["meta"]) == "Brouillon V1 — OVH - Actes du 09-12-2025"


def test_pdf_chunks_carry_acte_id(tmp_path):
    import chunking
    pdf = make_pdf(tmp_path / "OVH - Actes du 09-12-2025.pdf", ["Le quorum est atteint."])
    _, chunks = chunking.build_chunks(pdf, pdf.name)
    assert chunks[0].meta["acte_id"] == "OVH - Actes du 09-12-2025" and chunks[0].meta["version"] == "final"
