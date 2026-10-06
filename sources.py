"""Normalisation de format, en amont du découpage : chaque fichier devient des Documents
{texte, meta}. Le nettoyage de contenu et le préfixe de citation se font après, par chunk.

Formats : .pdf (couche texte ou OCR, un document par page), .eml (mail), .txt / .md
(transcript de réunion ou note), .docx (modèle, PV, ou fil d'emails découpé par « De : »). Métadonnées communes, toutes scalaires (contrainte Chroma) :
    source, page, categorie, dossier, source_type (document|mail|reunion|note), date, auteur, titre
"""
import re
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path

from ocr import extract_pages

REUNION_RE = re.compile(r"reunion|réunion|call|meeting|transcript|visio", re.I)
DATE_RE = re.compile(r"(20\d{2})[-_](\d{2})[-_](\d{2})")
EXTENSIONS = {".pdf", ".eml", ".txt", ".md", ".docx"}
EMAILS_DOC_RE = re.compile(r"^emails?\b|^échanges internes|^echanges internes", re.I)
# Bandeau des dossiers de formation : ne doit jamais atteindre le modèle (il contient la note).
# En-tête des brouillons reconstitués par generate_history.py (V1.txt / V2.txt).
VERSION_RE = re.compile(r"^\[DOCUMENT SYNTHÉTIQUE — version (V\d+) reconstituée de « (.+?) »")
BANNER_RE = re.compile(r"DOSSIER DE FORMATION|Exemple pédagogique|Feedback associé|Note auteur|Niveau :|Cohérence :|ne pas reproduire|à corriger avant utilisation", re.I)


def _meta(rel: Path, dossier: str, **extra) -> dict:
    base = {
        "source": str(rel),
        "page": 0,
        "categorie": rel.parts[0] if len(rel.parts) > 1 else "general",
        "dossier": dossier,
        "source_type": "document",
        "date": "",
        "auteur": "",
        "titre": rel.stem,
        "acte_id": "",   # nom du PDF final auquel la pièce se rattache (historiques synthétiques)
        "version": "",   # V1, V2… pour un brouillon ; v1/v2/final pour le mail qui le revoit
    }
    base.update({k: v for k, v in extra.items() if v is not None})
    return base


def _date_from_name(name: str) -> str:
    m = DATE_RE.search(name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def load_pdf(path: Path, rel: Path, dossier: str) -> list[dict]:
    return [{"text": t, "meta": _meta(rel, dossier, page=n)} for n, t in extract_pages(path)]


def load_eml(path: Path, rel: Path, dossier: str) -> list[dict]:
    msg = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    body = msg.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body else ""
    if body and body.get_content_type() == "text/html":
        text = re.sub(r"<[^>]+>", " ", text)
    date = ""
    if msg["date"]:
        try:
            date = parsedate_to_datetime(msg["date"]).date().isoformat()
        except (TypeError, ValueError):
            date = ""
    text = f"Objet : {msg['subject'] or ''}\n\n{text.strip()}"
    pdf = str(msg["X-Source-PDF"] or "")
    return [{"text": text, "meta": _meta(rel, dossier, page=1, source_type="mail", date=date,
                                         auteur=str(msg["from"] or ""), titre=str(msg["subject"] or rel.stem),
                                         acte_id=Path(pdf).stem if pdf else "",
                                         version=str(msg["X-Version-Cible"] or ""))}]


def load_text(path: Path, rel: Path, dossier: str) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    m = VERSION_RE.match(text)
    if m:  # brouillon reconstitué : on retire l'en-tête, on garde le lien vers le PDF final
        body = text.split("\n", 1)[1].strip() if "\n" in text else ""
        acte = Path(m.group(2)).stem
        return [{"text": body, "meta": _meta(rel, dossier, page=1, source_type="version", version=m.group(1),
                                             acte_id=acte, titre=f"{acte} {m.group(1)}")}]
    kind = "reunion" if REUNION_RE.search(str(rel)) else "note"
    return [{"text": text, "meta": _meta(rel, dossier, page=1, source_type=kind, date=_date_from_name(str(rel)))}]


def strip_training_banner(text: str) -> str:
    """Retire les lignes du bandeau « DOSSIER DE FORMATION … » (version, niveau, note, feedback)."""
    return "\n".join(ln for ln in text.splitlines() if not BANNER_RE.search(ln)).strip()


def docx_text(path: Path) -> str:
    """Texte d'un .docx : paragraphes puis tableaux (une ligne par rangée, cellules séparées par « | »)."""
    import docx  # python-docx, importé à la demande

    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def split_emails(text: str) -> list[dict]:
    """Découpe un fil « De : … / À : … / Objet : … » en mails ; [] si le texte n'en a pas la forme."""
    starts = [m.start() for m in re.finditer(r"^De\s*:", text, re.M)]
    if len(starts) < 2:
        return []
    mails = []
    for i, start in enumerate(starts):
        block = text[start: starts[i + 1] if i + 1 < len(starts) else len(text)].strip()
        de = re.search(r"^De\s*:\s*(.+)$", block, re.M)
        objet = re.search(r"^Objet\s*:\s*(.+)$", block, re.M)
        body = re.sub(r"^(De|À|A|Objet)\s*:.*$", "", block, flags=re.M).strip()
        if len(body) < 40:  # en-tête répété sans corps (le .docx redonde la première ligne)
            continue
        mails.append({"auteur": (de.group(1) if de else "").strip(), "titre": (objet.group(1) if objet else "").strip(),
                      "text": f"Objet : {objet.group(1).strip() if objet else ''}\n\n{body}"})
    return mails


def load_docx(path: Path, rel: Path, dossier: str) -> list[dict]:
    text = strip_training_banner(docx_text(path))
    if EMAILS_DOC_RE.search(rel.stem) or text.count("Objet :") >= 2:
        mails = split_emails(text)
        if mails:
            return [{"text": m["text"], "meta": _meta(rel, dossier, page=i, source_type="mail", auteur=m["auteur"],
                                                      titre=m["titre"] or rel.stem, date=_date_from_name(str(rel)))}
                    for i, m in enumerate(mails, start=1)]
    kind = "reunion" if REUNION_RE.search(str(rel)) else "document"
    return [{"text": text, "meta": _meta(rel, dossier, page=1, source_type=kind, date=_date_from_name(str(rel)))}]


LOADERS = {".pdf": load_pdf, ".eml": load_eml, ".txt": load_text, ".md": load_text, ".docx": load_docx}


def load(path: Path, root: Path, dossier: str = "general") -> list[dict]:
    """Un fichier → liste de Documents (vide si rien d'extractible)."""
    loader = LOADERS.get(path.suffix.lower())
    if loader is None:
        return []
    return [d for d in loader(path, path.relative_to(root), dossier) if d["text"].strip()]


def iter_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS)


# --- après le découpage : nettoyage et préfixe de citation --------------------------------
def clean_chunk(text: str) -> str:
    """Retire les lignes citées des mails (« > ») et les tics d'oral ; "" si rien ne reste."""
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith(">")]
    text = "\n".join(lines)
    text = re.sub(r"\b(euh+|hum+|hein)\b[,.]?\s*", "", text, flags=re.I)
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text


def label(meta: dict) -> str:
    """Préfixe embarqué avec le chunk : c'est ce que la réponse finale pourra citer."""
    kind, date, auteur, titre = meta["source_type"], meta["date"], meta["auteur"], meta["titre"]
    if kind == "mail":
        return f"Mail de {auteur}, {date} — {titre}".replace(", —", " —")
    if kind == "reunion":
        return f"Réunion {date} — {titre}".replace("Réunion  —", "Réunion —")
    if kind == "version":
        return f"Brouillon {meta['version']} — {meta['acte_id']}"
    if kind == "note":
        return f"Note {date} — {titre}".replace("Note  —", "Note —")
    return f"{titre} (p.{meta['page']})"
