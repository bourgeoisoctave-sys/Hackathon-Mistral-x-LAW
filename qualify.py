"""Qualification d'un acte sans API : forme sociale, dénomination, date, nature (AGO / AGE / décision).

Sert au brouillon (pipeline) et à chaque précédent du corpus (corpus_index) pour le classement
des « cas similaires » : même type d'opération, même forme sociale, plus récent, mieux noté.
"""
import re
from datetime import date

FORMES = [
    ("SASU", r"\bSASU\b|soci[ée]t[ée] par actions simplifi[ée]e unipersonnelle"),
    ("SAS", r"\bSAS\b|soci[ée]t[ée] par actions simplifi[ée]e"),
    ("SA", r"\bS\.?A\.?\b(?![A-Z])|soci[ée]t[ée] anonyme"),
    ("SARL", r"\bSARL\b|soci[ée]t[ée] [àa] responsabilit[ée] limit[ée]e"),
    ("EURL", r"\bEURL\b"),
    ("SCA", r"\bSCA\b|soci[ée]t[ée] en commandite par actions"),
    ("SNC", r"\bSNC\b"),
    ("SCI", r"\bSCI\b|soci[ée]t[ée] civile immobili[èe]re"),
    ("GAEC", r"\bGAEC\b"),
    ("SELAS", r"\bSELAS\b"),
    ("SELARL", r"\bSELARL\b"),
    ("SC", r"soci[ée]t[ée] civile\b"),
]
MOIS = {m: i for i, m in enumerate(
    ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"], 1)}
MOIS.update({"fevrier": 2, "aout": 8, "decembre": 12})
DATE_TXT = re.compile(r"\b(\d{1,2}|1er)\s+(" + "|".join(MOIS) + r")\s+(\d{4})\b", re.I)
DATE_NUM = re.compile(r"\b(\d{2})[/.-](\d{2})[/.-](\d{4})\b")


def forme_sociale(text: str) -> str:
    head = text[:4000]
    for code, pattern in FORMES:
        if re.search(pattern, head, re.I):
            return code
    return ""


def denomination(text: str) -> str:
    """Première ligne « parlante » avant la mention de forme / de capital ; sinon la 1re ligne."""
    lines = [ln.strip(" #*") for ln in text.splitlines() if ln.strip(" #*")]
    for ln in lines[:8]:
        if re.search(r"au capital|R\.?C\.?S|si[èe]ge social|proc[èe]s|d[ée]cision|confidential|copyright|classification", ln, re.I):
            continue
        if sum(ch.isdigit() for ch in ln) >= 4 or re.match(r"^[A-Z]{2,}_", ln):  # références de dossier, numéros de page
            continue
        if 2 < len(ln) < 80:
            return ln
    return lines[0][:80] if lines else ""


def date_acte(text: str, fallback_name: str = "") -> str:
    """Date ISO de l'acte : première date du texte (priorité à celles près de « du / en date du »), sinon le nom de fichier."""
    head = text[:6000]
    m = re.search(r"(?:du|en date du|le)\s+" + DATE_TXT.pattern, head, re.I) or DATE_TXT.search(head)
    if m:
        g = m.groups()[-3:]
        d = 1 if g[0].lower() == "1er" else int(g[0])
        try:
            return date(int(g[2]), MOIS[g[1].lower()], d).isoformat()
        except (ValueError, KeyError):
            pass
    m = DATE_NUM.search(head) or DATE_NUM.search(fallback_name)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            pass
    return ""


def nature(text: str) -> str:
    head = text[:3000].lower()
    if re.search(r"extraordinaire|\bage\b", head):
        return "AGE"
    if re.search(r"ordinaire|\bago\b|approbation des comptes", head):
        return "AGO"
    if re.search(r"d[ée]cision[s]? (du|de l'|de la) (pr[ée]sident|associ[ée] unique|g[ée]rant)", head):
        return "DECISION"
    if "assembl" in head:
        return "AG"
    return ""


def qualify(text: str, fallback_name: str = "") -> dict:
    return {"forme": forme_sociale(text), "societe": denomination(text), "date": date_acte(text, fallback_name), "nature": nature(text)}
