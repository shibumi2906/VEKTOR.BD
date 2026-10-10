# PinuiRAG

A local application for one or two users that demonstrates vector search over Hebrew documents. It searches public sources, guidance, and private contracts. With an OpenAI key, it translates questions into Hebrew and answers in the language of the question. Comparison covers a specific topic in two documents.

The application uses FastAPI, a Streamlit interface, PostgreSQL for the document registry and original text, and Qdrant for dense and sparse vectors. Search defaults to all available documents, including contracts. Sources retain their type, version, verification status, and original citations.

## Features and requirements

Without an API key, PDF/DOCX upload, Hebrew OCR, parsing, chunking, local indexing, Hebrew search, original passages, and the document registry are available. Translation, generated answers, and thematic comparison require internet access and a personal OpenAI API key. The primary model is `gpt-5.4-mini`, with `gpt-4.1-mini` configured as a fallback. Embeddings and reranking run locally.

The default query languages are Hebrew and Russian. The design is not restricted to Russian: `SUPPORTED_QUERY_LANGUAGES` can be extended, but additional languages require validation. Hebrew RTL and LTR text are handled separately. Current interface labels are in Russian.

## Windows installer

Run **`PinuiRAG-Setup-Windows-x64.exe`** from the project root. The build output is also available in `dist/`. The current installer is approximately 472 MB and targets Windows 10/11 x64.

It includes Python, PostgreSQL, Qdrant, local search models, PDF/OCR tools, and the prepared corpus. No separate Python/Docker installation or additional model downloads are required.

1. Install the application and open the PinuiRAG shortcut.
2. Wait for the initial database preparation; the interface opens in a browser.
3. Keep the launcher window open while using the application. Its **Close application** button stops the services.
4. Expand **GPT-5.4 mini settings** in the sidebar, paste your existing key into **OpenAI API key**, and select **Check and save**. You only need the OpenAI website link if you want to obtain a key.

The launcher chooses free loopback ports; its browser URL can change between launches. A page showing **CONNECTING** after shutdown is disconnected: launch PinuiRAG again and use the newly opened page.

Working databases, documents, and settings are stored in `%LOCALAPPDATA%\PinuiRAG\data`, separately from the installed program. Updating or uninstalling the program preserves that data folder. Saved keys are protected with Windows DPAPI for the current user. The installer contains no developer API key.

This is a personal build containing the current private contracts. Installation, offline search, vectors, citations, OCR, key protection, restart, and data preservation after uninstall were tested on the current Windows computer with system Python/Docker excluded from PATH. A clean Windows VM test has not been performed. See [Windows distribution](docs/windows-distribution.md) for packaging details.

## Docker development setup

Run these PowerShell commands from the project root. Development requires Docker Desktop with Compose and local Python for the configuration initialization script. The application runs in the locked Python 3.12 environment inside its Docker image. Initial image, source, and model downloads require internet access.

```powershell
python scripts/init_env.py
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

`init_env.py` creates `.env` with a random PostgreSQL password and an empty OpenAI key; it retains an existing `.env`. A fresh configuration starts in **bootstrap** mode. Starting containers alone does not create a searchable corpus: complete the procedure below before enabling production mode.

| Service | Default address |
|---|---|
| Interface | http://localhost:8510 |
| OpenAPI | http://localhost:8010/docs |
| Readiness and capabilities | http://localhost:8010/status |

`AUTH_MODE=local` is intended for a personal computer. The interface has no administrator account, login, or access token. Published ports bind to loopback.

## Creating the vector database

The source workflow builds an index from originals. The Windows installer instead restores its bundled PostgreSQL seed and imports already computed vectors into native Qdrant on first launch.

### 1. Download and register documents

The curated source list is `config/corpus-downloads.json`; source metadata is in `config/sources.yaml`. The downloader accepts allowlisted PDF URLs, records URLs and SHA-256 checksums, and writes originals under `data/raw/legislation/` with a `data/corpus-manifest.json` inventory. Downloading a file does not confirm its legal currentness.

With Docker services running:

```powershell
docker compose run --rm --no-deps api alembic upgrade head
docker compose run --rm --no-deps --user root api python -m scripts.download_corpus
docker compose run --rm --no-deps --user root api python -m scripts.registry import
```

Check the downloader's exit status and resolve failed downloads before continuing. Registry import copies checksum-verified originals into the raw storage volume and creates PostgreSQL document/version/source records. Repeated imports retain existing identities and review statuses. The curated public download does not include the private contracts or synthetic scan from the personal build; those files are excluded from Git.

### 2. Download the pinned local models

```powershell
docker compose run --rm --no-deps --user root api python -m scripts.download_models
```

The script downloads the model files in `config/local-models.json`, including a benchmark candidate, and records hashes in `data/models/manifest.json`. The active pipeline uses:

| Purpose | Model | Runtime |
|---|---|---|
| Embeddings | `intfloat/multilingual-e5-small` | ONNX INT8 CPU; 384 dimensions |
| Reranking | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | ONNX INT8 CPU; 512-token input |

Weights and tokenizer hashes are verified before loading. No remote model code is executed.

### 3. Parse originals and create chunks

```powershell
docker compose run --rm --no-deps --user root api python -m scripts.parse_registered_corpus
```

The parser reads registered PDF/DOCX originals, performs Hebrew OCR when necessary, extracts structural blocks, and retains page/paragraph/table locators and exact original text ranges. The current registered-document pipeline uses the selected E5 tokenizer with a **480-token chunk limit and 16-token overlap**. Artifacts are stored under `data/registered/`; PostgreSQL stores immutable revisions, blocks, and chunks.

`scripts/create_chunks.py --store` is the earlier manifest-based PDF tool. Its provisional settings in `config/chunking.json` are not the final E5 indexing limits. Use the registered-document pipeline above for the current PDF/DOCX/OCR workflow. Uncertain extraction and legal review statuses are not automatically promoted to verified.

To optionally import your own PDF/DOCX contracts, place them in the `договора` folder and run:

```powershell
docker compose run --rm --no-deps --user root -v "${PWD}:/source" -w /source api /workspace/.venv/bin/python -m scripts.import_contracts
```

This registers and parses the files; filename stems become version labels. DOCX contracts are labelled as drafts. Import does not establish signing or legal applicability. Once production mode is running, the interface's upload/jobs tab is another way to add documents.

### 4. Compute vectors and populate Qdrant

```powershell
docker compose run --rm --no-deps --user root api python -m scripts.index_corpus
```

The indexer performs these steps:

1. Validates parsing artifacts and original checksums and applies the selected model's chunking settings.
2. Computes normalized 384-dimensional embeddings with the `passage: ` prefix. Queries use `query: `.
3. Creates lexical sparse vectors using the PostgreSQL vocabulary, BM25 term weighting, and Qdrant IDF.
4. Writes a fingerprinted collection with named `dense` cosine vectors, named `lexical` sparse vectors, and document/version/generation metadata.
5. Reads points back and verifies dense vectors, sparse vectors, payloads, and expected counts.
6. Activates verified generations in PostgreSQL, updates the Qdrant alias, and atomically writes `data/index-manifest.json`.

The dense-vector cache is `data/all-vectors.npy`, with checksums/model metadata in `data/all-vector-checksums.json`. Unchanged builds reuse valid embeddings; model/document/chunk changes require corresponding index generations. Unverified generations are not made searchable.

Search combines dense and sparse candidates through reciprocal rank fusion, then reranks them with the local cross-encoder. Citations resolve to original PostgreSQL text rather than model-generated offsets.

### 5. Enable production mode and verify search

Update these **non-secret** settings in `.env`, retaining the generated PostgreSQL credentials. Values must match the selected models and index:

```dotenv
APP_MODE=production
AUTH_MODE=local
MODEL_STORAGE_PATH=/workspace/data/models
INDEX_STORAGE_PATH=/workspace/data
EMBEDDING_MODEL=intfloat/multilingual-e5-small
EMBEDDING_REVISION=614241f622f53c4eeff9890bdc4f31cfecc418b3
EMBEDDING_DIMENSION=384
RERANKER_MODEL=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
RERANKER_REVISION=1427fd652930e4ba29e8149678df786c240d8825
RERANK_MIN_SCORE=-3.0190533638000487
MAX_CONTEXT_TOKENS=64000
MAX_OUTPUT_TOKENS=1500
QUERY_COST_LIMIT=0.20
TOPIC_COMPARE_COST_LIMIT=0.40
DAILY_COST_LIMIT=1.00
```

Recreate services to apply the environment:

```powershell
docker compose up -d --force-recreate api ui worker scheduler
docker compose run --rm --no-deps api python -m scripts.registry summary
Invoke-RestMethod http://localhost:8010/status
```

The indexer's output reports active document and point counts and the collection name. `data/index-manifest.json` records models, vocabulary, fingerprint, and chunk count. `/status` reports readiness and capabilities.

Open the interface, select search-only mode, and ask a Hebrew question such as `מה מטרת תקן 21.1?`. Check a citation and its original file. The current personal build has **18 documents and 3,664 active chunks**; a fresh public-only build has fewer documents and chunks.

For new uploads, durable jobs handle parsing/indexing and expose progress. API operations include `POST /documents`, `POST /documents/{id}/reindex`, and `POST /documents/index`. Parsing alone does not activate a vector index.

## API key, answers, and comparison

Use the sidebar to check and save your existing OpenAI key. An invalid replacement leaves the saved key unchanged. Model access verification does not confirm account funds. Docker also accepts `OPENAI_API_KEY` in `.env`; recreate the API container after changing it. Saved keys stay in local runtime storage and are excluded from the repository/distribution. Windows uses DPAPI; the Docker credential file uses local file permissions.

For thematic comparison, select two versions and enter a specific topic, such as parking or payment of the owners' lawyer. A request without a topic asks for clarification. Exhaustive comparison of every clause is outside the implemented scope.

Default configured budgets are $0.20 per question, $0.40 per comparison, and $1.00 per day in the Asia/Jerusalem timezone. Usage and reservations are stored in PostgreSQL; adding a key does not bypass these limits.

## Corpus and legal-currentness limits

The prepared personal corpus contains 15 public PDFs (205 pages), two private contracts, and one explicitly labelled synthetic OCR fixture. The public sources comprise Standard 21.1, eight guidance documents, two regulations, two model agreements, one model form, and one ethics decision.

Only Standard 21.1 currently has confirmed current/verified status in this corpus. Other sources retain their review status and are not presented as verified current legislation. **Verified consolidated versions of 16 laws and two appraiser-related acts are still missing.** Historical publications and standalone amendments were removed from the retained corpus.

The amendment-chain compiler, effective dates, transitional conditions, provenance, and legal search gate are implemented. A law requires a reviewed complete chain; incomplete or stale chains cannot provide a normative answer. Downloading, chunking, and indexing cannot replace that review.

Local retrieval and Windows packaging have been checked. Public-source GPT answers/translations have received live checks, but full multilingual/manual Hebrew QA and live comparison of the private contracts are not fully accepted. See [progress](docs/progress.md), [corpus status](docs/corpus-status.md), and [legal currentness](docs/legal-currentness.md).

## Checks and data maintenance

These development checks use Docker and do not call paid APIs:

```powershell
docker compose run --rm --no-deps api uv run --frozen --group dev ruff check app tests scripts ui
docker compose run --rm --no-deps api uv run --frozen --group dev ruff format --check app tests scripts ui
docker compose run --rm --no-deps -e REGISTRY_INTEGRATION=1 api uv run --frozen --group dev pytest -q
python scripts/check_documents.py
docker compose run --rm --no-deps --user root api python -m scripts.accept_local
```

Integration/local acceptance checks require a prepared registry, models, and index. The latest complete regression run passed 141 tests. Windows checks verified all 3,664 vectors and payloads against the exported source data. Reports and pending checks are recorded in `docs/progress.md`.

Stop Docker services with `docker compose stop` and resume with `docker compose start`. Do not use `docker compose down -v` for a normal shutdown: it deletes storage volumes. Keep `.env`, keys, private contracts, `data/`, and backups out of Git.

Back up PostgreSQL, originals, parsing artifacts, configuration, and vectors consistently. Follow [operations](docs/operations.md) for backup and isolated restore checks. Cross-platform packaging uses `scripts/export_windows_vectors.py` to transfer exact vectors/payloads; it does not directly restore a Linux RocksDB snapshot into native Windows Qdrant.

## Project layout and documentation

| Location | Contents |
|---|---|
| `app/` | API, registry, parsers, chunking, embeddings, retrieval, jobs, LLM services |
| `ui/` | Streamlit interface |
| `config/` | Sources, pinned models, terminology, provider settings |
| `migrations/` | PostgreSQL schema migrations |
| `scripts/` | Download, import, parsing, indexing, verification, backup, packaging |
| `tests/`, `benchmarks/` | Automated checks and retrieval evaluation |
| `packaging/windows/` | Native launcher and Inno Setup definition |
| `data/` | Local originals, models, artifacts, reports, build inputs; ignored by Git |
| `dist/` | Generated Windows installer; ignored by Git |

Canonical requirements: [specification](docs/specification.md), [implementation plan](docs/implementation-plan.md), and [traceability](docs/requirements-traceability.md). Some supporting documents are in Russian. The older Word specification is not authoritative.
