"""Brique amont : PDF → contexte structuré prêt pour la génération (LLM → réponse).

    from pipeline import prepare
    ctx = prepare("pv.pdf", exigence="max")      # écrit aussi pv.context.json

    python pipeline.py pv.pdf --exigence max [--dossier acme] [--categorie modeles_pv] [-o ctx.json]

Le contexte contient : texte du PV, type d'opération, sections avec passages de la base,
clauses attendues (grille), clauses détectées, score. Aucune synthèse ni feedback rédigé :
c'est la brique aval qui s'en charge.
"""
import argparse
import json
from pathlib import Path

import analyze
import llm
import scoring
from ingest import get_collection


ORAL_TYPES = ["mail", "reunion", "note"]


def contexte_dossier(col, clauses: list[dict], dossier: str) -> dict[str, list[dict]]:
    """Pour chaque clause : les passages de mails / réunions / notes du dossier qui en parlent."""
    where = {"$and": [{"dossier": dossier}, {"source_type": {"$in": ORAL_TYPES}}]}
    out = {}
    for c in clauses:
        passages = analyze.retrieve(col, [c["libelle"]], where=where)
        out[c["id"]] = [
            {"citation": analyze_label(p["meta"]), "text": p["text"], "source": p["meta"]["source"],
             "source_type": p["meta"]["source_type"], "date": p["meta"].get("date", ""), "distance": round(p["distance"], 3)}
            for p in passages
        ]
    return out


def analyze_label(meta: dict) -> str:
    import sources
    return sources.label(meta) if "source_type" in meta else f"{meta['source']} p.{meta['page']}"


def prepare(pv_path, exigence: str = "standard", categorie: str | None = None, out=None,
            dossier: str | None = None, pv_text: str | None = None, sections: bool = True) -> dict:
    """`pv_text` : texte déjà extrait (ex. reçu d'un client distant) ; le PDF n'est alors pas lu."""
    pv_path = Path(pv_path)
    grille = scoring.load_grille()
    if exigence not in grille["exigences"]:
        raise ValueError(f"exigence inconnue : {exigence} (attendu : {', '.join(grille['exigences'])})")

    print("1/6 Lecture du PV…")
    if not pv_text:
        pv_text = analyze.read_document(pv_path)

    print("2/6 Type d'opération…")
    typ = scoring.detect_type(pv_text, grille)
    clauses = grille["types_operation"][typ["type_operation"]]["clauses"]
    print(f"    {typ['type_operation']}" + ("" if typ["detecte"] else " (défaut : détection échouée)"))

    print("3/6 Clauses attendues…")
    checks = scoring.check_clauses(pv_text, clauses)
    score = scoring.compute_score(checks, clauses, exigence, grille)
    print(f"    score {score['final']}/100 (brut {score['brut']}, malus {score['malus_cles']})")

    print("4/6 Sections et passages de la base…" if sections else "4/6 Sections : ignorées")
    col = get_collection()
    sections = llm.chat_json(analyze.SYSTEM_DECOMPOSE, pv_text).get("sections", []) if sections else []
    for sec in sections:
        passages = analyze.retrieve(col, [sec.get("titre", ""), *sec.get("requetes", [])], categorie) if col.count() else []
        sec["passages"] = [
            {"text": p["text"], "source": p["meta"]["source"], "page": p["meta"]["page"], "distance": round(p["distance"], 3)}
            for p in passages
        ]
    print(f"    {len(sections)} sections, base : {col.count()} passages")

    oral = {}
    if dossier and col.count():
        print(f"5/6 Contexte oral du dossier « {dossier} »…")
        oral = contexte_dossier(col, clauses, dossier)
        print(f"    {sum(1 for v in oral.values() if v)}/{len(clauses)} clauses ont des traces (mails / réunions)")

    ctx = {
        "pv": pv_path.name,
        "pv_text": pv_text,
        "type_operation": typ["type_operation"],
        "type_libelle": grille["types_operation"][typ["type_operation"]]["libelle"],
        "type_detecte": typ["detecte"],
        "type_justification": typ["justification"],
        "exigence": exigence,
        "clauses_attendues": clauses,
        "clauses_detectees": checks,
        "score": score,
        "sections": sections,
        "dossier": dossier or "",
        "contexte_dossier": oral,
    }

    print("6/6 Écriture du contexte…")
    out = Path(out) if out else pv_path.with_suffix(".context.json")
    out.write_text(json.dumps(ctx, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Contexte écrit : {out}")
    return ctx


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pv", type=Path)
    ap.add_argument("--exigence", default="standard", choices=["standard", "max"])
    ap.add_argument("--categorie", default=None)
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--dossier", default=None, help="dossier client : ajoute le contexte mails / réunions par clause")
    a = ap.parse_args()
    prepare(a.pv, a.exigence, a.categorie, a.output, a.dossier)
