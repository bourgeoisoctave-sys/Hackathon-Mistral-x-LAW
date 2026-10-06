"""Ingestion des documents (PDF, mails .eml, transcripts .txt/.md) dans la base vectorielle.

Les PDF sont découpés par unité juridique (décision, résolution, article, tableau…) — voir
chunking.py ; un PDF scanné passe par Mistral OCR (ocr.py). Mails et transcripts sont
normalisés par sources.py. Les petits chunks sont indexés dans ChromaDB ; l'unité entière
(parent) est stockée à part (parents.py) et rendue à l'agent après la recherche.

Usage :
    python ingest.py docs/                                  # bonnes pratiques (récursif)
    python ingest.py dossiers/acme --dossier acme           # contexte d'un dossier client
    python ingest.py docs/ --reset                          # repart d'une base vide
    python ingest.py docs/ --dry-run                        # montre le découpage sans API ni écriture
    python ingest.py docs/ --skip-annexes                   # n'indexe pas les annexes

Le premier sous-dossier donne la métadonnée « categorie » ; le format donne « source_type »
(document | mail | reunion | note). Ré-ingérer un fichier remplace son ancienne version.
"""
import argparse
from pathlib import Path

import chromadb

import chunking
import config
import llm
import sources
from parents import ParentStore


def get_collection(reset: bool = False):
    client = chromadb.PersistentClient(path=config.DB_PATH)
    if reset:
        try:
            client.delete_collection(config.COLLECTION)
        except Exception:  # noqa: BLE001
            pass
    return client.get_or_create_collection(
        config.COLLECTION, metadata={"hnsw:space": "cosine"}
    )


def file_chunks(path: Path, root: Path, dossier: str, doc_type: str | None = None, allow_ocr: bool = True):
    """Un fichier → (résumé affichable, chunks). Résumé None : rien d'extractible."""
    rel = path.relative_to(root)
    if path.suffix.lower() == ".pdf":
        categorie = rel.parts[0] if len(rel.parts) > 1 else "general"
        info, chunks = chunking.build_chunks(path, str(rel), doc_type, categorie, dossier, allow_ocr)
        if info is None:
            return None, []
        return f"type={info.doc_type}, société={info.societe or '?'}, date={info.date_texte or '?'}", chunks
    chunks = []
    docs = sources.load(path, root, dossier)
    for doc in docs:
        text = sources.clean_chunk(doc["text"])  # lignes citées « > », tics d'oral
        if text:
            chunks += chunking.build_text_chunks(text, doc["meta"], sources.label(doc["meta"]))
    if not chunks:
        return None, []
    return f"[{docs[0]['meta']['source_type']}]", chunks


def ingest(docs_dir: Path, reset: bool = False, dossier: str = "general", doc_type: str | None = None,
           skip_annexes: bool = False, dry_run: bool = False, categorie: str | None = None) -> None:
    """`categorie` : impose la métadonnée « categorie » (sinon : premier sous-dossier de docs_dir)."""
    files = sources.iter_files(docs_dir)
    if not files:
        raise SystemExit(f"Aucun fichier exploitable ({', '.join(sorted(sources.EXTENSIONS))}) dans {docs_dir}")
    col = store = None
    if not dry_run:
        col, store = get_collection(reset), ParentStore(reset)
    print(f"{len(files)} fichiers à traiter, dossier « {dossier} »"
          + (" (simulation, rien n'est écrit)" if dry_run else f" → collection « {config.COLLECTION} »"))

    total = 0
    for path in files:
        rel = path.relative_to(docs_dir)
        resume, chunks = file_chunks(path, docs_dir, dossier, doc_type, allow_ocr=not dry_run)
        if resume is None:
            print(f"  - {rel} : aucun texte extractible "
                  + ("(scan : OCR à l'ingestion réelle)" if dry_run else "(même après OCR) → ignoré"))
            continue
        if categorie:
            for c in chunks:
                c.meta["categorie"] = categorie
        if skip_annexes:
            chunks = [c for c in chunks if not c.meta.get("annexe")]
        chunks = list({c.id: c for c in chunks}.values())  # deux tableaux identiques → un seul id
        kinds: dict[str, int] = {}
        for c in chunks:
            kinds[c.meta["chunk_type"]] = kinds.get(c.meta["chunk_type"], 0) + 1
        detail = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
        print(f"  + {rel} {resume} → {len(chunks)} chunks ({detail})")
        total += len(chunks)
        if dry_run or not chunks:
            continue

        # Ré-ingestion : on retire l'ancienne version de ce fichier pour ce dossier.
        source = str(rel)
        col.delete(where={"$and": [{"source": source}, {"dossier": dossier}]})
        store.delete_source(f"{dossier}/{source}")

        embeddings = llm.embed([c.embed_text for c in chunks])
        col.upsert(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[{**c.meta, "parent_id": c.parent_id} for c in chunks],
            embeddings=embeddings,
        )
        store.put_many({c.parent_id: c.parent_text for c in chunks}, f"{dossier}/{source}")

    if dry_run:
        print(f"Simulation terminée : {total} chunks seraient indexés.")
    else:
        print(f"Terminé : {total} chunks indexés ({col.count()} au total dans la base).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docs_dir", type=Path)
    ap.add_argument("--reset", action="store_true", help="vide la base avant ingestion")
    ap.add_argument("--dossier", default="general", help="nom du dossier client (métadonnée « dossier »)")
    ap.add_argument("--doc-type", default=None,
                    choices=["decision_president", "decision_associes", "pv_ag", "traite", "document_structure", "generic"],
                    help="force le type de découpage des PDF (sinon détecté automatiquement)")
    ap.add_argument("--skip-annexes", action="store_true", help="n'indexe pas les annexes")
    ap.add_argument("--dry-run", action="store_true", help="affiche le découpage sans embeddings ni écriture")
    ap.add_argument("--categorie", default=None, help="impose la catégorie (ex. historiques) au lieu du sous-dossier")
    args = ap.parse_args()
    ingest(args.docs_dir, args.reset, args.dossier, args.doc_type, args.skip_annexes, args.dry_run, args.categorie)
