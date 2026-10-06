"""Cas similaires : les n précédents du cabinet les plus proches d'un brouillon.

Classement, dans l'ordre : même type d'opération (obligatoire si possible) → même nature
(AGE / AGO / décision) → même forme sociale → meilleure couverture de la grille (`brut`) →
date la plus récente. Chaque cas rend ses raisons, affichées dans l'UI.

    python similar.py "legora-files-2026-10-04/PV AG - 01 V1 Augmentation de capital en numéraire.docx" -n 3
"""
import argparse
import re
import json
from datetime import date
from pathlib import Path

import analyze
import llm
import qualify
import scoring
import sources
from corpus_index import INDEX_PATH

WEIGHTS = {"categorie": 120, "type": 60, "nature": 30, "forme": 25, "brut": 0.5, "recence": 4}  # recence : points/an, max 5 ans
HISTORIQUES_DIR = Path(__file__).parent / "historiques"
LEGORA_DIR = Path(__file__).parent / "legora-files-2026-10-04"

SYSTEM_CATEGORIE = """Tu es un juriste d'entreprise. Classe ce procès-verbal / cette décision dans UNE des catégories \
d'opération proposées (numéro). Réponds UNIQUEMENT en JSON : {"categorie": "NN"}"""


def categories() -> dict[str, str]:
    """Les 13 types d'opération du jeu pédagogique, d'après les noms « PV AG - NN Vx libellé »."""
    out = {}
    for p in sorted(LEGORA_DIR.glob("PV AG - * V1 *.docx")):
        m = re.match(r"PV AG - (\d{2}) V1 (.+)", p.stem)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def histories() -> dict[str, dict]:
    """acte_id → historique reconstitué (catégorie, date, défauts + corrections). Vide si le dossier n'existe pas."""
    out = {}
    for meta in HISTORIQUES_DIR.glob("*/historique.json"):
        try:
            h = json.loads(meta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out[meta.parent.name] = h
    return out


def classify_categorie(text: str, cats: dict[str, str]) -> dict:
    """Catégorie (13 types) du brouillon, par LLM ; {"categorie": "", ...} si indéterminée."""
    if not cats:
        return {"categorie": "", "categorie_libelle": ""}
    user = "CATÉGORIES :\n" + "\n".join(f"{k} : {v}" for k, v in cats.items()) + f"\n\nTEXTE :\n{text[:6000]}"
    try:
        res = llm.chat_json(SYSTEM_CATEGORIE, user)
    except Exception:  # noqa: BLE001
        res = {}
    cat = str(res.get("categorie", "")).zfill(2) if res.get("categorie") else ""
    return {"categorie": cat if cat in cats else "", "categorie_libelle": cats.get(cat, "")}


def load_index(path: Path = INDEX_PATH, only_ingested: bool = True) -> list[dict]:
    """Index des précédents ; par défaut restreint aux sources présentes dans la base (parents réutilisables)."""
    if not path.exists():
        return []
    entries = json.loads(path.read_text(encoding="utf-8"))
    if only_ingested:
        try:
            from corpus_index import ingested_sources
            keep = ingested_sources()
            entries = [e for e in entries if e["source"] in keep]
        except Exception:  # noqa: BLE001  (base absente : on garde tout)
            pass
    # Catégorie (13 types) et date depuis l'historique reconstitué quand il existe.
    hist = histories()
    for e in entries:
        h = hist.get(Path(e["source"]).stem)
        e["categorie"] = h.get("categorie", "") if h else ""
        e["categorie_libelle"] = h.get("categorie_libelle", "") if h else ""
        if h and h.get("date_acte") and not e.get("date"):
            e["date"] = h["date_acte"]
    return entries


def _years_ago(iso: str) -> float:
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return 10.0
    return max(0.0, (date.today() - d).days / 365.25)


def rank(draft: dict, index: list[dict], n: int = 3) -> list[dict]:
    """draft : {type_operation, forme, nature}. Retourne les n meilleurs avec `points` et `raisons`."""
    scored = []
    for e in index:
        pts, raisons = 0.0, []
        if draft.get("categorie") and e.get("categorie") == draft["categorie"]:
            pts += WEIGHTS["categorie"]; raisons.append(f"même opération ({e.get('categorie_libelle') or e['categorie']})")
        if e["type_operation"] == draft["type_operation"]:
            pts += WEIGHTS["type"]; raisons.append("même famille de grille")
        if draft.get("nature") and e.get("nature") == draft["nature"]:
            pts += WEIGHTS["nature"]; raisons.append(f"même nature ({e['nature']})")
        if draft.get("forme") and e.get("forme") == draft["forme"]:
            pts += WEIGHTS["forme"]; raisons.append(f"même forme sociale ({e['forme']})")
        pts += WEIGHTS["brut"] * e.get("brut", 0)
        raisons.append(f"couverture de la grille {e.get('brut', 0)}/100")
        rec = max(0.0, 5 - _years_ago(e.get("date", ""))) * WEIGHTS["recence"]
        pts += rec
        if e.get("date"):
            raisons.append(f"acte du {e['date']}")
        scored.append({**e, "points": round(pts, 1), "raisons": raisons})
    scored.sort(key=lambda x: (-x["points"], x["source"]))
    return scored[:n]


def with_history(cases: list[dict], max_chars: int = 1500) -> list[dict]:
    """Ajoute à chaque cas son historique reconstitué (defauts V1/V2, revues de l'associé), s'il existe."""
    from retrieval import historique_acte
    out = []
    for c in cases:
        h = historique_acte(Path(c["source"]).stem)
        revues = [] if "erreur" in h else [
            {"version": e["version"],
             "defauts": [{"defaut": str(d.get("defaut", d))[:300], "correction": str(d.get("correction", ""))[:400]} if isinstance(d, dict) else {"defaut": str(d)[:300], "correction": ""}
                         for d in e.get("defauts", [])[:6]],
             "revue": (e.get("revue_associe") or "")[:max_chars]}
            for e in h.get("etapes", []) if e.get("revue_associe") or e.get("defauts")]
        out.append({**c, "acte_id": Path(c["source"]).stem, "historique": revues, "synthetique": bool(revues)})
    return out


def similar_cases(pv_path: Path, n: int = 3, pv_text: str | None = None, type_operation: str | None = None) -> dict:
    text = pv_text or sources.strip_training_banner(analyze.read_document(pv_path))
    qual = qualify.qualify(text, pv_path.name)
    if type_operation is None:
        type_operation = scoring.detect_type(text, scoring.load_grille())["type_operation"]
    draft = {"type_operation": type_operation, **qual, **classify_categorie(text, categories())}
    return {"brouillon": draft, "cas": with_history(rank(draft, load_index(), n))}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pv", type=Path)
    ap.add_argument("-n", type=int, default=3)
    a = ap.parse_args()
    res = similar_cases(a.pv, a.n)
    print("Brouillon :", json.dumps(res["brouillon"], ensure_ascii=False))
    print(f"Index : {len(load_index())} précédents, {sum(1 for h in histories().values())} historiques, {len(categories())} catégories")
    for i, c in enumerate(res["cas"], 1):
        print(f"\n{i}. {c['source']}  ({c['points']} pts)\n   {c['societe']} · {c['forme'] or '?'} · {c['nature'] or '?'} · {c['date'] or '?'} · brut {c['brut']}\n   " + " ; ".join(c["raisons"]))
        for h in c["historique"]:
            print(f"   revue {h['version']} (synthétique) : {h['revue'][:140].replace(chr(10), ' ')}…")
