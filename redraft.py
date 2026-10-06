"""Correction ciblée d'un brouillon de PV : clauses absentes / partielles réécrites à partir des
précédents du cabinet (cas similaires) et des échanges du dossier, le reste du texte conservé.

    python redraft.py pv.context.json -o corrige.docx       # context.json de pipeline.prepare

Sortie : {texte_corrige, changements[], score_avant, score_apres, inchange_pct} et un .docx où chaque
passage modifié est surligné, suivi d'un journal des modifications sourcé (précédent, email, pratique).
Le LLM ne « génère pas un PV parfait » : il complète les clauses listées, chacune avec sa source.
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path

import analyze
import config
import llm
import scoring
import similar
from ingest import get_collection

SYSTEM = """Tu es un avocat associé en droit des sociétés. On te donne le BROUILLON intégral d'un procès-verbal, \
la liste des CLAUSES À CORRIGER (absentes ou partielles), pour chacune des EXTRAITS DE PRÉCÉDENTS du cabinet \
(rédactions validées sur des opérations comparables), les REVUES DE L'ASSOCIÉ sur ces précédents avec, pour chaque \
défaut relevé, la CORRECTION attendue (ce que le cabinet exige quand il corrige ce type d'acte) et, s'il y en a, des \
ÉCHANGES DU DOSSIER (mails / réunions).

Ta mission : produire le PV corrigé.
Règles strictes :
- Reprends le brouillon INTÉGRALEMENT et dans l'ordre. Ne reformule pas ce qui n'est pas à corriger.
- Pour chaque clause à corriger : insère ou complète le passage au bon endroit, en t'inspirant de la \
rédaction du précédent indiqué, adaptée aux noms, chiffres et dates du brouillon.
- INTERDICTION D'INVENTER : toute donnée (date, délai, montant, nombre d'actions, adresse, e-mail, numéro RCS, \
nom) qui ne figure ni dans le brouillon, ni dans les précédents, ni dans les échanges fournis s'écrit \
[à compléter : nature de la donnée]. Un crochet vaut mieux qu'un chiffre plausible.
- Encadre CHAQUE passage ajouté ou modifié par les balises [[MOD:id_clause]] … [[/MOD]] (une balise par clause, \
le texte du passage à l'intérieur, rien d'autre).
- Pas de commentaire hors du PV.

Réponds UNIQUEMENT en JSON :
{"texte_corrige": "le PV complet avec les balises",
 "changements": [{"id": "id_clause", "resume": "ce qui a été ajouté/modifié en une phrase",
                  "source_precedent": "source du précédent utilisé ou chaîne vide",
                  "source_revue": "acte dont la revue de l'associé a guidé ce changement, ou chaîne vide",
                  "source_email": "citation de l'échange du dossier utilisé ou chaîne vide",
                  "justification": "pourquoi, en une ou deux phrases"}]}"""

MOD_RE = re.compile(r"\[\[MOD:([a-z_]+)\]\](.*?)\[\[/MOD\]\]", re.S)
FACT_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\b\d{1,2}(?:er)?\s+(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4}\b"
                     r"|\b\d{2}/\d{2}/\d{4}\b|\b\d[\d\s.,]{2,}\d\b", re.I)


def _facts(text: str) -> set[str]:
    """Dates, nombres (≥ 3 chiffres), e-mails : les données qu'un rédacteur n'a pas le droit d'inventer."""
    return {re.sub(r"\s", "", m.group(0)).lower() for m in FACT_RE.finditer(text)}


def unsupported_facts(passage: str, *sources: str) -> list[str]:
    """Faits du passage absents de toutes les sources (brouillon, précédents, échanges) → à vérifier."""
    known = set().union(*(_facts(s) for s in sources))
    return sorted(f for f in _facts(passage) if f not in known and not f.isdigit() or (f.isdigit() and f not in known and len(f) >= 3))


def _precedent_passages(clauses: list[dict], cases: list[dict], per_clause: int = 2) -> dict[str, list[dict]]:
    """Pour chaque clause à corriger : les meilleures unités (parents) issues des cas similaires, sinon du corpus."""
    col = get_collection()
    if col.count() == 0:
        return {c["id"]: [] for c in clauses}
    sources_cases = [c["source"] for c in cases]
    out = {}
    for c in clauses:
        where = {"$and": [{"dossier": "general"}, {"source": {"$in": sources_cases}}]} if sources_cases else {"dossier": "general"}
        passages = analyze.retrieve(col, [c["libelle"]], where=where)
        if not passages:
            passages = analyze.retrieve(col, [c["libelle"]], where={"dossier": "general"})
        out[c["id"]] = [{"source": p["meta"]["source"], "page": p["meta"].get("page"), "section": p["meta"].get("section", ""),
                         "texte": p["text"][:1800]} for p in passages[:per_clause]]
    return out


RANG = {"absente": 0, "partielle": 1, "presente": 2}


def merge_states(avant: list[dict], apres: list[dict], modifiees: set[str]) -> list[dict]:
    """États après correction : re-vérification pour les clauses modifiées, max(avant, après) pour les autres."""
    etat_avant = {c["id"]: c["etat"] for c in avant}
    out = []
    for c in apres:
        a = etat_avant.get(c["id"], "absente")
        etat = c["etat"] if c["id"] in modifiees or RANG[c["etat"]] >= RANG[a] else a
        out.append({**c, "etat": etat})
    return out


def redraft(ctx: dict, n_cases: int = 3, cas: dict | None = None) -> dict:
    """`cas` : résultat de similar.similar_cases déjà calculé (sinon calculé ici)."""
    grille = scoring.load_grille()
    attendues = {c["id"]: c for c in grille["types_operation"][ctx["type_operation"]]["clauses"]}
    a_corriger = [{**attendues[d["id"]], "etat": d["etat"], "extrait_pv": d["extrait"]}
                  for d in ctx["clauses_detectees"] if d["etat"] != "presente"]
    if cas is None:
        cas = similar.similar_cases(Path(ctx["pv"]), n_cases, pv_text=ctx["pv_text"], type_operation=ctx["type_operation"])
    passages = _precedent_passages(a_corriger, cas["cas"])
    traces = ctx.get("contexte_dossier", {})

    revues = [{"acte": c["acte_id"], "societe": c["societe"], "version": h["version"], "revue": h["revue"],
               "defauts_releves_et_corrections": h["defauts"]}
              for c in cas["cas"] for h in c.get("historique", [])]
    user = json.dumps({
        "brouillon": ctx["pv_text"],
        "revues_associe_cas_similaires": revues,
        "clauses_a_corriger": [
            {"id": c["id"], "libelle": c["libelle"], "etat": c["etat"], "pourquoi": c["pourquoi"], "extrait_actuel": c["extrait_pv"],
             "precedents": passages[c["id"]],
             "echanges_dossier": [{"citation": t["citation"], "texte": t["text"][:500]} for t in traces.get(c["id"], [])[:2]]}
            for c in a_corriger
        ],
    }, ensure_ascii=False)
    res = llm.chat_json(SYSTEM, user, temperature=0.2)

    texte = str(res.get("texte_corrige", "")).strip()
    mods = {m.group(1): m.group(2).strip() for m in MOD_RE.finditer(texte)}
    texte_propre = MOD_RE.sub(lambda m: m.group(2), texte)

    # Taux de texte du brouillon conservé tel quel (garde-fou contre une réécriture globale).
    brouillon_paras = [p.strip() for p in ctx["pv_text"].split("\n") if p.strip()]
    corrige_paras = [p.strip() for p in texte_propre.split("\n") if p.strip()]
    sm = difflib.SequenceMatcher(None, brouillon_paras, corrige_paras, autojunk=False)
    inchange = sum(b.size for b in sm.get_matching_blocks())
    inchange_pct = round(100 * inchange / max(1, len(brouillon_paras)))

    sources_connues = [ctx["pv_text"]] + [p["texte"] for ps in passages.values() for p in ps] \
        + [t["text"] for ts in traces.values() for t in ts] + [r["revue"] for r in revues] \
        + [d["correction"] for r in revues for d in r["defauts_releves_et_corrections"]]
    changements = []
    for ch in res.get("changements", []) or []:
        cid = str(ch.get("id", ""))
        if cid not in attendues:
            continue
        texte_mod = mods.get(cid, "")
        changements.append({"id": cid, "libelle": attendues[cid]["libelle"], "etat_avant": next((c["etat"] for c in a_corriger if c["id"] == cid), ""),
                            "texte": texte_mod, "resume": str(ch.get("resume", "")), "source_precedent": str(ch.get("source_precedent", "")),
                            "source_revue": str(ch.get("source_revue", "")), "source_email": str(ch.get("source_email", "")),
                            "justification": str(ch.get("justification", "")),
                            "a_verifier": unsupported_facts(texte_mod, *sources_connues)})

    # Score après : mêmes règles, sur le texte corrigé. Une clause que la correction n'a pas touchée
    # ne peut pas être jugée pire qu'avant (bruit du vérificateur LLM) ; les clauses modifiées sont re-vérifiées.
    clauses = grille["types_operation"][ctx["type_operation"]]["clauses"]
    checks_apres = merge_states(ctx["clauses_detectees"], scoring.check_clauses(texte_propre, clauses), {c["id"] for c in changements})
    score_apres = scoring.compute_score(checks_apres, clauses, ctx["exigence"], grille)

    return {"texte_corrige": texte_propre, "texte_balise": texte, "changements": changements, "cas_similaires": cas["cas"],
            "brouillon_qualifie": cas["brouillon"], "score_avant": ctx["score"], "score_apres": score_apres, "inchange_pct": inchange_pct}


def to_docx(result: dict, ctx: dict, out: Path) -> Path:
    """PV corrigé : passages modifiés surlignés, puis journal des modifications."""
    import docx
    from docx.enum.text import WD_COLOR_INDEX
    from docx.shared import Pt

    d = docx.Document()
    style = d.styles["Normal"]; style.font.name = "Calibri"; style.font.size = Pt(11)
    pos = 0
    for m in MOD_RE.finditer(result["texte_balise"]):
        for para in result["texte_balise"][pos:m.start()].split("\n"):
            if para.strip():
                d.add_paragraph(para.strip())
        for para in m.group(2).strip().split("\n"):
            if para.strip():
                run = d.add_paragraph().add_run(para.strip()); run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        pos = m.end()
    for para in result["texte_balise"][pos:].split("\n"):
        if para.strip():
            d.add_paragraph(para.strip())

    d.add_page_break()
    d.add_heading("Journal des modifications", level=1)
    d.add_paragraph(f"Score avant : {result['score_avant']['final']}/100 · après : {result['score_apres']['final']}/100 "
                    f"(exigence {ctx['exigence']}). {result['inchange_pct']} % du brouillon conservé tel quel.")
    for ch in result["changements"]:
        d.add_heading(ch["libelle"], level=2)
        d.add_paragraph(ch["resume"])
        if ch["justification"]:
            d.add_paragraph("Pourquoi : " + ch["justification"])
        if ch["source_precedent"]:
            d.add_paragraph("Précédent : " + ch["source_precedent"])
        if ch.get("source_revue"):
            d.add_paragraph("Revue de l'associé (historique reconstitué, synthétique) : " + ch["source_revue"])
        if ch["source_email"]:
            d.add_paragraph("Échange du dossier : " + ch["source_email"])
        if ch.get("a_verifier"):
            run = d.add_paragraph().add_run("À vérifier (donnée absente du brouillon et des sources) : " + ", ".join(ch["a_verifier"]))
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
    d.add_heading("Cas similaires consultés", level=1)
    for c in result["cas_similaires"]:
        d.add_paragraph(f"{c['societe']} · {c['forme'] or '?'} · {c['date'] or '?'} · couverture {c['brut']}/100 — {c['source']}")
    d.save(str(out))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("context", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("-n", type=int, default=3)
    a = ap.parse_args()
    ctx = json.loads(a.context.read_text(encoding="utf-8"))
    res = redraft(ctx, a.n)
    out = a.output or a.context.with_suffix(".corrige.docx")
    to_docx(res, ctx, out)
    a.context.with_suffix(".redraft.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Score {res['score_avant']['final']} → {res['score_apres']['final']} · {res['inchange_pct']} % conservé · "
          f"{len(res['changements'])} changements · {out}", file=sys.stderr)
    for ch in res["changements"]:
        flag = f"  ⚠ à vérifier : {', '.join(ch['a_verifier'])}" if ch["a_verifier"] else ""
        print(f"  - {ch['libelle']}: {ch['resume'][:90]}{flag}", file=sys.stderr)


if __name__ == "__main__":
    main()
