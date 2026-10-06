"""Ingestion des documents de l'entreprise (PDF texte) dans la base vectorielle.

Chaque PDF est découpé par unité juridique (décision, article, tableau…) — voir chunking.py.
Les petits chunks sont indexés dans ChromaDB ; l'unité entière (parent) est stockée à part.

Usage :
    python ingest.py docs/                    # indexe tous les PDF (récursif)
    python ingest.py docs/ --reset            # repart d'une base vide
    python ingest.py docs/ --dry-run          # montre le découpage sans appeler l'API
    python ingest.py docs/ --skip-annexes     # n'indexe pas les annexes (listes de salariés, bilans…)

Organisation conseillée : un sous-dossier par catégorie
    docs/modeles_pv/…, docs/guides_internes/…, docs/juridique/…
Le nom du sous-dossier est stocké comme métadonnée « categorie ».
"""
import argparse
from pathlib import Path

import chromadb

import chunking as chunking
import config as config
import llm
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


def ingest(docs_dir: Path, reset: bool = False, doc_type: str | None = None,
           skip_annexes: bool = False, dry_run: bool = False) -> None:
    pdfs = sorted(docs_dir.rglob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"Aucun PDF trouvé dans {docs_dir}")
    col = store = None
    if not dry_run:
        col, store = get_collection(reset), ParentStore(reset)
    print(f"{len(pdfs)} PDF à traiter" + (" (simulation, rien n'est écrit)" if dry_run else ""))

    total = 0
    for pdf in pdfs:
        rel = pdf.relative_to(docs_dir)
        source = str(rel)
        categorie = rel.parts[0] if len(rel.parts) > 1 else "general"
        info, chunks = chunking.build_chunks(pdf, source, doc_type, categorie)
        if info is None:
            print(f"  - {rel} : aucun texte extractible (scan ?) → ignoré")
            continue
        if skip_annexes:
            chunks = [c for c in chunks if not c.meta.get("annexe")]
        kinds = {}
        for c in chunks:
            kinds[c.meta["chunk_type"]] = kinds.get(c.meta["chunk_type"], 0) + 1
        resume = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
        print(f"  + {rel} : type={info.doc_type}, société={info.societe or '?'}, "
              f"date={info.date_texte or '?'} → {len(chunks)} chunks ({resume})")
        if dry_run or not chunks:
            total += len(chunks)
            continue

        # Ré-ingestion : on retire l'ancienne version de ce fichier (autre découpage, texte modifié…)
        col.delete(where={"source": source})
        store.delete_source(source)

        embeddings = llm.embed([c.embed_text for c in chunks])
        col.upsert(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[{**c.meta, "parent_id": c.parent_id} for c in chunks],
            embeddings=embeddings,
        )
        store.put_many({c.parent_id: c.parent_text for c in chunks}, source)
        total += len(chunks)

    if dry_run:
        print(f"Simulation terminée : {total} chunks seraient indexés.")
    else:
        print(f"Terminé : {total} chunks indexés ({col.count()} au total dans la base).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docs_dir", type=Path)
    ap.add_argument("--reset", action="store_true", help="vide la base avant ingestion")
    ap.add_argument("--doc-type", default=None,
                    choices=["decision_president", "decision_associes", "pv_ag", "traite", "document_structure", "generic"],
                    help="force le type de découpage (sinon détecté automatiquement)")
    ap.add_argument("--skip-annexes", action="store_true", help="n'indexe pas les annexes")
    ap.add_argument("--dry-run", action="store_true", help="affiche le découpage sans embeddings ni écriture")
    args = ap.parse_args()
    ingest(args.docs_dir, args.reset, args.doc_type, args.skip_annexes, args.dry_run)