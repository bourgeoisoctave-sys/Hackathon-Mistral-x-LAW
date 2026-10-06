"""Recherche dans la base pour la barre de l'UI : question → documents trouvés + leurs fils, JSON sur stdout.

    .venv/bin/python scripts/search.py "Comment constater une augmentation de capital ?" [--k 4]

Un document = un acte (acte_id) ou, à défaut, un fichier source. Les brouillons V1/V2 ne sortent jamais
comme résultat (retrieval.retrieve les exclut) ; ils apparaissent seulement dans les fils d'un acte.
Les liens pointent vers /api/doc (servi par l'UI).
"""
import argparse
import contextlib
import json
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import retrieval  # noqa: E402
from ingest import get_collection  # noqa: E402

MAIL_LABELS = {
    "01_revue_v1": "Revue V1 – associé",
    "02_envoi_v2": "Envoi V2 – collaboratrice",
    "03_revue_v2": "Revue V2 – associé",
    "04_envoi_final": "Envoi final – collaboratrice",
    "05_validation": "Validation – associé",
}


def _doc_url(acte: str, piece: str) -> str:
    return f"/api/doc?acte={quote(acte)}&piece={quote(piece)}"


def threads(acte: str) -> list[dict]:
    """Final (PDF) puis, si un historique existe, V2, V1 et les emails dans l'ordre."""
    out = []
    if (ROOT / "docs" / "actes" / f"{acte}.pdf").exists():
        out.append({"label": "Final (PDF)", "href": _doc_url(acte, "final")})
    h = ROOT / "historiques" / acte
    if (h / "historique.json").is_file():
        out += [{"label": v, "href": _doc_url(acte, v)} for v in ("V2", "V1") if (h / f"{v}.txt").is_file()]
        out += [{"label": label, "href": _doc_url(acte, f"mail:{stem}")}
                for stem, label in MAIL_LABELS.items() if (h / "mails" / f"{stem}.eml").is_file()]
    return out


def search(question: str, k: int = 4) -> dict:
    col = get_collection()
    if col.count() == 0:
        return {"docs": [], "error": "Base vide : lancer python ingest.py docs/"}
    docs: dict[str, dict] = {}
    for p in retrieval.retrieve(col, [question]):
        m = p["meta"]
        key = m.get("acte_id") or m.get("source", "")
        if key in docs:
            continue
        docs[key] = {
            "id": key,
            "name": key if m.get("acte_id") else Path(m.get("source", key)).stem,
            "score": round(1 - p["distance"], 2),
            "where": retrieval.passage_label(p),
            "excerpt": p["text"][:400],
            "threads": threads(m["acte_id"]) if m.get("acte_id") else [],
        }
        if len(docs) == k:
            break
    return {"question": question, "docs": list(docs.values())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--k", type=int, default=4)
    a = ap.parse_args()
    with contextlib.redirect_stdout(sys.stderr):  # stdout ne contient que le JSON (lu par /api/search)
        res = search(a.question, a.k)
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
