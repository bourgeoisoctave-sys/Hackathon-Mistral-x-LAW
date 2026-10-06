"""Fixtures communes : mode hors-ligne, base Chroma temporaire, PDF synthétiques."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf  # noqa: E402
import pytest  # noqa: E402

import config  # noqa: E402
import ingest  # noqa: E402
import ocr  # noqa: E402


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    """Par défaut : embeddings factices, base Chroma jetable, OCR désactivé (scan → rien)."""
    monkeypatch.setattr(config, "FAKE_EMBEDDINGS", True)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "chroma"))
    monkeypatch.setattr(ocr, "ocr_pages", lambda pdf_path: [])
    yield tmp_path


def make_pdf(path: Path, pages: list[str]) -> Path:
    """Écrit un PDF texte avec une page par élément de `pages` ("" = page vide/scan)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=11)
    doc.save(path)
    doc.close()
    return path


GUIDE_P1 = (
    "Guide de redaction des PV.\n"
    "Le quorum doit etre constate en debut de seance.\n"
    "La feuille de presence est signee par chaque actionnaire present."
)
GUIDE_P2 = (
    "Resultat des votes.\n"
    "Chaque resolution indique le nombre de voix pour, contre et les abstentions."
)
MODELE_P1 = (
    "Modele de PV.\n"
    "L'assemblee designe un president et un secretaire de seance."
)


@pytest.fixture
def docs_dir(tmp_path) -> Path:
    """Corpus minimal : deux catégories, un PDF à la racine, un PDF scanné."""
    root = tmp_path / "docs"
    make_pdf(root / "guides_internes" / "guide.pdf", [GUIDE_P1, GUIDE_P2])
    make_pdf(root / "modeles_pv" / "modele.pdf", [MODELE_P1])
    make_pdf(root / "racine.pdf", ["Document a la racine."])
    make_pdf(root / "guides_internes" / "scan.pdf", ["", ""])
    return root


@pytest.fixture
def indexed(docs_dir):
    """Corpus minimal déjà ingéré ; retourne la collection Chroma."""
    ingest.ingest(docs_dir)
    return ingest.get_collection()
