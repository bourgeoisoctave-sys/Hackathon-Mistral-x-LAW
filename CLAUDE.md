# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Prototype RAG (Python, all in French: code comments, prompts, output). It reads a PV d'AG (French shareholders' meeting minutes) as a PDF, retrieves the company's internal best practices from a vector DB, and writes a Markdown improvement report that cites its sources (file + page). Uses Mistral for embeddings and chat, ChromaDB for storage, PyMuPDF for PDF text.

## Commands

```bash
pip install -r requirements.txt
echo 'MISTRAL_API_KEY=...' > .env      # config.py loads .env (never overrides exported vars)

pytest                 # offline suite: fake embeddings, temp Chroma, synthetic PDFs
pytest -m real_api     # one smoke test against the real Mistral API (skipped without key)

python ingest.py docs/                 # index all PDFs under docs/ (recursive); --reset to wipe the collection first
python analyze.py mon_pv.pdf -o rapport.md [--categorie modeles_pv] [--json]
FAKE_EMBEDDINGS=1 python ingest.py docs/   # offline check of ingestion/retrieval, no API key
```

No linter or build step. Tests live in `tests/` (`conftest.py` forces `FAKE_EMBEDDINGS` and a per-test Chroma dir; `make_pdf()` builds PDFs on the fly). `analyze.py` always needs the real API (chat calls are never faked). Default chat model is `ministral-14b-latest`: `mistral-large`/`medium` are not available on the free tier. The installed SDK is `mistralai` 3.x (`from mistralai.client import Mistral`); `llm.py` falls back to the 1.x import.

## Architecture

Flat modules, no package:

- `config.py` holds every tunable as an env var with a default (models, `CHUNK_SIZE`/`CHUNK_OVERLAP`, `TOP_K_PER_QUERY`, `TOP_K_PER_SECTION`, `MAX_DISTANCE`, `RAG_DB_PATH`). Change behaviour here, not inline.
- `llm.py` is the only place that talks to Mistral: `embed()`, `chat()`, `chat_json()` (uses `response_format={"type": "json_object"}`, not a schema), all wrapped in an exponential-backoff `_retry`. The client is created lazily.
- `ingest.py` does PDF → pages → paragraph/sentence chunks (by character size, not by article) → embeddings → Chroma `upsert`. It also exposes `get_collection()`, which `analyze.py` reuses.
- `analyze.py` runs a 4-step pipeline: read PV → LLM splits it into sections, each with 2–4 retrieval questions (`SYSTEM_DECOMPOSE`) → multi-query retrieval per section → per-section JSON analysis (`SYSTEM_SECTION`) → prose synthesis (`SYSTEM_SYNTHESE`) → `build_report()`.

Non-obvious points that span files:

- **Metadata contract.** Every chunk carries `{source, page, categorie}`. `categorie` is the first subfolder under `docs/` (or `"general"`), and it is what `--categorie` filters on via Chroma `where`.
- **Idempotent ingestion.** Chunk IDs are a sha1 of `path|page|index|text`, so re-ingesting unchanged files does not duplicate them. Edited files leave their old chunks behind unless you use `--reset`.
- **Embedded text ≠ stored text.** At ingestion, the embedded string is prefixed with `"<file stem> (p.N)\n"`, but `documents` stores the raw chunk.
- **Embedding dimensions must not be mixed.** `FAKE_EMBEDDINGS` gives 256-d vectors and `mistral-embed` gives 1024-d. Switching between them, or changing `EMBED_MODEL`, needs `ingest.py --reset`, otherwise Chroma rejects the dimension.
- **Retrieval.** Cosine collection (`hnsw:space: cosine`). Each section is queried with its title plus its generated questions, results are deduplicated by ID with the best distance kept, anything above `MAX_DISTANCE` is dropped, and the top `TOP_K_PER_SECTION` are kept.
- **Citation mapping.** Passages are shown to the LLM as 1-based `[i]`. The LLM returns `sources: [i, ...]`, and `build_report()` maps these back to `passages[i-1].meta` (invalid indexes are ignored silently). If you change the passage numbering, update both sides.
- **Grounding rules live in the prompts.** `SYSTEM_SECTION` must answer only from the given passages and returns `couverture: "aucune"` when nothing is relevant. Statuses are `conforme | a_ameliorer | lacune`; `STATUT_LABEL` must match.
- Scanned PDFs (no text layer) are skipped at ingestion. `analyze.py` exits on them.

Git-ignored: `docs/` (the corpus), `chroma_db/` (the vector store), `*.analyse.md` (generated reports).

## Design notes

`mistral-rag.md` holds planning notes. They describe a **target** pipeline that differs from the current code: Mistral OCR with `document_annotation_format` for metadata, per-article chunking, a rerank step, pydantic-constrained output, Ragas evaluation, and a 2-person split of the work. Treat them as direction, not as a description of what exists. The README's "Limites connues" section lists the same gaps: no OCR, retrieval quality not yet measured, no document versioning, data sent to the Mistral API.
