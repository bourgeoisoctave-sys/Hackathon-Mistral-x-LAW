"""Découpage structurel des documents d'entreprise (actes, PV, traités, guides).

Principe : une unité de découpage = une unité juridique (décision, résolution, article),
pas un nombre de caractères. Les tableaux sont extraits à part. Chaque chunk reçoit un
préfixe de contexte et des métadonnées, et pointe vers un « parent » (l'unité entière)
que l'agent lira à la place du petit chunk retrouvé.

Aperçu sans API :
    python chunking.py mon_acte.pdf              # liste les chunks
    python chunking.py mon_acte.pdf --full       # affiche aussi leur texte
"""
from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

import config

# --------------------------------------------------------------------------- #
# Structures
# --------------------------------------------------------------------------- #
TABLE_MARK = "\x00TABLE:"


@dataclass
class Line:
    text: str
    page: int


@dataclass
class Block:
    text: str
    page: int
    kind: str = "p"  # "p" (texte) ou "table"


@dataclass
class Table:
    page: int
    caption: str
    rows: list[list[str]]


@dataclass
class Section:
    level: int
    num: str
    title: str
    path: str
    label: str  # ligne de titre affichée en tête de l'unité
    lines: list[Line]
    page: int
    top: str | None = None  # n° d'article de niveau 1 (pour regrouper les sous-articles)
    merge_ok: bool = False  # peut être regroupée avec ses voisines (articles numérotés)
    annex: bool = False

    def body_chars(self) -> int:
        return sum(len(l.text.strip()) for l in self.lines if not l.text.startswith(TABLE_MARK))

    def absorb(self, other: "Section") -> None:
        if self.body_chars() == 0 and not any(l.text.startswith(TABLE_MARK) for l in self.lines):
            self.path, self.num = other.path, other.num
        extra = [Line("", other.page)]
        if other.label:
            extra += [Line(other.label, other.page), Line("", other.page)]
        self.lines += extra + other.lines


@dataclass
class DocInfo:
    source: str
    doc_type: str
    societe: str = ""
    acte: str = ""
    date_texte: str = ""
    date_iso: str = ""


@dataclass
class Chunk:
    id: str
    text: str
    contexte: str
    parent_id: str
    parent_text: str
    meta: dict = field(default_factory=dict)

    @property
    def embed_text(self) -> str:
        return f"{self.contexte}\n{self.text}"


# --------------------------------------------------------------------------- #
# 1. Lecture et nettoyage du PDF
# --------------------------------------------------------------------------- #
NOISE_LINE = re.compile(r"^\s*(Docusign Envelope ID:.*|ACTIVE/\d+\.\d+|Page\s+\d+\s*(/|sur)\s*\d+)\s*$", re.I)
DOT_LEADER = re.compile(r"(\.{4,}|…{3,})\s*\d+\s*$")


def _inside(block, bbox, pad=1.5) -> bool:
    cx, cy = (block[0] + block[2]) / 2, (block[1] + block[3]) / 2
    return bbox[0] - pad <= cx <= bbox[2] + pad and bbox[1] - pad <= cy <= bbox[3] + pad


def _clean_cell(c) -> str:
    return re.sub(r"\s+", " ", (c or "").replace("\n", " ")).strip()


NUMERIC = re.compile(r"^[-–−+]?\s*\(?[\d\s.,/]+\)?\s*(%|k€|€)?$|^n/?a$", re.I)


def _table_rows(raw) -> list[list[str]]:
    """Nettoie un tableau PDF : cellules fusionnées / lignes de continuation / colonnes vides."""
    rows = [[_clean_cell(c) for c in r] for r in raw]
    rows = [r for r in rows if any(r)]
    if not rows:
        return []
    # 1. une cellule multi-lignes fusionnée est parfois éclatée en plusieurs lignes : on la recolle
    merged: list[list[str]] = []
    for r in rows:
        ne = [j for j, c in enumerate(r) if c]
        if merged:
            p = merged[-1]
            pe = [j for j, c in enumerate(p) if c]
            if len(pe) >= 2 and 0 < len(ne) < len(pe) and all(j < len(p) and p[j] for j in ne) \
                    and not any(NUMERIC.match(r[j]) for j in ne):
                for j in ne:
                    p[j] = f"{p[j]} {r[j]}"
                continue
        merged.append(list(r))
    # 2. les colonnes de fusion laissent des trous : on ne garde que les cellules non vides, dans l'ordre
    return [[c for c in r if c] for r in merged]


def table_markdown(rows: list[list[str]], header_only: bool = False) -> str:
    n = max(len(r) for r in rows)
    pad = lambda r: r + [""] * (n - len(r))  # noqa: E731
    out = ["| " + " | ".join(pad(rows[0])) + " |", "|" + "---|" * n]
    if not header_only:
        out += ["| " + " | ".join(pad(r)) + " |" for r in rows[1:]]
    return "\n".join(out)


def load_pdf(path: Path) -> tuple[list[Line], list[Table]]:
    """Retourne les lignes dans l'ordre de lecture (avec marqueurs de tableaux)."""
    lines: list[Line] = []
    tables: list[Table] = []
    with pymupdf.open(path) as doc:
        for pno, page in enumerate(doc, start=1):
            page_tables = []
            try:
                for t in page.find_tables().tables:
                    rows = _table_rows(t.extract())
                    if len(rows) >= 2 and len(rows[0]) >= 2:
                        page_tables.append((t.bbox, rows))
            except Exception:  # noqa: BLE001
                pass

            items = []  # (y, kind, payload)
            h = page.rect.height
            for b in page.get_text("blocks", sort=True):
                if b[6] != 0 or any(_inside(b, bb) for bb, _ in page_tables):
                    continue
                txt = b[4]
                # numéro de page isolé en haut ou en bas de page
                if re.fullmatch(r"\d{1,3}", txt.strip()) and (b[1] < 70 or b[3] > h - 70):
                    continue
                kept = [l for l in txt.split("\n") if not NOISE_LINE.match(l)]
                if any(l.strip() for l in kept):
                    items.append((b[1], "text", kept))
            for bb, rows in page_tables:
                items.append((bb[1], "table", rows))
            items.sort(key=lambda x: x[0])

            page_lines: list[Line] = []
            last_text = ""
            for _, kind, payload in items:
                if kind == "text":
                    page_lines += [Line(l.rstrip(), pno) for l in payload] + [Line("", pno)]
                    last_text = " ".join(l.strip() for l in payload if l.strip())
                else:
                    cap = last_text[-250:]
                    if len(last_text) > 250:
                        cap = "… " + cap[cap.find(" ") + 1:]
                    tables.append(Table(pno, cap, payload))
                    page_lines += [Line(f"{TABLE_MARK}{len(tables) - 1}", pno), Line("", pno)]
                    last_text = ""

            # page de table des matières : points de suite répétés → on l'écarte
            if sum(1 for l in page_lines if DOT_LEADER.search(l.text)) >= 4:
                continue
            lines += [l for l in page_lines if not DOT_LEADER.search(l.text)]
    return lines, tables


# --------------------------------------------------------------------------- #
# 2. Détection du type de document et métadonnées
# --------------------------------------------------------------------------- #
ORD_HEADING = re.compile(
    r"^(PREMI[ÈE]RE|SECONDE|DERNI[ÈE]RE|(?:[A-ZÉÈÂÛ]+[ -])*[A-ZÉÈÂÛ]*I[ÈE]ME)\s+(D[ÉE]CISION|R[ÉE]SOLUTION)\s*$",
    re.I,
)
NUM_HEADING = re.compile(r"^(\d{1,2}\.|\d{1,2}(?:\.\d{1,2}){1,3}\.?)$")
MONTHS = {m: i for i, m in enumerate(
    ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
     "septembre", "octobre", "novembre", "décembre"], start=1)}
DATE_RE = re.compile(r"\b(\d{1,2})(?:er)?\s+(" + "|".join(MONTHS) + r")\s+(\d{4})\b", re.I)


def _next_nonblank(lines: list[Line], i: int, end: int | None = None) -> int | None:
    end = len(lines) if end is None else end
    j = i + 1
    while j < end and not lines[j].text.strip():
        j += 1
    return j if j < end else None


def find_numbered_heads(lines: list[Line]) -> list[tuple[int, str, int]]:
    """[(index, numéro, niveau)] pour les titres numérotés « 4. » / « 4.2 » placés sur leur ligne."""
    heads, cur_top = [], 0
    for i, l in enumerate(lines):
        s = l.text.strip()
        m = NUM_HEADING.match(s)
        if not m:
            continue
        j = _next_nonblank(lines, i)
        if j is None:
            continue
        nxt = lines[j].text.strip()
        if NUM_HEADING.match(nxt) or nxt.startswith(TABLE_MARK):
            continue
        parts = [p for p in s.split(".") if p]
        level = len(parts)
        if level == 1:
            n = int(parts[0])
            letters = re.sub(r"[^A-Za-zÀ-ÿ]", "", nxt)
            if not (nxt.isupper() and len(letters) >= 4 and cur_top < n <= cur_top + 3):
                continue
            cur_top = n
        else:
            if int(parts[0]) != cur_top or not nxt[:1].isupper() or len(nxt) > 160:
                continue
        heads.append((i, ".".join(parts), level))
    return heads


def detect_doc_type(lines: list[Line]) -> str:
    head = "\n".join(l.text for l in lines[:150])
    ords = [ORD_HEADING.match(l.text.strip()) for l in lines if len(l.text.strip()) < 60]
    ords = [m for m in ords if m]
    n_num = len(find_numbered_heads(lines))
    if re.search(r"D[ÉE]CISIONS?\s+DU\s+PR[ÉE]SIDENT", head, re.I) and ords:
        return "decision_president"
    if ords and (any(m.group(2).upper().startswith("R") for m in ords)
                 or re.search(r"PROC[ÈE]S-VERBAL\s+(DE\s+L['’]|DES\s+D[ÉE]LIB)", head, re.I)):
        return "pv_ag"
    if ords:
        return "decision_associes"
    if re.search(r"TRAIT[ÉE]\s+DE\s+(SCISSION|FUSION|APPORT)", head, re.I) and n_num >= 3:
        return "traite"
    if n_num >= 5:
        return "document_structure"
    return "generic"


ACTE_LABEL = {
    "decision_president": "décision du Président",
    "decision_associes": "décision des associés",
    "pv_ag": "procès-verbal d'assemblée générale",
}


def _date(text: str) -> tuple[str, str]:
    m = DATE_RE.search(text)
    if not m:
        return "", ""
    d, mo, y = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    return f"{d} {mo} {y}", f"{y:04d}-{MONTHS[mo]:02d}-{d:02d}"


def extract_info(lines: list[Line], doc_type: str, source: str) -> DocInfo:
    info = DocInfo(source=source, doc_type=doc_type)
    first = [l.text.strip() for l in lines[:80]]
    head = "\n".join(first)

    if doc_type in ACTE_LABEL:
        info.acte = ACTE_LABEL[doc_type]
        m = re.search(r"EN\s+DATE\s+DU\s+(.{5,40}?\d{4})", head, re.I | re.S)
        info.date_texte, info.date_iso = _date(m.group(1) if m else head)
    elif doc_type == "traite":
        m = re.search(r"PROJET\s+DE\s+(TRAIT[ÉE]\s+DE\s+[A-ZÉÈ ]+?)\s*(?:\n|$)", head, re.I)
        info.acte = (m.group(1).lower() if m else "traité")
        info.date_texte, info.date_iso = _date(head)
    else:
        info.acte = Path(source).stem
        info.date_texte, info.date_iso = _date(head)

    names: list[str] = []
    non_blank = [s for s in first if s]
    for k, s in enumerate(non_blank):
        if re.match(r"^(Société|Societe)\s+(par actions|anonyme|à responsabilité)", s, re.I) and k > 0:
            names.append(non_blank[k - 1])
            break
        if re.match(r"^\(en qualité d", s, re.I) and k > 0:
            names.append(non_blank[k - 1])
    valid = [n for n in names if re.search(r"[A-Za-z]", n) and len(n) < 80]
    info.societe = ", ".join(list(dict.fromkeys(valid))[:3])
    return info


# --------------------------------------------------------------------------- #
# 3. Découpage en sections (unités juridiques)
# --------------------------------------------------------------------------- #
ORD_TITLE_STOP = re.compile(r"^(Le Président|Les Associés|L['’]Assemblée|La Société|Le Directeur|Après|Connaissance)", re.I)


def split_ordinal(lines: list[Line]) -> list[Section]:
    idxs = [i for i, l in enumerate(lines) if len(l.text.strip()) < 60 and ORD_HEADING.match(l.text.strip())]
    sections: list[Section] = []
    pre = lines[: idxs[0]] if idxs else lines
    sections.append(Section(0, "", "Préambule", "Préambule", "", pre, pre[0].page if pre else 1))
    for k, i in enumerate(idxs):
        end = idxs[k + 1] if k + 1 < len(idxs) else len(lines)
        m = ORD_HEADING.match(lines[i].text.strip())
        num = f"{m.group(1).upper()} {m.group(2).upper()}"
        j = i + 1
        while j < end and not lines[j].text.strip():
            j += 1
        title_lines: list[str] = []
        t = j
        while t < end and lines[t].text.strip() and len(title_lines) < 4 \
                and not ORD_TITLE_STOP.match(lines[t].text.strip()) \
                and not lines[t].text.startswith(TABLE_MARK):
            title_lines.append(lines[t].text.strip())
            t += 1
            # un titre coupé par un saut de bloc : « …huitième, » puis « neuvième et… »
            nb = _next_nonblank(lines, t - 1, end)
            if nb is not None and nb > t and title_lines[-1].endswith(",") and lines[nb].text.strip()[:1].islower():
                t = nb
        title = " ".join(title_lines)
        if not title or len(title) > 220 or title.endswith((",", ";", ":")):
            title, t = "", j
        label = f"{num} — {title}" if title else num
        sections.append(Section(1, num, title, label, label, lines[t:end], lines[i].page))
    return sections


ANNEX_HEAD = re.compile(r"^Annexe\s+[0-9A-Za-z][0-9A-Za-z.()]*$", re.I)


def find_annex_heads(lines: list[Line]) -> list[tuple[int, str, str]]:
    """[(index, numéro, titre)] : « LISTE DES ANNEXES » puis « Annexe 4.2(b) » + ligne de titre."""
    out: list[tuple[int, str, str]] = []
    for i, l in enumerate(lines):
        s = l.text.strip()
        if re.fullmatch(r"LISTE DES ANNEXES", s, re.I):
            out.append((i, "Annexes", "Liste des annexes"))
        elif ANNEX_HEAD.match(s) and len(s) < 40:
            j = _next_nonblank(lines, i)
            title = lines[j].text.strip() if j is not None and len(lines[j].text.strip()) <= 160 \
                and not lines[j].text.startswith(TABLE_MARK) else ""
            if out and out[-1][1].lower() == s.lower():  # en-tête répété sur chaque page
                continue
            out.append((i, s, title))
    return out


def split_numbered(lines: list[Line]) -> list[Section]:
    annexes = find_annex_heads(lines)
    cut = annexes[0][0] if annexes else len(lines)
    heads = [h for h in find_numbered_heads(lines) if h[0] < cut]
    sections: list[Section] = []
    first = heads[0][0] if heads else cut
    pre = lines[:first]
    sections.append(Section(0, "", "Préambule", "Préambule", "", pre, pre[0].page if pre else 1))
    stack: list[tuple[int, str, str]] = []
    for k, (i, num, level) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else cut
        j = _next_nonblank(lines, i, end)
        title_lines, t = [], (j if j is not None else end)
        if j is not None:
            title_lines.append(lines[j].text.strip())
            t = j + 1
            if level == 1:
                while t < end and lines[t].text.strip().isupper() and len(title_lines) < 3 \
                        and not NUM_HEADING.match(lines[t].text.strip()):
                    title_lines.append(lines[t].text.strip())
                    t += 1
        title = " ".join(title_lines)
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, num, title))
        path = " > ".join(f"{n}. {tt}" if lv == 1 else f"{n} {tt}" for lv, n, tt in stack)
        label = f"{num}. {title}" if level == 1 else f"{num} {title}"
        sections.append(Section(level, num, title, path, label, lines[t:end], lines[i].page,
                                top=num.split(".")[0], merge_ok=True))
    for k, (i, num, title) in enumerate(annexes):
        end = annexes[k + 1][0] if k + 1 < len(annexes) else len(lines)
        t = i + 1
        if title:
            j = _next_nonblank(lines, i)
            t = (j + 1) if j is not None else t
        label = f"{num} — {title}" if title else num
        sections.append(Section(1, num, title, label, label, lines[t:end], lines[i].page, annex=True))
    return sections


def split_generic(lines: list[Line], title: str) -> list[Section]:
    return [Section(0, "", title, title, "", lines, lines[0].page if lines else 1)]


def merge_small(sections: list[Section], min_chars: int) -> list[Section]:
    """Regroupe les sous-articles trop courts avec leur article parent / voisin."""
    out: list[Section] = []
    for s in sections:
        if out and s.merge_ok and out[-1].merge_ok and s.top == out[-1].top and s.body_chars() < min_chars:
            out[-1].absorb(s)
        else:
            out.append(s)
    i = 0
    while i < len(out) - 1:  # tête d'article vide ou minuscule → absorbe la suite
        a, b = out[i], out[i + 1]
        if a.merge_ok and b.merge_ok and a.top == b.top and a.body_chars() < min_chars:
            a.absorb(b)
            del out[i + 1]
        else:
            i += 1
    return out


# --------------------------------------------------------------------------- #
# 4. Blocs, découpage des unités trop longues
# --------------------------------------------------------------------------- #
BULLET = re.compile(r"^(?:([-−–•▪])|(\(\w{1,4}\)|\d{1,2}\)|[a-z]\)))\s*(.*)$")


def reflow(lines: list[Line]) -> list[Block]:
    """Regroupe les lignes en blocs : un paragraphe ou une puce = un bloc."""
    blocks: list[Block] = []
    cur: Block | None = None

    def flush():
        nonlocal cur
        if cur is not None and cur.text.strip():
            blocks.append(cur)
        cur = None

    for ln in lines:
        s = ln.text.strip()
        if not s:
            if cur is not None and cur.text in ("-", ):  # puce isolée : le texte suit
                continue
            flush()
            continue
        if s.startswith(TABLE_MARK):
            flush()
            blocks.append(Block(s, ln.page, "table"))
            continue
        m = BULLET.match(s)
        if m:
            flush()
            marker = "-" if m.group(1) else m.group(2)
            cur = Block(f"{marker} {m.group(3)}".rstrip() if m.group(3) else marker, ln.page)
        elif cur is None:
            cur = Block(s, ln.page)
        else:
            cur.text += " " + s
    flush()
    return blocks


def _split_sentences(b: Block, max_chars: int) -> list[Block]:
    out: list[Block] = []
    cur = ""
    for p in re.split(r"(?<=[.;:!?])\s+", b.text):
        while len(p) > max_chars:  # phrase sans ponctuation : coupe sur un espace
            if cur:
                out.append(Block(cur, b.page))
                cur = ""
            cut = p.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            out.append(Block(p[:cut], b.page))
            p = p[cut:].lstrip()
        if cur and len(cur) + 1 + len(p) > max_chars:
            out.append(Block(cur, b.page))
            cur = p
        else:
            cur = f"{cur} {p}".strip()
    if cur:
        out.append(Block(cur, b.page))
    return out


def pack(blocks: list[Block], max_chars: int, overlap: int) -> list[tuple[str, int]]:
    """Assemble des blocs en chunks ≤ max_chars. Chevauchement uniquement entre morceaux d'une même unité."""
    pieces: list[Block] = []
    for b in blocks:
        pieces += [b] if len(b.text) <= max_chars else _split_sentences(b, max_chars)
    chunks: list[tuple[str, int]] = []
    cur: list[str] = []
    cur_len, cur_page = 0, None
    for p in pieces:
        add = len(p.text) + (2 if cur else 0)
        if cur and cur_len + add > max_chars:
            text = "\n\n".join(cur)
            chunks.append((text, cur_page))
            tail = text[-overlap:] if overlap else ""
            tail = tail[tail.find(" ") + 1:] if tail and " " in tail else tail
            cur, cur_len, cur_page = ([f"… {tail}"] if tail else []), (len(tail) + 2 if tail else 0), p.page
            add = len(p.text) + (2 if cur else 0)
        if cur_page is None:
            cur_page = p.page
        cur.append(p.text)
        cur_len += add
    if cur:
        chunks.append(("\n\n".join(cur), cur_page))
    return chunks


# --------------------------------------------------------------------------- #
# 5. Construction des chunks
# --------------------------------------------------------------------------- #
def _hash(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()


def _ocr_lines(path: Path) -> list[Line]:
    """PDF scanné : texte des pages via Mistral OCR (ocr.py, avec cache), sans tableaux détectés."""
    import ocr

    lines: list[Line] = []
    for pno, text in ocr.ocr_pages(path):
        lines += [Line(l.rstrip(), pno) for l in text.splitlines()] + [Line("", pno)]
    return lines


def build_chunks(path: Path, source: str, doc_type: str | None = None, categorie: str = "general",
                 dossier: str = "general", allow_ocr: bool = True):
    """`allow_ocr=False` : un scan est ignoré au lieu d'appeler Mistral OCR (simulation sans API)."""
    lines, tables = load_pdf(path)
    if allow_ocr and not any(l.text.strip() for l in lines):
        lines, tables = _ocr_lines(path), []
    if not any(l.text.strip() for l in lines):
        return None, []
    doc_type = doc_type or detect_doc_type(lines)
    info = extract_info(lines, doc_type, source)

    if doc_type in ("decision_president", "decision_associes", "pv_ag"):
        sections = split_ordinal(lines)
    elif doc_type in ("traite", "document_structure"):
        sections = merge_small(split_numbered(lines), config.UNIT_MIN_CHARS)
    else:
        sections = split_generic(lines, info.acte)

    base = " — ".join(x for x in [info.societe, info.acte + (f" du {info.date_texte}" if info.date_texte else "")] if x)
    chunks: list[Chunk] = []

    def meta(section: Section, ctype: str, page: int) -> dict:
        return {
            "source": source, "categorie": categorie, "doc_type": doc_type,
            "societe": info.societe, "acte": info.acte, "date_acte": info.date_iso,
            "section": section.path, "section_num": section.num,
            "chunk_type": "annexe" if (section.annex and ctype == "texte") else ctype,
            "annexe": section.annex, "page": page,
            # champs communs à toutes les sources (voir sources.py), utilisés par pipeline.py
            "dossier": dossier, "source_type": "document", "date": info.date_iso,
            "auteur": "", "titre": Path(source).stem,
            "acte_id": Path(source).stem, "version": "final",
        }

    for u, sec in enumerate(sections):
        blocks = reflow(sec.lines)
        text_blocks = [b for b in blocks if b.kind == "p"]
        if sec.label:
            text_blocks.insert(0, Block(sec.label, sec.page))
        if text_blocks and not (len(text_blocks) == 1 and text_blocks[0].text == sec.label):
            unit_text = "\n\n".join(b.text for b in text_blocks)
            pieces = pack(text_blocks, config.UNIT_MAX_CHARS, config.CHUNK_OVERLAP) \
                if len(unit_text) > config.UNIT_MAX_CHARS else [(unit_text, text_blocks[0].page)]
            ctype = "preambule" if sec.level == 0 and sec.num == "" and sec.title == "Préambule" else "texte"
            parent_id = _hash(dossier, source, u, "parent", unit_text[:300])
            use_parent = len(unit_text) <= config.PARENT_MAX_CHARS
            for k, (txt, page) in enumerate(pieces):
                ptxt = unit_text if use_parent else txt
                pid = parent_id if use_parent else _hash(parent_id, k)
                contexte = f"{base} — {sec.path}" if base else sec.path
                chunks.append(Chunk(_hash(parent_id, k, txt), txt, contexte, pid, ptxt, meta(sec, ctype, page)))

        for b in (x for x in blocks if x.kind == "table"):
            tb = tables[int(b.text[len(TABLE_MARK):])]
            title = f"Tableau — {tb.caption}" if tb.caption else "Tableau"
            head_md = table_markdown(tb.rows[:1], header_only=True)
            groups, cur, cur_len = [], [], 0
            for r in tb.rows[1:]:
                row = "| " + " | ".join(r + [""] * (len(tb.rows[0]) - len(r))) + " |"
                if cur and cur_len + len(row) > config.UNIT_MAX_CHARS:
                    groups.append(cur)
                    cur, cur_len = [], 0
                cur.append(row)
                cur_len += len(row) + 1
            groups.append(cur)
            full = f"{title}\n{table_markdown(tb.rows)}"
            parent_id = _hash(dossier, source, u, "table", full[:300])
            use_parent = len(full) <= config.PARENT_MAX_CHARS
            for k, g in enumerate(groups):
                txt = f"{title}\n{head_md}\n" + "\n".join(g)
                pid = parent_id if use_parent else _hash(parent_id, k)
                contexte = f"{base} — {sec.path} — tableau" if base else f"{sec.path} — tableau"
                chunks.append(Chunk(_hash(parent_id, k, txt), txt, contexte, pid,
                                    full if use_parent else txt, meta(sec, "tableau", tb.page)))
    return info, chunks


def build_text_chunks(text: str, meta: dict, contexte: str) -> list[Chunk]:
    """Mail, transcript ou note (déjà normalisé par sources.py) : le document entier est l'unité."""
    lines = [Line(l, meta.get("page", 1)) for l in text.splitlines()]
    blocks = reflow(lines)
    if not blocks:
        return []
    unit_text = "\n\n".join(b.text for b in blocks)
    pieces = pack(blocks, config.UNIT_MAX_CHARS, config.CHUNK_OVERLAP) \
        if len(unit_text) > config.UNIT_MAX_CHARS else [(unit_text, blocks[0].page)]
    parent_id = _hash(meta.get("dossier", ""), meta["source"], "parent", unit_text[:300])
    use_parent = len(unit_text) <= config.PARENT_MAX_CHARS
    full_meta = {
        "doc_type": meta["source_type"], "societe": "", "acte": meta.get("titre", ""),
        "date_acte": meta.get("date", ""), "section": meta.get("titre", ""), "section_num": "",
        "chunk_type": "texte", "annexe": False, **meta,
    }
    return [
        Chunk(_hash(parent_id, k, txt), txt, contexte,
              parent_id if use_parent else _hash(parent_id, k),
              unit_text if use_parent else txt, {**full_meta, "page": page})
        for k, (txt, page) in enumerate(pieces)
    ]


# --------------------------------------------------------------------------- #
# Aperçu en ligne de commande
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--doc-type", default=None)
    ap.add_argument("--full", action="store_true", help="affiche le texte des chunks")
    args = ap.parse_args()
    info, chunks = build_chunks(args.pdf, args.pdf.name, args.doc_type)
    if info is None:
        raise SystemExit("Aucun texte extractible.")
    print(f"{args.pdf.name} → type={info.doc_type} | société={info.societe!r} | acte={info.acte!r} | "
          f"date={info.date_texte!r} ({info.date_iso}) | {len(chunks)} chunks")
    for n, c in enumerate(chunks, 1):
        m = c.meta
        print(f"\n#{n} [{m['chunk_type']}] p.{m['page']} | {m['section'][:90]} | "
              f"{len(c.text)} car. (parent {len(c.parent_text)} car.)")
        if args.full:
            print(c.text)