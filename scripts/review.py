"""Revue live d'un brouillon pour l'UI : qualification → grille/score → cas similaires → correction → feedback.

    .venv/bin/python scripts/review.py mon_pv.docx --exigence standard --dossier helianthe --id abc123

stdout : un seul JSON final (lu par /api/review). stderr : une ligne JSON par étape {"step","label","pct"}
(relayée en SSE à l'UI) puis les logs du pipeline. Le .docx corrigé est écrit dans reviews/<id>.docx.
"""
import argparse
import contextlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import analyze  # noqa: E402
import pipeline  # noqa: E402
import qualify  # noqa: E402
import redraft  # noqa: E402
import similar  # noqa: E402
import respond  # noqa: E402
import sources  # noqa: E402
from scripts.ui_data import build  # noqa: E402

REVIEWS_DIR = ROOT / "reviews"
STEPS = [
    ("lecture", "Reading the draft", 5),
    ("qualification", "Qualifying: operation, legal form, date", 12),
    ("grille", "Checking the expected clauses and scoring", 40),
    ("similaires", "Finding the closest precedents and the partner's reviews", 50),
    ("correction", "Rewriting the missing clauses from precedents", 80),
    ("feedback", "Writing the feedback", 92),
    ("fichier", "Building the corrected file", 98),
]


def progress(step: str, **extra) -> None:
    label, pct = next((l, p) for s, l, p in STEPS if s == step)
    print(json.dumps({"step": step, "label": label, "pct": pct, **extra}, ensure_ascii=False), file=sys.stderr, flush=True)


def corpus_stats() -> dict:
    import chromadb
    import config
    col = chromadb.PersistentClient(path=config.DB_PATH).get_or_create_collection(config.COLLECTION)
    metas = col.get(where={"dossier": "general"}, include=["metadatas"])["metadatas"]
    by = lambda cat, st=None: len({m["source"] for m in metas if m.get("categorie") == cat and (st is None or m.get("source_type") == st)})  # noqa: E731
    return {"actes": by("actes"), "templates": by("modeles_pv"), "revues": by("historiques", "mail"), "chunks": col.count()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pv", type=Path)
    ap.add_argument("--exigence", default="standard", choices=["standard", "max"])
    ap.add_argument("--dossier", default="helianthe")
    ap.add_argument("--id", default=None)
    ap.add_argument("-n", type=int, default=3)
    a = ap.parse_args()
    rid = a.id or f"{int(time.time())}"

    with contextlib.redirect_stdout(sys.stderr):
        progress("lecture")
        pv_text = sources.strip_training_banner(analyze.read_document(a.pv))
        progress("qualification")
        qual = qualify.qualify(pv_text, a.pv.name)
        progress("grille")
        ctx = pipeline.prepare(a.pv, a.exigence, None, out=Path("/dev/null"), dossier=a.dossier, pv_text=pv_text, sections=False)
        progress("similaires")
        cas = similar.similar_cases(Path(ctx["pv"]), a.n, pv_text=ctx["pv_text"], type_operation=ctx["type_operation"])
        progress("correction", docs=[c.get("acte_id") or c.get("source", "") for c in cas["cas"]])  # l'UI sort un cube par acte
        rd = redraft.redraft(ctx, a.n, cas=cas)
        progress("feedback")
        ctx["reponse"] = respond.respond(ctx)
        progress("fichier")
        REVIEWS_DIR.mkdir(exist_ok=True)
        redraft.to_docx(rd, ctx, REVIEWS_DIR / f"{rid}.docx")
        data = build(ctx, 0, qual["societe"] or a.pv.stem, corpus_stats())

    data.update({
        "id": rid,
        "qualification": {**qual, "categorie": rd["brouillon_qualifie"].get("categorie", ""),
                          "categorie_libelle": rd["brouillon_qualifie"].get("categorie_libelle", "")},
        "score_apres": rd["score_apres"],
        "inchange_pct": rd["inchange_pct"],
        "cas_similaires": [
            {k: c.get(k) for k in ("acte_id", "source", "societe", "forme", "nature", "date", "brut", "points", "raisons",
                                   "categorie_libelle", "historique", "synthetique")}
            for c in rd["cas_similaires"]
        ],
        "changements": rd["changements"],
        "texte_corrige": rd["texte_corrige"],
        "texte_balise": rd["texte_balise"],
        "docx_url": f"/api/download?id={rid}",
        "live": True,
    })
    json.dump(data, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
