"""Reconstitue l'historique de rédaction d'un acte réel : V1 → email → V2 → email → FINAL (le PDF).

Le PDF déposé est la version finale. On remonte le temps : V2 = le final avec 2-3 finitions
manquantes, V1 = la V2 avec les erreurs de fond d'un premier jet. Les emails entre l'associé et la
collaboratrice (personnages fictifs) relèvent exactement les écarts entre deux versions.
Le modèle de style et de défauts est la catégorie correspondante de legora-files-2026-10-04/
(PV AG - NN V1/V2/V3 + Emails pédagogiques - PV NN).

Tout est marqué « synthétique » et écrit dans historiques/<nom du PDF>/ (ignoré par git).

Génération par Claude (GEN_PROVIDER=claude, défaut) ou Mistral (GEN_PROVIDER=mistral). Les réponses
brutes sont gardées sur disque : relancer ne repaie aucun appel déjà fait.

Usage :
    python generate_history.py "PDF/OVH - Actes du 09-12-2025.pdf"
    python generate_history.py PDF/x.pdf --categorie 13     # force la catégorie (sinon détectée par le LLM)
    python generate_history.py --all PDF --workers 8        # tout le dossier, en parallèle
"""
import argparse
import json
import os
import re
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from datetime import datetime
from pathlib import Path

import chunking
import config
import llm
from ocr import extract_pages

MODELES_DIR = config.BASE_DIR / "legora-files-2026-10-04"
OUT_DIR = config.BASE_DIR / "historiques"
ASSOCIE = ("Antoine Berthier", "a.berthier@cabinet.example", "Avocat associé")
COLLAB = ("Léa Marchand", "l.marchand@cabinet.example", "Avocate collaboratrice")
MENTION = ("[DOCUMENT SYNTHÉTIQUE — version {v} reconstituée de « {pdf} » pour l'entraînement ; "
           "jamais déposée ni signée]")
PROVIDER = os.getenv("GEN_PROVIDER", "claude")
CLAUDE_MODEL = os.getenv("GEN_CLAUDE_MODEL", "claude-opus-5")
CLAUDE_EFFORT = os.getenv("GEN_CLAUDE_EFFORT", "medium")
_PDF_LOCK = threading.Lock()  # PyMuPDF n'est pas thread-safe


class Ignore(Exception):
    """PDF sans historique possible (pas de texte, pas de catégorie legora, refus du modèle)."""


PIED_MAIL = ("\n\n--\nÉchange synthétique généré pour l'entraînement : ne reflète aucune "
             "correspondance réelle.")


# --------------------------------------------------------------------------- #
# Modèles du cabinet (legora)
# --------------------------------------------------------------------------- #
def docx_text(path: Path) -> str:
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    paras = [re.sub(r"<[^>]+>", "", p) for p in xml.split("</w:p>")]
    return "\n".join(p.strip() for p in paras if p.strip())


def categories() -> dict[str, str]:
    """{"13": "Approbation des comptes annuels exercice 2022", ...} d'après les noms de fichiers."""
    out = {}
    for f in MODELES_DIR.glob("PV AG - * V1 *.docx"):
        m = re.match(r"PV AG - (\d+) V1 (.+)\.docx$", f.name)
        if m:  # « … exercice 2022 » : l'année de l'exemple ne doit pas exclure les autres exercices
            out[m.group(1)] = re.sub(r"\s*(exercice\s+)?(19|20)\d{2}$", "", m.group(2)).strip()
    return dict(sorted(out.items()))


def modele(num: str) -> dict[str, str]:
    versions = {v: docx_text(next(MODELES_DIR.glob(f"PV AG - {num} {v} *.docx"))) for v in ("V1", "V2", "V3")}
    versions["emails"] = docx_text(next(MODELES_DIR.glob(f"Emails pédagogiques - PV {num} *.docx")))
    return versions


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
SYSTEM_CATEGORIE = """Tu classes un acte juridique de société dans UNE des catégories suivantes, \
selon l'opération principale qu'il décide :
{liste}
Réponds UNIQUEMENT en JSON : {{"categorie": "NN" ou "aucune", "justification": "une phrase"}}"""

REGLES = """Règles :
- Garde la même structure, les mêmes noms, montants et dates que la version suivante, sauf là où \
tu introduis un défaut. Conserve les « (...) » d'un extrait.
- Chaque défaut doit être exactement corrigé par la version suivante, et les emails ne parlent que \
de ces défauts.
- Les emails sont échangés entre Antoine Berthier (avocat associé) et Léa Marchand (avocate \
collaboratrice), personnages fictifs. N'attribue aucun propos aux dirigeants ni aux associés de la société.
- Français juridique, même ton que les emails de l'exemple. Pas de signature ni d'en-tête dans les corps d'email.
- Les emails ne mentionnent jamais « la V2 », « la version finale » ni l'exemple : l'associé ne connaît \
pas encore la version suivante, il dit ce qu'il attend."""

SYSTEM_V2 = """Tu reconstitues l'historique de rédaction d'un acte de société réel. L'acte FINAL a été \
déposé au greffe. Écris la version V2 qui l'a précédé : un brouillon presque abouti de la \
collaboratrice, auquel il manque encore 2 ou 3 finitions que l'associé a demandées.

On te donne un EXEMPLE du cabinet pour la même catégorie d'acte (V2, V3 finale, emails) : \
inspire-toi du type de défauts et du ton, adaptés à l'acte réel.

""" + REGLES + """

Réponds UNIQUEMENT en JSON :
{"v2": "texte complet de la V2, en une seule chaîne de caractères (sauts de ligne \\n)",
 "defauts": [{"defaut": "ce qui manque ou est imprécis en V2", "correction": "ce que contient le final"}],
 "email_revue_v2": "email d'Antoine à Léa : relève ces défauts et explique comment les corriger",
 "email_envoi_final": "réponse de Léa : corrections faites, version finale jointe",
 "email_validation": "court email d'Antoine qui valide la version finale"}"""

SYSTEM_V1 = """Tu reconstitues l'historique de rédaction d'un acte de société. On te donne la V2 \
de l'acte. Écris la V1 : le premier jet de la collaboratrice, plus court et plus approximatif, \
avec 3 à 5 erreurs de fond que l'associé a relevées (mentions obligatoires absentes, chiffres \
manquants ou faux, résolutions fusionnées, quorum ou majorité non constatés…).

On te donne un EXEMPLE du cabinet pour la même catégorie d'acte (V1, V2, emails) : inspire-toi \
du type d'erreurs et du ton, adaptés à cet acte.

""" + REGLES + """

Réponds UNIQUEMENT en JSON :
{"v1": "texte complet de la V1, en une seule chaîne de caractères (sauts de ligne \\n)",
 "defauts": [{"defaut": "erreur de la V1", "correction": "ce que contient la V2"}],
 "email_revue_v1": "email d'Antoine à Léa : relève ces erreurs, explique pourquoi et comment corriger",
 "email_envoi_v2": "réponse de Léa : liste des corrections faites, V2 jointe"}"""


def _texte(x) -> str:
    """Le LLM renvoie parfois un objet au lieu d'une chaîne : on l'aplatit dans l'ordre."""
    if isinstance(x, dict):
        return "\n\n".join(_texte(v) for v in x.values())
    if isinstance(x, list):
        return "\n\n".join(_texte(v) for v in x)
    return str(x or "").strip()


def _appel(cache: Path, system: str, user: str, schema: dict) -> dict:
    """Réponse brute gardée sur disque : une relance ne repaie pas l'appel."""
    if cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))
    cache.parent.mkdir(parents=True, exist_ok=True)
    res = _llm_json(system, user, schema)
    cache.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


_STR = {"type": "string"}
_DEFAUTS = {"type": "array", "items": _obj({"defaut": _STR, "correction": _STR})}
SCHEMA_CATEGORIE = _obj({"categorie": _STR, "justification": _STR})
SCHEMA_V2 = _obj({"v2": _STR, "defauts": _DEFAUTS, "email_revue_v2": _STR,
                  "email_envoi_final": _STR, "email_validation": _STR})
SCHEMA_V1 = _obj({"v1": _STR, "defauts": _DEFAUTS, "email_revue_v1": _STR, "email_envoi_v2": _STR})

_claude_client = None


def _claude_json(system: str, user: str, schema: dict) -> dict:
    global _claude_client
    if _claude_client is None:
        import anthropic  # clé : ANTHROPIC_API_KEY (chargée depuis .env par config.py)
        _claude_client = anthropic.Anthropic(max_retries=6)
    with _claude_client.beta.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=64000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={"effort": CLAUDE_EFFORT, "format": {"type": "json_schema", "schema": schema}},
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise Ignore("refus du modèle")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("réponse tronquée (max_tokens)")
    return json.loads(next(b.text for b in msg.content if b.type == "text"))


def _llm_json(system: str, user: str, schema: dict) -> dict:
    if PROVIDER == "claude":
        return _claude_json(system, user, schema)
    return llm.chat_json(system, user, temperature=0.4)


def _exemple(m: dict, versions: tuple[str, str]) -> str:
    a, b = versions
    return (f"=== EXEMPLE — {a} ===\n{m[a]}\n\n=== EXEMPLE — {b} ===\n{m[b]}\n\n"
            f"=== EXEMPLE — EMAILS ===\n{m['emails']}")


# --------------------------------------------------------------------------- #
# Génération
# --------------------------------------------------------------------------- #
def acte_info(pdf: Path) -> tuple[str, str, str]:
    """(société, libellé de l'acte, date ISO) ; date du nom de fichier à défaut."""
    with _PDF_LOCK:
        lines, _ = chunking.load_pdf(pdf)
    info = chunking.extract_info(lines, chunking.detect_doc_type(lines), pdf.name) if lines else None
    d = info.date_iso if info and info.date_iso else ""
    if not d:
        m = re.search(r"(\d{2})-(\d{2})-(\d{4})", pdf.name)
        d = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else date.today().isoformat()
    societe = pdf.name.split(" - ")[0].strip()
    return societe, (info.acte if info else "acte"), d


def eml(path: Path, de, a, objet: str, corps: str, quand: date, pdf: Path, version_cible: str) -> None:
    msg = EmailMessage()
    msg["From"] = f"{de[0]} <{de[1]}>"
    msg["To"] = f"{a[0]} <{a[1]}>"
    msg["Subject"] = objet
    msg["Date"] = format_datetime(datetime(quand.year, quand.month, quand.day, 9, 30).astimezone())
    msg["X-Synthetique"] = "oui"
    msg["X-Source-PDF"] = str(pdf)
    msg["X-Version-Cible"] = version_cible
    prenom = de[0].split()[0]
    corps = corps.replace("**", "").strip()
    corps = re.sub(rf"(\n\s*{prenom}\s*)+$", "", corps).strip()  # le LLM signe parfois lui-même
    msg.set_content(corps + f"\n\n{prenom}" + PIED_MAIL)
    path.write_bytes(bytes(msg))


def generate(pdf: Path, num: str | None = None) -> Path:
    with _PDF_LOCK:
        final = "\n\n".join(t for _, t in extract_pages(pdf)).strip()
    if not final:
        raise Ignore("aucun texte extractible")
    cats = categories()

    if num is None:
        liste = "\n".join(f"{k} : {v}" for k, v in cats.items())
        res = _appel(OUT_DIR / "_categories" / f"{pdf.stem}.json",
                     SYSTEM_CATEGORIE.format(liste=liste), final, SCHEMA_CATEGORIE)
        num = str(res.get("categorie", "aucune")).zfill(2)
        print(f"[{pdf.stem}] catégorie {num} ({res.get('justification', '')})")
    if num not in cats:
        raise Ignore(f"pas de modèle legora pour la catégorie « {num} »")
    m = modele(num)

    out = OUT_DIR / pdf.stem
    (out / "mails").mkdir(parents=True, exist_ok=True)
    print(f"[{pdf.stem}] V2…")
    r2 = _appel(out / "_brut_v2.json", SYSTEM_V2,
                f"{_exemple(m, ('V2', 'V3'))}\n\n=== ACTE FINAL RÉEL ===\n{final}", SCHEMA_V2)
    v2 = _texte(r2["v2"])
    print(f"[{pdf.stem}] V1…")
    r1 = _appel(out / "_brut_v1.json", SYSTEM_V1,
                f"{_exemple(m, ('V1', 'V2'))}\n\n=== V2 DE L'ACTE ===\n{v2}", SCHEMA_V1)
    v1 = _texte(r1["v1"])

    (out / "V1.txt").write_text(MENTION.format(v="V1", pdf=pdf.name) + "\n\n" + v1 + "\n", encoding="utf-8")
    (out / "V2.txt").write_text(MENTION.format(v="V2", pdf=pdf.name) + "\n\n" + v2 + "\n", encoding="utf-8")

    societe, acte, d = acte_info(pdf)
    j = date.fromisoformat(d)
    sujet = f"Draft {acte} – {societe}"
    fils = [  # (fichier, de, à, version, corps, jours avant l'acte)
        ("01_revue_v1.eml", ASSOCIE, COLLAB, "v1", r1["email_revue_v1"], 12),
        ("02_envoi_v2.eml", COLLAB, ASSOCIE, "v2", r1["email_envoi_v2"], 10),
        ("03_revue_v2.eml", ASSOCIE, COLLAB, "v2", r2["email_revue_v2"], 6),
        ("04_envoi_final.eml", COLLAB, ASSOCIE, "final", r2["email_envoi_final"], 4),
        ("05_validation.eml", ASSOCIE, COLLAB, "final", r2["email_validation"], 3),
    ]
    for nom, de, a, v, corps, jours in fils:
        eml(out / "mails" / nom, de, a, f"RE: {sujet} – {v}", _texte(corps), j - timedelta(days=jours), pdf, v)

    meta = {
        "synthetique": True,
        "final": str(pdf),
        "categorie": num,
        "categorie_libelle": cats[num],
        "modele": f"legora-files-2026-10-04/PV AG - {num} V1-V3 + Emails pédagogiques - PV {num}",
        "date_acte": d,
        "versions": {"V1": "V1.txt", "V2": "V2.txt", "final": str(pdf)},
        "defauts_v1": r1.get("defauts", []),
        "defauts_v2": r2.get("defauts", []),
        "mails": [f"mails/{f[0]}" for f in fils],
        "modele_llm": CLAUDE_MODEL if PROVIDER == "claude" else config.CHAT_MODEL,
    }
    (out / "historique.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{pdf.stem}] ✓ historique écrit")
    return out


def generate_all(root: Path, workers: int = 8, reverse: bool = False) -> None:
    """`reverse` : ordre inverse, pour lancer un second passage en parallèle d'un premier sans doublons
    (les deux se rejoignent au milieu ; un PDF déjà fait par l'autre est relu depuis le cache)."""
    pdfs = sorted((p for p in root.glob("*.pdf") if not (OUT_DIR / p.stem / "historique.json").is_file()),
                  reverse=reverse)
    print(f"{len(pdfs)} PDF à traiter ({PROVIDER}, {workers} en parallèle)")
    faits, ignores, erreurs = [], [], []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(generate, p): p for p in pdfs}
        for f in as_completed(futs):
            p = futs[f]
            try:
                f.result()
                faits.append(p.name)
            except Ignore as e:
                ignores.append((p.name, str(e)))
                print(f"[{p.stem}] – ignoré : {e}")
            except Exception as e:  # noqa: BLE001  (un PDF en échec n'arrête pas les autres)
                erreurs.append((p.name, f"{type(e).__name__}: {e}"))
                print(f"[{p.stem}] ✗ {type(e).__name__}: {e}")
    rapport = {"faits": sorted(faits), "ignores": sorted(ignores), "erreurs": sorted(erreurs)}
    (OUT_DIR / ("_rapport_inverse.json" if reverse else "_rapport.json")).write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Terminé : {len(faits)} historiques, {len(ignores)} ignorés, {len(erreurs)} erreurs "
          f"(détail : historiques/_rapport.json)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path, nargs="?")
    ap.add_argument("--categorie", default=None, help="numéro de catégorie legora (ex. 13)")
    ap.add_argument("--all", type=Path, default=None, help="dossier de PDF à traiter en entier")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--reverse", action="store_true", help="traite les PDF en ordre inverse (second passage parallèle)")
    a = ap.parse_args()
    if a.all:
        generate_all(a.all, a.workers, a.reverse)
    elif a.pdf:
        try:
            generate(a.pdf, a.categorie)
        except Ignore as e:
            raise SystemExit(f"Ignoré : {e}")
    else:
        ap.error("donner un PDF ou --all DOSSIER")
