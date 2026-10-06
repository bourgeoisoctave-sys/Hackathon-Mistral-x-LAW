"""Brique LLM → réponse : à partir de context.json (pipeline.prepare), rédige le feedback au junior.

    python respond.py pv.context.json            # ajoute la clé "reponse" dans le fichier
    python respond.py pv.context.json -o out.json

Contrat de sortie (lu tel quel par l'UI) :
    "reponse": {
      "resume":          "3 à 5 phrases : le message de l'assistant",
      "priorites":       ["<id clause>", ...],              # 3 max, dans l'ordre
      "par_clause":      {"<id>": {"pourquoi_ici": "...", "redaction": "..."}},
      "questions_suite": ["...", "..."]                     # 2 à 3 questions que le junior peut poser
    }

Règle : le LLM ne touche ni au score ni aux états des clauses (calculés) ; il rédige autour,
en s'appuyant uniquement sur le contexte fourni (extraits du PV, traces orales, précédents).
"""
import argparse
import json
from pathlib import Path

import llm

SYSTEM = """Tu es un avocat associé qui relit le projet de procès-verbal d'un junior. On te donne un \
contexte structuré : type d'opération, score calculé, état de chaque clause attendue (présente / \
partielle / absente) avec son poids et pourquoi elle compte, les extraits du PV, les échanges \
internes du dossier (mails, réunions) qui parlent de chaque clause, et des passages des précédents \
du cabinet.

Ta mission : rédiger le retour au junior, en français, pour qu'il comprenne POURQUOI chaque clause \
manquante compte dans CE dossier, pas seulement qu'elle manque.

Règles strictes :
- Ne modifie ni le score ni les états : tu rédiges autour de ce qui est calculé.
- Appuie-toi UNIQUEMENT sur le contexte fourni. Cite les traces orales (« dans le mail de X du … », \
« en réunion le … ») quand elles existent ; sinon, dis que le dossier n'en garde pas trace.
- Ton direct, bienveillant, concret : un associé qui forme, pas un correcteur.
- Pour chaque clause clé manquante ou partielle, propose une rédaction utilisable, cohérente avec \
les chiffres et noms du PV ; laisse [entre crochets] ce qui manque.

Réponds UNIQUEMENT en JSON :
{"resume": "3 à 5 phrases",
 "priorites": ["id_clause", "id_clause", "id_clause"],
 "par_clause": {"id_clause": {"pourquoi_ici": "1 à 3 phrases ancrées dans le dossier", "redaction": "texte proposé ou chaîne vide"}},
 "questions_suite": ["question courte", "question courte"]}"""


def _compact(ctx: dict, max_traces: int = 3, max_passages: int = 2) -> dict:
    """Le contexte vu par le LLM : tout ce qui compte, sans les champs volumineux inutiles."""
    attendues = {c["id"]: c for c in ctx["clauses_attendues"]}
    clauses = []
    for d in ctx["clauses_detectees"]:
        a = attendues[d["id"]]
        clauses.append({
            "id": d["id"], "libelle": a["libelle"], "etat": d["etat"], "cle": a["cle"], "poids": a["poids"],
            "pourquoi_general": a["pourquoi"], "extrait_pv": d["extrait"][:300], "commentaire": d["commentaire"][:200],
            "traces_orales": [{"citation": t["citation"], "texte": t["text"][:400]}
                              for t in ctx.get("contexte_dossier", {}).get(d["id"], [])[:max_traces]],
        })
    precedents = []
    for s in ctx.get("sections", []):
        for p in s.get("passages", [])[:max_passages]:
            precedents.append({"section_pv": s.get("titre"), "source": p.get("source"), "page": p.get("page"), "texte": p["text"][:400]})
    return {
        "pv": ctx["pv"], "type_operation": ctx["type_libelle"], "exigence": ctx["exigence"],
        "score": ctx["score"], "clauses": clauses, "precedents_cabinet": precedents[:12],
        "texte_pv": ctx["pv_text"][:6000],
    }


def respond(ctx: dict) -> dict:
    ids = {c["id"] for c in ctx["clauses_attendues"]}
    res = llm.chat_json(SYSTEM, json.dumps(_compact(ctx), ensure_ascii=False), temperature=0.3)
    # Validation légère : on ne garde que ce qui respecte le contrat.
    par_clause = {k: {"pourquoi_ici": str(v.get("pourquoi_ici", "")), "redaction": str(v.get("redaction", ""))}
                  for k, v in (res.get("par_clause") or {}).items() if k in ids and isinstance(v, dict)}
    priorites = [p for p in (res.get("priorites") or []) if p in ids][:3]
    questions = [str(q) for q in (res.get("questions_suite") or []) if q][:3]
    return {"resume": str(res.get("resume", "")).strip(), "priorites": priorites,
            "par_clause": par_clause, "questions_suite": questions}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("context", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    a = ap.parse_args()
    ctx = json.loads(a.context.read_text(encoding="utf-8"))
    ctx["reponse"] = respond(ctx)
    out = a.output or a.context
    out.write_text(json.dumps(ctx, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Réponse écrite : {out}\n\n{ctx['reponse']['resume']}\n\nPriorités : {', '.join(ctx['reponse']['priorites'])}")


if __name__ == "__main__":
    main()
