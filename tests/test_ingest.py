"""Découpage, extraction PDF et ingestion dans Chroma (hors-ligne)."""
import pytest

import chunking
import ingest
import ocr
from conftest import make_pdf


# --- extraction PDF (ocr.py) ------------------------------------------------------------
def test_extract_pages_skips_empty_pages(tmp_path):
    pdf = make_pdf(tmp_path / "x.pdf", ["Page un.", "", "Page trois."])
    pages = ocr.extract_pages(pdf)
    assert [n for n, _ in pages] == [1, 3]
    assert "Page un." in pages[0][1]


def test_extract_pages_scan_returns_nothing(tmp_path):
    pdf = make_pdf(tmp_path / "scan.pdf", ["", ""])
    assert ocr.extract_pages(pdf) == []


# --- découpage structurel (chunking.py) -----------------------------------------------------
PV_AG = (
    "PROCÈS-VERBAL DE L'ASSEMBLÉE GÉNÉRALE\n"
    "\n"
    "PREMIÈRE RÉSOLUTION\n"
    "Approbation des comptes\n"
    "L'Assemblée approuve les comptes de l'exercice.\n"
    "\n"
    "DEUXIÈME RÉSOLUTION\n"
    "Pouvoirs pour les formalites\n"
    "L'Assemblée confère tous pouvoirs au porteur."
)


def test_pv_ag_is_split_by_resolution(tmp_path):
    pdf = make_pdf(tmp_path / "pv.pdf", [PV_AG])
    info, chunks = chunking.build_chunks(pdf, "pv.pdf")
    assert info.doc_type == "pv_ag"
    sections = [c.meta["section"] for c in chunks]
    assert any(s.startswith("PREMIÈRE RÉSOLUTION") for s in sections)
    assert any(s.startswith("DEUXIÈME RÉSOLUTION") for s in sections)
    deux = next(c for c in chunks if c.meta["section"].startswith("DEUXIÈME"))
    assert "tous pouvoirs" in deux.text and "approuve les comptes" not in deux.text


def test_scanned_pdf_goes_through_ocr(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "ocr_pages", lambda p: [(1, "Texte lu par OCR.")])
    pdf = make_pdf(tmp_path / "scan.pdf", [""])
    info, chunks = chunking.build_chunks(pdf, "scan.pdf")
    assert info is not None and "Texte lu par OCR." in chunks[0].text


def test_text_chunks_keep_source_metadata():
    meta = {"source": "mails/a.eml", "page": 1, "categorie": "mails", "dossier": "acme",
            "source_type": "mail", "date": "2026-09-14", "auteur": "Me X", "titre": "DPS"}
    chunks = chunking.build_text_chunks("Il faut supprimer le DPS.", meta, "Mail de Me X, 2026-09-14 — DPS")
    assert len(chunks) == 1
    c = chunks[0]
    assert c.meta["source_type"] == "mail" and c.meta["dossier"] == "acme" and c.meta["chunk_type"] == "texte"
    assert c.embed_text.startswith("Mail de Me X")
    assert c.parent_text == "Il faut supprimer le DPS."


# --- ingest ---------------------------------------------------------------------------
def test_ingest_metadata_contract(docs_dir):
    ingest.ingest(docs_dir)
    col = ingest.get_collection()
    rows = col.get(include=["metadatas"])
    assert col.count() > 0
    for m in rows["metadatas"]:
        assert {"source", "page", "categorie", "dossier", "source_type", "date", "auteur", "titre",
                "doc_type", "section", "chunk_type", "parent_id"} <= set(m)
        assert m["source_type"] == "document" and m["dossier"] == "general"
    cats = {m["categorie"] for m in rows["metadatas"]}
    assert cats == {"guides_internes", "modeles_pv", "general"}
    # La catégorie vient du premier sous-dossier ; la racine donne "general".
    by_source = {m["source"]: m["categorie"] for m in rows["metadatas"]}
    assert by_source["guides_internes/guide.pdf"] == "guides_internes"
    assert by_source["racine.pdf"] == "general"


def test_ingest_stores_raw_chunk_not_prefixed(docs_dir):
    ingest.ingest(docs_dir)
    docs = ingest.get_collection().get(include=["documents"])["documents"]
    assert not any(d.startswith("guide (p.") for d in docs)


def test_ingest_skips_scanned_pdf(docs_dir, capsys):
    ingest.ingest(docs_dir)
    sources = {m["source"] for m in ingest.get_collection().get(include=["metadatas"])["metadatas"]}
    assert "guides_internes/scan.pdf" not in sources
    assert "scan.pdf : aucun texte extractible" in capsys.readouterr().out


def test_ingest_is_idempotent(docs_dir):
    ingest.ingest(docs_dir)
    n1 = ingest.get_collection().count()
    ingest.ingest(docs_dir)
    assert ingest.get_collection().count() == n1


def test_ingest_reset_wipes_collection(docs_dir, tmp_path):
    ingest.ingest(docs_dir)
    other = tmp_path / "docs2"
    make_pdf(other / "seul.pdf", ["Nouveau corpus."])
    ingest.ingest(other, reset=True)
    sources = {m["source"] for m in ingest.get_collection().get(include=["metadatas"])["metadatas"]}
    assert sources == {"seul.pdf"}


def test_ingest_no_pdf_exits(tmp_path):
    (tmp_path / "vide").mkdir()
    with pytest.raises(SystemExit):
        ingest.ingest(tmp_path / "vide")


def test_reingest_replaces_old_version(docs_dir):
    ingest.ingest(docs_dir)
    make_pdf(docs_dir / "modeles_pv" / "modele.pdf", ["Texte entierement nouveau."])
    ingest.ingest(docs_dir)
    docs = ingest.get_collection().get(where={"source": "modeles_pv/modele.pdf"}, include=["documents"])["documents"]
    assert docs and all("nouveau" in d for d in docs)


def test_dry_run_writes_nothing(docs_dir, capsys):
    ingest.ingest(docs_dir, dry_run=True)
    assert "Simulation terminée" in capsys.readouterr().out
    assert ingest.get_collection().count() == 0


def test_dry_run_never_calls_ocr(docs_dir, monkeypatch):
    def boom(p):
        raise AssertionError("OCR appelé pendant une simulation")
    monkeypatch.setattr(ocr, "ocr_pages", boom)
    ingest.ingest(docs_dir, dry_run=True)  # docs_dir contient un scan
