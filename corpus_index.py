"""Index qualité du corpus : pour chaque précédent, type d'opération, forme sociale, date et score (grille).

    python corpus_index.py docs/                 # écrit corpus_index.json (cache par fichier : relance rapide)
    python corpus_index.py docs/ --limit 2       # essai
    python corpus_index.py docs/ --workers 3
    python corpus_index.py docs/ --all          # aussi les documents non ingérés (OCR possible, long)

Par défaut, seuls les documents présents dans la base vectorielle sont indexés : ce sont les seuls
dont les unités entières (parents) sont réutilisables pour corriger un brouillon.

Le classement des « cas similaires » (similar.py) lit cet index : même type → même forme → score → date.
"""
import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import analyze
import qualify
import scoring
import sources

INDEX_PATH = Path(__file__).parent / "corpus_index.json"


def _file_hash(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()[:12]


def index_one(path: Path, root: Path, grille: dict) -> dict:
    rel = str(path.relative_to(root))
    text = analyze.read_document(path) if path.suffix.lower() in (".pdf", ".docx") else path.read_text(encoding="utf-8", errors="replace")
    text = sources.strip_training_banner(text)
    qual = qualify.qualify(text, rel)
    typ = scoring.detect_type(text, grille)
    clauses = grille["types_operation"][typ["type_operation"]]["clauses"]
    checks = scoring.check_clauses(text, clauses)
    score = scoring.compute_score(checks, clauses, "standard", grille)
    return {
        "source": rel, "hash": _file_hash(path), "chars": len(text), **qual,
        "type_operation": typ["type_operation"], "type_detecte": typ["detecte"],
        "score": score["final"], "brut": score["brut"], "cles_manquantes": score["cles_manquantes"],
        "clauses_presentes": [c["id"] for c in checks if c["etat"] == "presente"],
    }


def ingested_sources(dossier: str = "general") -> set[str]:
    """Sources présentes dans la base vectorielle : les seuls précédents réutilisables (parents)."""
    import chromadb
    import config
    col = chromadb.PersistentClient(path=config.DB_PATH).get_or_create_collection(config.COLLECTION)
    return {m["source"] for m in col.get(where={"dossier": dossier}, include=["metadatas"])["metadatas"]}


def build_index(root: Path, limit: int = 0, workers: int = 3, out: Path = INDEX_PATH, only_ingested: bool = True) -> list[dict]:
    grille = scoring.load_grille()
    files = [p for p in sources.iter_files(root) if p.suffix.lower() in (".pdf", ".docx")]
    if only_ingested:
        keep = ingested_sources()
        files = [p for p in files if str(p.relative_to(root)) in keep]
    if limit:
        files = files[:limit]
    cache = {e["source"]: e for e in json.loads(out.read_text(encoding="utf-8"))} if out.exists() else {}
    todo = [p for p in files if cache.get(str(p.relative_to(root)), {}).get("hash") != _file_hash(p)]
    print(f"{len(files)} documents, {len(todo)} à (re)scorer, {workers} workers", file=sys.stderr)

    results = {k: v for k, v in cache.items() if any(str(p.relative_to(root)) == k for p in files)}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(index_one, p, root, grille): p for p in todo}
        for fut in as_completed(futs):
            p = futs[fut]
            try:
                e = fut.result()
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {p.name} : {exc}", file=sys.stderr)
                continue
            results[e["source"]] = e
            print(f"  + {e['source'][:60]:60} {e['type_operation']:26} {e['forme'] or '?':5} {e['date'] or '?':10} score {e['score']:3}", file=sys.stderr)
            out.write_text(json.dumps(sorted(results.values(), key=lambda x: x["source"]), ensure_ascii=False, indent=1), encoding="utf-8")
    entries = sorted(results.values(), key=lambda x: x["source"])
    out.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Index écrit : {out} ({len(entries)} entrées)", file=sys.stderr)
    return entries


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("-o", "--output", type=Path, default=INDEX_PATH)
    ap.add_argument("--all", action="store_true", help="indexe aussi les documents absents de la base vectorielle")
    a = ap.parse_args()
    build_index(a.root, a.limit, a.workers, a.output, only_ingested=not a.all)
