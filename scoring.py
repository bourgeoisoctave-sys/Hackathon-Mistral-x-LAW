"""Grille de scoring : type d'opération, détection des clauses, calcul du score.

Les deux appels LLM (détection du type, état des clauses) renvoient du JSON validé ici ;
le calcul du score est pur et testable sans API.
"""
import json
import unicodedata
from pathlib import Path

import config
import llm

GRILLE_PATH = Path(__file__).parent / "grille.json"
ETATS = ("presente", "partielle", "absente")

SYSTEM_TYPE = """Tu es un juriste d'entreprise. On te donne le texte d'un procès-verbal d'assemblée \
et une liste de types d'opération possibles. Choisis le type qui correspond le mieux.
Réponds UNIQUEMENT en JSON : {"type_operation": "<id>", "justification": "une phrase"}"""

SYSTEM_CLAUSES = """Tu es un juriste d'entreprise qui relit un procès-verbal d'assemblée. On te donne \
le texte du PV et une liste de clauses attendues (id + libellé). Pour CHAQUE clause, indique si elle \
est présente, partielle (mentionnée mais incomplète ou sans les éléments attendus) ou absente, et \
cite l'extrait exact du PV qui la contient (chaîne vide si absente). Ne juge que ce qui est écrit.
Réponds UNIQUEMENT en JSON :
{"clauses": [{"id": "...", "etat": "presente" | "partielle" | "absente", "extrait": "...", "commentaire": "..."}]}"""


def load_grille(path: Path = GRILLE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalise_etat(value) -> str:
    s = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().strip().lower()
    return s if s in ETATS else "absente"


# --- appels LLM --------------------------------------------------------------------
def detect_type(pv_text: str, grille: dict) -> dict:
    """Retourne {"type_operation": id, "justification": str, "detecte": bool}."""
    types = grille["types_operation"]
    choix = "\n".join(f"- {tid} : {t['libelle']}" for tid, t in types.items())
    user = f"TYPES POSSIBLES :\n{choix}\n\nPV :\n{pv_text}"
    try:
        res = llm.chat_json(SYSTEM_TYPE, user)
    except Exception as exc:  # noqa: BLE001
        res = {"justification": f"erreur LLM : {exc}"}
    tid = res.get("type_operation")
    if tid in types:
        return {"type_operation": tid, "justification": res.get("justification", ""), "detecte": True}
    return {"type_operation": grille["type_par_defaut"], "justification": res.get("justification", ""), "detecte": False}


def check_clauses(pv_text: str, clauses: list[dict]) -> list[dict]:
    """Un appel LLM pour toutes les clauses ; toute clause non renvoyée est 'absente'."""
    liste = "\n".join(f"- {c['id']} : {c['libelle']}" for c in clauses)
    user = f"CLAUSES ATTENDUES :\n{liste}\n\nPV :\n{pv_text}"
    res = llm.chat_json(SYSTEM_CLAUSES, user)
    by_id = {str(r.get("id")): r for r in res.get("clauses", []) if isinstance(r, dict)}
    out = []
    for c in clauses:
        r = by_id.get(c["id"], {})
        out.append({
            "id": c["id"],
            "etat": _normalise_etat(r.get("etat")),
            "extrait": str(r.get("extrait") or ""),
            "commentaire": str(r.get("commentaire") or ""),
        })
    return out


# --- calcul pur ----------------------------------------------------------------------
def compute_score(checks: list[dict], clauses: list[dict], exigence: str, grille: dict) -> dict:
    """Score 0-100 : couverture pondérée des clauses, puis malus par clause clé manquante."""
    regles = grille["exigences"][exigence]
    valeur = {"presente": 1.0, "partielle": regles["partielle"], "absente": 0.0}
    etat = {c["id"]: c["etat"] for c in checks}

    total = sum(c["poids"] for c in clauses)
    obtenu = sum(c["poids"] * valeur[etat.get(c["id"], "absente")] for c in clauses)
    brut = round(100 * obtenu / total) if total else 0

    manquantes = [
        c["id"] for c in clauses
        if c["cle"] and (etat.get(c["id"], "absente") == "absente"
                         or (regles["malus_partielle_cle"] and etat.get(c["id"]) == "partielle"))
    ]
    malus = grille["malus_cle"] * len(manquantes)
    return {
        "brut": brut,
        "malus_cles": malus,
        "final": max(0, brut + malus),
        "cles_manquantes": manquantes,
        "exigence": exigence,
    }
