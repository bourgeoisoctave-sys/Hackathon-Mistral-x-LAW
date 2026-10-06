"""Serveur MCP : expose le moteur de scoring des PV à Claude (Desktop ou Code).

    python mcp_server.py                      # stdio, pour Claude Code / Desktop en local
    python mcp_server.py --http [--port 8000] # HTTP (streamable-http) sur /mcp, pour Legora ou tout client distant

    claude mcp add --scope project pv-scoring -- .venv/bin/python mcp_server.py

En stdio, stdout est réservé au protocole : tout affichage du pipeline part sur stderr.
En HTTP, le serveur n'écoute qu'en local ; pour Legora (SaaS), l'exposer via un tunnel (ex. ngrok).
Claude appelle `scorer_pv`, reçoit le contexte JSON (type, clauses, score, passages) et
rédige lui-même le feedback au junior.
"""
import base64
import binascii
import contextlib
import sys
import tempfile
from pathlib import Path

from mcp.server.mcpserver import MCPServer

import pipeline
import scoring

server = MCPServer(
    "pv-scoring",
    instructions=(
        "Outils d'évaluation de procès-verbaux d'assemblée générale (droit des sociétés, France). "
        "Appelle `scorer_pv` (chemin local) ou `scorer_pv_document` (PDF en base64 ou texte), puis rédige au junior un feedback pédagogique : "
        "score, clauses clés manquantes (chacune vaut -10), pourquoi chaque clause compte, "
        "en citant les passages de la base et du dossier fournis dans le contexte."
    ),
)


@server.tool()
def scorer_pv(pdf_path: str, exigence: str = "standard", dossier: str | None = None) -> dict:
    """Lit un PV d'AG (PDF), détecte le type d'opération, vérifie les clauses attendues et calcule le score.

    exigence : "standard" (dossier courant) ou "max" (dossier important : clause partielle = manquante).
    dossier  : nom du dossier client indexé, pour joindre le contexte mails / réunions par clause.
    Retourne le contexte complet : texte du PV, clauses attendues et détectées, score, sections et passages.
    """
    path = Path(pdf_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"PDF introuvable : {path}")
    with contextlib.redirect_stdout(sys.stderr):  # les print() du pipeline ne doivent pas toucher stdout
        return pipeline.prepare(path, exigence=exigence, dossier=dossier)


@server.tool()
def scorer_pv_document(
    nom: str,
    pdf_base64: str | None = None,
    pv_texte: str | None = None,
    exigence: str = "standard",
    dossier: str | None = None,
) -> dict:
    """Même évaluation que `scorer_pv`, mais le PV est transmis dans l'appel (client distant, ex. Legora).

    nom        : nom du fichier, pour le rapport (ex. "pv_age_acme.pdf").
    pdf_base64 : contenu du PDF encodé en base64 ; ou bien
    pv_texte   : texte du PV déjà extrait. L'un des deux est requis.
    exigence   : "standard" ou "max". dossier : dossier client indexé (contexte mails / réunions).
    """
    if not pdf_base64 and not pv_texte:
        raise ValueError("Fournir pdf_base64 ou pv_texte.")
    with tempfile.TemporaryDirectory(prefix="pv_") as tmp:
        path = Path(tmp) / (Path(nom).name or "pv.pdf")
        if pdf_base64:
            try:
                path.write_bytes(base64.b64decode(pdf_base64, validate=True))
            except (binascii.Error, ValueError) as exc:
                raise ValueError(f"pdf_base64 invalide : {exc}") from exc
        else:
            path.touch()
        with contextlib.redirect_stdout(sys.stderr):
            ctx = pipeline.prepare(path, exigence=exigence, dossier=dossier, pv_text=pv_texte,
                                   out=path.with_suffix(".context.json"))
    ctx["pv"] = nom
    return ctx


@server.tool()
def grille(type_operation: str | None = None) -> dict:
    """Grille de scoring : types d'opération et clauses attendues (poids, clause clé ou non).

    Sans argument : la liste des types. Avec un id (ex. AGE_levee_de_fonds) : ses clauses détaillées.
    """
    g = scoring.load_grille()
    if type_operation is None:
        return {
            "types": {tid: t["libelle"] for tid, t in g["types_operation"].items()},
            "exigences": g["exigences"],
            "malus_cle": g["malus_cle"],
        }
    if type_operation not in g["types_operation"]:
        raise ValueError(f"type inconnu : {type_operation} (attendu : {', '.join(g['types_operation'])})")
    return g["types_operation"][type_operation]


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Serveur MCP pv-scoring")
    ap.add_argument("--http", action="store_true", help="transport streamable-http au lieu de stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    if a.http:
        server.run("streamable-http", host=a.host, port=a.port)
    else:
        server.run("stdio")
