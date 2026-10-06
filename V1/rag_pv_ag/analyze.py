"""Analyse un PV d'AG au regard des best practices indexées et produit un rapport.

Usage :
    python analyze.py mon_pv.pdf -o rapport.md
    python analyze.py mon_pv.pdf --categorie modeles_pv     # restreint la recherche

Pipeline :
    1. extraction du texte du PV
    2. décomposition en sections + points à vérifier (LLM)
    3. recherche vectorielle des best practices pour chaque section
    4. recommandations par section, uniquement à partir des passages retrouvés (LLM)
    5. synthèse globale + rapport Markdown avec sources citées
"""
import argparse
import json
from pathlib import Path

import pymupdf

import llm
from ingest import get_collection
from retrieval import passage_label, retrieve

# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
SYSTEM_DECOMPOSE = """Tu es un juriste d'entreprise spécialisé dans les procès-verbaux d'assemblée \
générale de sociétés commerciales. On te donne le texte d'un PV. Découpe-le en sections \
logiques (ex. : en-tête et convocation, quorum et feuille de présence, bureau de l'assemblée, \
documents mis à disposition, ordre du jour, chaque résolution, votes, clôture et signatures).

Réponds UNIQUEMENT en JSON, au format :
{"sections": [{"titre": "...", "extrait": "texte exact de la section (copié du PV)", \
"requetes": ["2 à 4 questions courtes à poser à une base de bonnes pratiques pour juger \
cette section (ex. : 'Quelles mentions doivent figurer dans le résultat d'un vote ?')"]}]}"""

SYSTEM_SECTION = """Tu es un conseiller qui aide à améliorer des PV d'AG selon les bonnes \
pratiques INTERNES de l'entreprise. On te donne une section de PV et des passages numérotés \
issus de la base documentaire de l'entreprise.

Règles strictes :
- Appuie-toi UNIQUEMENT sur les passages fournis. N'invente aucune règle ni référence.
- Chaque recommandation cite les passages utilisés via leur numéro dans "sources".
- Si aucun passage n'est pertinent, mets "couverture": "aucune" et n'invente rien.
- Ne donne pas d'avis juridique définitif ; signale ce qui mérite validation par le juridique.

Réponds UNIQUEMENT en JSON :
{"statut": "conforme" | "a_ameliorer" | "lacune",
 "couverture": "bonne" | "partielle" | "aucune",
 "constats": ["ce qui est correct ou problématique dans la section"],
 "recommandations": [{"action": "...", "justification": "...", "sources": [1, 2]}],
 "reformulation_proposee": "texte réécrit de la section, ou chaîne vide si inutile"}"""

SYSTEM_SYNTHESE = """Tu rédiges la synthèse d'un audit de PV d'AG. À partir des résultats par \
section, écris en français, en 6 à 10 lignes de prose (sans liste), les forces principales du PV, \
les 3 priorités d'amélioration, et les sections où la base de bonnes pratiques ne permettait pas \
de se prononcer."""


# --------------------------------------------------------------------------- #
# Étapes
# --------------------------------------------------------------------------- #
def read_pdf(path: Path) -> str:
    with pymupdf.open(path) as doc:
        text = "\n\n".join(page.get_text("text") for page in doc).strip()
    if not text:
        raise SystemExit("Aucun texte extractible dans ce PV (PDF scanné ?).")
    return text


def analyze_section(section: dict, passages: list[dict]) -> dict:
    if passages:
        ctx = "\n\n".join(
            f"[{i}] ({passage_label(p)})\n{p['text']}"
            for i, p in enumerate(passages, start=1)
        )
    else:
        ctx = "(aucun passage pertinent trouvé dans la base)"
    user = (
        f"SECTION DU PV : {section['titre']}\n\n{section['extrait']}\n\n"
        f"PASSAGES DE LA BASE DE BONNES PRATIQUES :\n{ctx}"
    )
    result = llm.chat_json(SYSTEM_SECTION, user)
    result["_passages"] = passages
    return result


STATUT_LABEL = {"conforme": "Conforme", "a_ameliorer": "À améliorer", "lacune": "Lacune"}


def build_report(pv_name: str, synthese: str, results: list[tuple[dict, dict]]) -> str:
    lines = [f"# Analyse du PV d'AG — {pv_name}", "", "## Synthèse", "", synthese, ""]
    lines += ["## Vue d'ensemble", "", "| Section | Statut | Couverture base |", "|---|---|---|"]
    for sec, res in results:
        lines.append(
            f"| {sec['titre']} | {STATUT_LABEL.get(res.get('statut'), res.get('statut', '?'))} "
            f"| {res.get('couverture', '?')} |"
        )
    lines.append("")
    for sec, res in results:
        passages = res["_passages"]
        lines += [f"## {sec['titre']}", ""]
        lines.append(
            f"**Statut :** {STATUT_LABEL.get(res.get('statut'), res.get('statut'))} · "
            f"**Couverture de la base :** {res.get('couverture')}"
        )
        lines.append("")
        for c in res.get("constats", []):
            lines.append(f"- {c}")
        if res.get("constats"):
            lines.append("")
        for k, rec in enumerate(res.get("recommandations", []), start=1):
            refs = " ; ".join(
                passage_label(passages[i - 1])
                for i in rec.get("sources", [])
                if isinstance(i, int) and 1 <= i <= len(passages)
            )
            lines.append(f"**Recommandation {k}.** {rec.get('action', '')}")
            lines.append(f"  - Pourquoi : {rec.get('justification', '')}")
            if refs:
                lines.append(f"  - Sources : {refs}")
            lines.append("")
        if res.get("reformulation_proposee"):
            lines += ["**Reformulation proposée**", "", f"> {res['reformulation_proposee']}", ""]
    lines += [
        "---",
        "*Rapport généré à partir de la base de bonnes pratiques de l'entreprise. "
        "Les points juridiques sont à valider par le service juridique.*",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pv", type=Path, help="PV d'AG au format PDF texte")
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--categorie", default=None, help="limite la recherche à une catégorie de documents")
    ap.add_argument("--json", action="store_true", help="écrit aussi les résultats bruts en .json")
    args = ap.parse_args()

    col = get_collection()
    if col.count() == 0:
        raise SystemExit("Base vide : lancez d'abord `python ingest.py docs/`.")

    print("1/4 Lecture du PV…")
    pv_text = read_pdf(args.pv)

    print("2/4 Décomposition en sections…")
    sections = llm.chat_json(SYSTEM_DECOMPOSE, pv_text).get("sections", [])
    if not sections:
        raise SystemExit("Le modèle n'a identifié aucune section.")
    print(f"    {len(sections)} sections identifiées")

    print("3/4 Recherche des best practices et analyse par section…")
    results = []
    for sec in sections:
        queries = [sec["titre"], *sec.get("requetes", [])]
        passages = retrieve(col, queries, args.categorie)
        print(f"    - {sec['titre']} ({len(passages)} passages)")
        results.append((sec, analyze_section(sec, passages)))

    print("4/4 Synthèse et rapport…")
    recap = json.dumps(
        [
            {"section": s["titre"], "statut": r.get("statut"), "couverture": r.get("couverture"),
             "constats": r.get("constats"), "recommandations": [x.get("action") for x in r.get("recommandations", [])]}
            for s, r in results
        ],
        ensure_ascii=False,
    )
    synthese = llm.chat(SYSTEM_SYNTHESE, recap)
    report = build_report(args.pv.name, synthese, results)

    out = args.output or args.pv.with_suffix(".analyse.md")
    out.write_text(report, encoding="utf-8")
    if args.json:
        out.with_suffix(".json").write_text(
            json.dumps([{"section": s, "analyse": {k: v for k, v in r.items() if k != "_passages"}} for s, r in results],
                       ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Rapport écrit : {out}")


if __name__ == "__main__":
    main()