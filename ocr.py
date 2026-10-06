"""Extraction du texte d'un PDF : couche texte (PyMuPDF) sinon Mistral OCR, avec cache.

Le résultat OCR est écrit à côté du PDF (`mon_pv.ocr.json`) : l'API n'est payée qu'une fois.
"""
import base64
import json
from pathlib import Path

import pymupdf

import config
import llm


def _text_layer(pdf_path: Path) -> list[tuple[int, str]]:
    pages = []
    with pymupdf.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if text:
                pages.append((i, text))
    return pages


def cache_path(pdf_path: Path) -> Path:
    return pdf_path.with_suffix(".ocr.json")


def ocr_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """OCR Mistral de tout le document ; pages 1-based ; pages vides ignorées."""
    cache = cache_path(pdf_path)
    if cache.is_file():
        return [tuple(p) for p in json.loads(cache.read_text(encoding="utf-8"))]

    b64 = base64.b64encode(pdf_path.read_bytes()).decode()
    client = llm._get_client()
    res = llm._retry(
        lambda: client.ocr.process(
            model=config.OCR_MODEL,
            document={"type": "document_url", "document_url": f"data:application/pdf;base64,{b64}"},
        )
    )
    pages = [(p.index + 1, p.markdown.strip()) for p in res.pages if p.markdown and p.markdown.strip()]
    cache.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    return pages


def extract_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """Retourne [(numéro_de_page, texte)]. Scan (aucune couche texte) → OCR."""
    pages = _text_layer(pdf_path)
    if pages:
        return pages
    return ocr_pages(pdf_path)
