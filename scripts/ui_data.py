"""Produit les fichiers de données de l'UI (ui/data/<dossier>/vN.json) à partir des context.json.

    python scripts/ui_data.py helianthe "Hélianthe Technologies" out/helianthe_v1.json out/helianthe_v2.json ...

Chaque context.json vient de pipeline.prepare() puis respond.py (clé "reponse"). On ne garde que
ce que l'UI affiche : clauses fusionnées (attendu + détecté + traces), précédents dédupliqués, réponse LLM.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build(ctx: dict, version: int, dossier_label: str, corpus: dict) -> dict:
    att = {x["id"]: x for x in ctx["clauses_attendues"]}
    seen, precedents = set(), []
    for s in ctx["sections"]:
        for p in s["passages"]:
            key = (p["source"], p["page"])
            if key in seen:
                continue
            seen.add(key)
            precedents.append({"source": p["source"], "page": p["page"], "section_pv": s["titre"],
                               "text": p["text"][:400], "distance": p["distance"]})
    return {
        "pv": ctx["pv"], "version": version, "dossier": dossier_label,
        "type_operation": ctx["type_operation"], "type_libelle": ctx["type_libelle"],
        "exigence": ctx["exigence"], "score": ctx["score"], "reponse": ctx.get("reponse", {}),
        "clauses": [
            {"id": d["id"], "libelle": att[d["id"]]["libelle"], "etat": d["etat"], "cle": att[d["id"]]["cle"],
             "poids": att[d["id"]]["poids"], "pourquoi": att[d["id"]]["pourquoi"], "extrait_pv": d["extrait"][:300],
             "traces_orales": [{"citation": t["citation"], "text": t["text"][:320], "source_type": t["source_type"], "date": t["date"]}
                               for t in ctx.get("contexte_dossier", {}).get(d["id"], [])[:3]]}
            for d in ctx["clauses_detectees"]
        ],
        "precedents": sorted(precedents, key=lambda p: p["distance"])[:10],
        "corpus": corpus,
    }


def main() -> None:
    dossier, label, *files = sys.argv[1:]
    import chromadb
    sys.path.insert(0, str(ROOT))
    import config
    col = chromadb.PersistentClient(path=config.DB_PATH).get_collection(config.COLLECTION)
    general = col.get(where={"dossier": "general"}, include=["metadatas"])["metadatas"]
    sources = {m["source"] for m in general}
    corpus = {"actes": sum(1 for s in sources if s.lower().endswith(".pdf")),
              "templates": sum(1 for s in sources if s.lower().endswith(".docx")), "chunks": col.count()}
    out_dir = ROOT / "ui" / "data" / dossier
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(files, start=1):
        ctx = json.loads(Path(f).read_text(encoding="utf-8"))
        data = build(ctx, i, label, corpus)
        (out_dir / f"v{i}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"v{i}: score {data['score']['final']}, {len(data['precedents'])} précédents, "
              f"{sum(len(c['traces_orales']) for c in data['clauses'])} traces, résumé {len(data['reponse'].get('resume', ''))} car.")


if __name__ == "__main__":
    main()
