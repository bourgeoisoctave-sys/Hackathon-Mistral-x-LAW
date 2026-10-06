"""Recherche dans la base de bonnes pratiques, utilisable par analyze.py ou comme outil d'un LLM.

Usage comme outil (function calling Mistral / OpenAI) :
    tools = [TOOL_SPEC]
    ... le LLM renvoie un tool_call (name, arguments) ...
    resultat = call_tool(tool_call.function.name, tool_call.function.arguments)
    # resultat est une string JSON à renvoyer au LLM dans un message de rôle "tool"
"""
import json

import config
import llm
from ingest import get_collection
from parents import ParentStore

TEXTE_MAX_CHARS = 2500  # longueur maximale du texte d'un passage renvoyé au LLM


def retrieve(col, queries: list[str], categorie: str | None) -> list[dict]:
    """Cherche sur les petits chunks, puis rend l'unité entière (parent) à l'agent.

    Plusieurs requêtes par section ; les chunks d'une même unité sont fusionnés
    (on garde la meilleure distance) et dédoublonnés.
    """
    where = {"categorie": categorie} if categorie else None
    embeddings = llm.embed(queries)
    best: dict[str, dict] = {}  # parent_id -> {meta, distance}
    for emb in embeddings:
        res = col.query(
            query_embeddings=[emb],
            n_results=config.TOP_K_PER_QUERY,
            where=where,
            include=["metadatas", "distances"],
        )
        for meta, dist in zip(res["metadatas"][0], res["distances"][0]):
            if dist > config.MAX_DISTANCE:
                continue
            pid = meta["parent_id"]
            if pid not in best or dist < best[pid]["distance"]:
                best[pid] = {"meta": meta, "distance": dist}
    ranked = sorted(best.items(), key=lambda kv: kv[1]["distance"])[: config.TOP_K_PER_SECTION]
    texts = ParentStore().get_many([pid for pid, _ in ranked])
    return [
        {"text": texts[pid], "meta": v["meta"], "distance": v["distance"]}
        for pid, v in ranked
        if pid in texts
    ]


def passage_label(p: dict) -> str:
    m = p["meta"]
    section = m.get("section", "")
    return f"{m['source']}, p.{m['page']}" + (f" — {section[:100]}" if section else "")


# --------------------------------------------------------------------------- #
# Outil pour un LLM (function calling)
# --------------------------------------------------------------------------- #
def _tronquer(texte: str, max_chars: int = TEXTE_MAX_CHARS) -> str:
    return texte if len(texte) <= max_chars else texte[:max_chars].rstrip() + " […]"


def search_best_practices(query: str, categorie: str | None = None) -> dict:
    """Recherche les passages de la base pertinents pour une question unique."""
    col = get_collection()
    if col.count() == 0:
        return {"erreur": "La base est vide : lancer d'abord python ingest.py docs/"}
    passages = retrieve(col, [query], categorie)
    if not passages:
        return {"resultats": [], "message": "Aucun passage pertinent dans la base pour cette question."}
    return {
        "resultats": [
            {
                "source": p["meta"].get("source"),
                "page": p["meta"].get("page"),
                "section": p["meta"].get("section"),
                "societe": p["meta"].get("societe"),
                "date_acte": p["meta"].get("date_acte"),
                "type": p["meta"].get("chunk_type"),  # texte, preambule, tableau ou annexe
                "pertinence": round(1 - p["distance"], 2),
                "texte": _tronquer(p["text"]),
            }
            for p in passages
        ]
    }


TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "search_best_practices",
        "description": (
            "Recherche dans la base documentaire de l'entreprise (PV, décisions, actes et guides "
            "déjà validés) les passages qui illustrent les bonnes pratiques de rédaction pour un "
            "point précis d'un PV d'assemblée générale (quorum, bureau, ordre du jour, résolution, "
            "vote, pouvoirs, signatures…). Renvoie les passages avec leur source, page et section. "
            "Appeler une fois par thème, avec une question précise et autonome "
            "(compréhensible sans le reste de la conversation)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Question précise et autonome, par exemple : "
                        "« Comment rédiger la résolution donnant pouvoirs pour les formalités ? »"
                    ),
                },
                "categorie": {
                    "type": "string",
                    "description": (
                        "Optionnel : limite la recherche à une catégorie de documents, c'est-à-dire "
                        "au nom d'un sous-dossier de docs/ (par exemple modeles_pv). "
                        "Ne pas renseigner pour chercher dans toute la base."
                    ),
                },
            },
            "required": ["query"],
        },
    },
}

TOOLS = {"search_best_practices": search_best_practices}


def call_tool(name: str, arguments: str | dict) -> str:
    """Exécute un outil appelé par le LLM et renvoie toujours une string JSON.

    Ne lève jamais d'exception : toute erreur est renvoyée sous la forme
    {"erreur": "..."} pour que le LLM puisse la lire et réessayer.
    """
    try:
        if name not in TOOLS:
            raise ValueError(f"Outil inconnu : {name!r}. Outils disponibles : {', '.join(TOOLS)}")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError as exc:
                raise ValueError(f"Arguments JSON invalides : {exc}") from None
        if not isinstance(arguments, dict):
            raise ValueError("Les arguments doivent être un objet JSON.")
        if name == "search_best_practices":
            query = arguments.get("query")
            if not isinstance(query, str) or not query.strip():
                raise ValueError("Le paramètre « query » (texte non vide) est obligatoire.")
            resultat = search_best_practices(query.strip(), arguments.get("categorie") or None)
        else:
            resultat = TOOLS[name](**arguments)
    except Exception as exc:  # noqa: BLE001
        resultat = {"erreur": f"{type(exc).__name__} : {exc}" if not isinstance(exc, ValueError) else str(exc)}
    return json.dumps(resultat, ensure_ascii=False)
