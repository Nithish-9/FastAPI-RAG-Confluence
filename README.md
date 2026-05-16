# RAG Backend — Production Reference

A production-grade Retrieval-Augmented Generation backend built with FastAPI and Qdrant.  
Supports two independent knowledge pipelines: **Enterprise** (Confluence + documents) and **Workspace** (local codebases via the `nexus` CLI).

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Collections](#collections)
- [Project Structure](#project-structure)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
  - [System](#system)
  - [Enterprise Pipeline](#enterprise-pipeline)
  - [Workspace Pipeline](#workspace-pipeline)
- [Workspace Auth Model](#workspace-auth-model)
- [Code Parser — Language Support](#code-parser--language-support)
- [Chunking Strategy](#chunking-strategy)
- [Ingestion Pipelines](#ingestion-pipelines)
- [Retrieval Pipeline](#retrieval-pipeline)
- [System Readiness Gate](#system-readiness-gate)
- [Dependencies](#dependencies)
- [Running Locally](#running-locally)
- [Docker](#docker)
- [Production Checklist](#production-checklist)

---

## Architecture Overview

```
                        ┌─────────────────────────────────────────┐
                        │            FastAPI Server                │
                        │                                          │
  Confluence Webhook ──▶│  POST /webhook/confluence                │
  Document Upload    ──▶│  POST /documentupload                    │
                        │         │                                │
                        │   document_processor                     │
                        │         │ LangChain Loaders              │
                        │         ▼                                │
                        │   document_chunker                       │
                        │   (Markdown + Recursive split)           │
                        │         │                                │
  nexus CLI          ──▶│  POST /workspace/create-index            │
  (Go client)           │         │ tree-sitter parser             │
                        │         ▼                                │
                        │   EmbeddingService                       │
                        │   ┌─────────────┬──────────────┐        │
                        │   │ Dense Model │ Sparse Model │        │
                        │   │ (Async HTTP)│ (SPLADE)     │        │
                        │   └──────┬──────┴──────┬───────┘        │
                        │          └──────┬───────┘                │
                        │                 ▼                        │
                        │           Qdrant (2 collections)         │
                        │   ┌────────────────────────────┐        │
                        │   │ Enterprise_Knowledge_Base  │        │
                        │   │ Workspace_Knowledge_Base   │        │
                        │   └────────────────────────────┘        │
                        │                 │                        │
  LLM Tool Call      ──▶│  POST /workspace/retrieve               │
  RAG Query          ──▶│  POST /rag/retrieve                      │
                        │         │ Hybrid RRF + Reranker          │
                        │         ▼                                │
                        │      Results                             │
                        └─────────────────────────────────────────┘
```

---

## Collections

### `Enterprise_Knowledge_Base_<dim>`

For organizational knowledge: Confluence pages and uploaded documents (PDF, DOCX, TXT, MD).

| Field | Description |
|---|---|
| `page_id` | Confluence page ID or SHA-256 of file content |
| `source_type` | `CONFLUENCE`, `PDF`, `DOCX`, `TXT`, etc. |
| `content_hash` | SHA-256 of raw content — used for change detection |
| `chunk_index` | Position of chunk within the document |
| `space_key` | Confluence space key (N/A for files) |
| `content` | Chunk text (stored for retrieval) |

**Payload index:** `page_id`

---

### `Workspace_Knowledge_Base_<dim>`

For per-user codebase indexing. Supports 3-level isolation.

| Field | Description |
|---|---|
| `user_id` | Base64-encoded email — L1 isolation |
| `email_id` | Plain email — human-readable reference |
| `workspace_id` | SHA-256 of workspace root path — L2 isolation |
| `path_id` | SHA-256 of absolute file path — L3 isolation |
| `path` | Absolute file path on client machine |
| `file_name` | e.g. `LoanService.java` |
| `file_extension` | e.g. `.java` |
| `content_id` | SHA-256 of file content — used for dedup |
| `chunk_index` | Position of chunk within the file |
| `symbol` | Extracted function / class / trigger name |
| `language` | Detected language (from tree-sitter) |
| `content` | Context header + code (shown to LLM) |
| `raw_content` | Code only, no header (debug/audit) |

**Payload indexes:** `user_id`, `workspace_id`, `path_id`

Both collections use **named vectors** (`dense-vector`, `sparse-vector`) with HNSW configuration and on-disk storage.

---

## Project Structure

```
.
├── main.py                          # FastAPI app, lifespan, enterprise endpoints
├── core/
│   ├── config_validator.py          # Fail-fast env validation on startup
│   ├── concurrency.py               # ThreadPoolExecutor for sync tasks
│   └── state.py                     # SystemState readiness gate
├── schemas/
│   ├── dense_dto.py                 # Dense embedding request/response models
│   ├── sparse_dto.py                # Sparse embedding request/response models
│   ├── reranker_dto.py              # Reranker request/response models
│   ├── rag_dto.py                   # Enterprise RAG query models
│   └── workspace_dto.py             # Workspace create/delete/retrieve models
├── service/
│   ├── model_services.py            # Hosted/Local factory for Dense, Sparse, Reranker
│   ├── generate_embedding.py        # EmbeddingService — parallel dense+sparse
│   ├── rerank_service.py            # RerankService with connectivity check
│   ├── document_chunking.py         # Markdown + recursive chunker (enterprise)
│   ├── document_processor.py        # LangChain loaders for Confluence + files
│   ├── document_ingestion.py        # Enterprise ingestion pipeline
│   ├── qdrant_service.py            # Enterprise Qdrant collection + hybrid search
│   ├── code_parser.py               # Tree-sitter code chunker (workspace)
│   ├── workspace_ingestion.py       # Workspace ingestion pipeline
│   └── workspace_qdrant_service.py  # Workspace Qdrant collection + hybrid search
└── routers/
    └── workspace_router.py          # /workspace/* endpoints
```

---

## Environment Variables

### Required

| Variable | Description | Example |
|---|---|---|
| `QDRANT_HOST` | Qdrant server hostname | `localhost` |
| `DENSE_MODEL_DIM` | Dense vector dimension — must match model output | `768` |
| `DENSE_URL` | Dense embedding service URL | `http://localhost:8001` |
| `SPARSE_URL` | Sparse embedding service URL | `http://localhost:8002` |
| `RERANKER_URL` | Reranker service URL | `http://localhost:8003` |

### Model Mode (per service: DENSE / SPARSE / RERANKER)

| Variable | Description | Default |
|---|---|---|
| `{PREFIX}_HOSTED` | `true` = hosted API, `false` = local service | `false` |
| `{PREFIX}_API_KEY` | API key (required when `_HOSTED=true`) | — |
| `{PREFIX}_MODEL` | Model name (required when `_HOSTED=true`) | — |

### Qdrant Tuning

| Variable | Description | Default |
|---|---|---|
| `QDRANT_PORT` | Qdrant port | `6333` |
| `QDRANT_COLLECTION_BASE` | Enterprise collection name prefix | `Enterprise_Knowledge_Base` |
| `WORKSPACE_COLLECTION_BASE` | Workspace collection name prefix | `Workspace_Knowledge_Base` |
| `DENSE_DISTANCE` | Distance metric (`COSINE`, `DOT`, `EUCLID`) | `COSINE` |
| `QDRANT_ON_DISK` | Store vectors on disk (saves RAM) | `true` |
| `HNSW_M` | HNSW M parameter | `16` |
| `HNSW_EF_CONSTRUCT` | HNSW ef_construct | `100` |
| `HNSW_EF` | HNSW ef at query time | `128` |
| `SPARSE_FULL_SCAN_THRESHOLD` | Sparse index full-scan threshold | `1000` |
| `QDRANT_INDEXING_THREADS` | Indexing thread count (`0` = auto) | `0` |

### Confluence (optional)

| Variable | Description |
|---|---|
| `CONFLUENCE_BASE_URL` | e.g. `https://yourorg.atlassian.net/wiki` |
| `EMAIL` | Atlassian account email |
| `API_TOKEN` | Atlassian API token |

### App

| Variable | Description | Default |
|---|---|---|
| `APP_PORT` | Port to bind | `9000` |
| `RETRIES` | Connectivity check retries | `5` |
| `DELAY` | Seconds between retries | `3` |

---

## API Reference

### System

#### `GET /health`

Returns readiness state of all components.

```json
{
  "dense": true,
  "sparse": true,
  "reranker": true,
  "vectordb": true
}
```

Returns `503` from any endpoint until all four components are `true`.

---

### Enterprise Pipeline

#### `POST /webhook/confluence`

Webhook receiver for Confluence page events. Ingestion is queued to a background worker.

```json
{
  "page": { "id": "123456" }
}
```

#### `POST /documentupload`

Upload a document for ingestion. Supported: `.pdf`, `.docx`, `.doc`, `.txt`, and any other format via `UnstructuredFileLoader`.

- **Content-Type:** `multipart/form-data`
- **Field:** `file`

Ingestion is queued to a background worker. Returns immediately.

#### `POST /rag/retrieve`

Hybrid semantic search over the enterprise knowledge base.

**Request:**
```json
{
  "query": "how does the loan approval process work?",
  "top_k": 5,
  "page_id": "optional-filter",
  "chunk_index": null
}
```

**Response:**
```json
{
  "status": "success",
  "count": 5,
  "data": [
    {
      "content": "...",
      "metadata": { "page_id": "...", "source_type": "CONFLUENCE", "chunk_index": 2, "...": "..." },
      "rrf_score": 0.032,
      "rerank_score": 0.91
    }
  ]
}
```

---

### Workspace Pipeline

All workspace endpoints require the header:

```
X-User-Email: <base64-encoded email>
```

#### `POST /workspace/create-index`

Ingest a single file from a user's local workspace. Called by the `nexus` Go CLI.

- **Content-Type:** `multipart/form-data`
- **Max file size:** 50 MB

| Field | Type | Description |
|---|---|---|
| `content_id` | string | SHA-256 of file content |
| `workspace_id` | string | SHA-256 of workspace root path |
| `path` | string | Absolute file path on client |
| `path_id` | string | SHA-256 of file path |
| `file_name` | string | e.g. `LoanService.java` |
| `file_extension` | string | e.g. `.java` |
| `file_data` | file | File bytes |

**Dedup:** If a point with the same `path_id` + `content_id` already exists, ingestion is skipped and `"status": "skipped"` is returned. No API call to the embedding service is made.

**Response (indexed):**
```json
{ "status": "success", "chunks_upserted": 12, "file_name": "LoanService.java" }
```

**Response (skipped):**
```json
{ "status": "skipped", "reason": "content_id unchanged" }
```

---

#### `POST /workspace/delete-index`

Bulk-delete all indexed chunks for a list of `path_id`s. Called by the `nexus` delete worker using pre-computed `ChildFilePathIDs` from the directory tree — no tree traversal required at delete time.

**Request:**
```json
{
  "path_ids": ["sha256-of-path-1", "sha256-of-path-2"]
}
```

**Response:**
```json
{ "status": "success", "deleted_path_ids": 2 }
```

---

#### `POST /workspace/retrieve`

Hybrid semantic search over a user's indexed workspace. Designed to be called as an **LLM tool**.

**Request:**
```json
{
  "query": "how is interest calculated for fixed rate loans?",
  "top_k": 5,
  "workspace_id": "sha256-of-workspace-root",
  "path_id": null,
  "chunk_index": null
}
```

`workspace_id` and the `X-User-Email` header are **mandatory**. `path_id` and `chunk_index` are optional — the LLM passes these on follow-up calls to drill into a specific file or chunk.

**LLM tool call pattern:**
```
Turn 1: query + workspace_id                       → returns chunks with path_id, chunk_index
Turn 2: query + workspace_id + path_id             → narrows to one file
Turn 3: query + workspace_id + path_id + chunk_index → fetches a specific chunk's context
```

**Response:**
```json
{
  "status": "success",
  "count": 3,
  "data": [
    {
      "content": "# File: src/loans/LoanService.java\n# Workspace: /users/nithish/bank-repo\n# Language: java\n# Symbol: LoanService.calculateInterest\n---\npublic double calculateInterest(...) { ... }",
      "file_name": "LoanService.java",
      "file_extension": ".java",
      "path": "/users/nithish/bank-repo/src/loans/LoanService.java",
      "path_id": "sha256-of-path",
      "workspace_id": "sha256-of-workspace",
      "chunk_index": 3,
      "content_id": "sha256-of-content",
      "symbol": "calculateInterest",
      "language": "java",
      "rrf_score": 0.031,
      "rerank_score": 0.94
    }
  ]
}
```

---

## Workspace Auth Model

```
X-User-Email: <base64("user@example.com")>
             = "dXNlckBleGFtcGxlLmNvbQ=="
```

The server decodes this to derive:

| Stored Field | Value |
|---|---|
| `user_id` | `dXNlckBleGFtcGxlLmNvbQ==` (base64 — used for Qdrant filtering) |
| `email_id` | `user@example.com` (plain — stored for human-readable reference) |

Every Qdrant query carries a mandatory `user_id` filter, so users can never read each other's indexed data even within the same collection.

---

## Code Parser — Language Support

`service/code_parser.py` uses **tree-sitter** (the same parsing engine used by Cursor and Claude Code) for accurate, error-tolerant AST-based chunking.

| Strategy | Languages |
|---|---|
| **tree-sitter (native grammar)** | Python, Go, Java, JavaScript, TypeScript, JSX, TSX, C, C++, C#, Rust, Ruby, Kotlin, PHP, Scala, Bash, HTML, CSS, SCSS, SQL, TOML, YAML, JSON |
| **Regex boundary detection** | Apex (`.cls`, `.trigger`, `.apex`, `.page`, `.component`), Swift |
| **Recursive text splitter** | Markdown, plain text, XML |
| **Existing document pipeline** | PDF, DOCX, DOC |

Tree-sitter has built-in **error recovery** — even syntactically broken or partially valid code files are parsed without failure. If tree-sitter produces no nodes, the file silently falls back to `RecursiveCharacterTextSplitter`.

### Salesforce / Apex Extensions

| Extension | Handled as |
|---|---|
| `.cls` | Apex (regex: class + method boundaries) |
| `.trigger` | Apex (regex: trigger declaration boundary) |
| `.apex` | Apex |
| `.page` | Apex (Visualforce) |
| `.component` | Apex (Visualforce component) |

---

## Chunking Strategy

Every chunk produced by the workspace pipeline includes:

**Context header** (prepended to every chunk):
```
# File: src/loans/LoanService.java
# Workspace: /users/nithish/bank-repo
# Language: java
# Symbol: LoanService.calculateInterest
---
<code>
```

This ensures the LLM always knows which file and symbol a chunk belongs to without needing a separate metadata lookup.

**Overlap:** 50-character tail of the previous chunk is prepended to the next chunk within the same file, preventing logic from being cut at function boundaries. Overlap never crosses file boundaries.

**Enterprise pipeline** uses 1000-character chunks with 100-character overlap via LangChain's `MarkdownHeaderTextSplitter` + `RecursiveCharacterTextSplitter`.

---

## Ingestion Pipelines

### Enterprise

```
Confluence Webhook / File Upload
        │
        ▼
document_processor.py       (LangChain loaders)
        │  combined content + metadata
        ▼
Change detection             (content_hash comparison via Qdrant scroll)
        │  changed or new
        ▼
document_chunking.py         (MarkdownHeader + Recursive split)
        │  List[Document] with metadata
        ▼
EmbeddingService             (dense + sparse in parallel via asyncio.gather)
        │
        ▼
qdrant_service.upsert_chunks (delete old → upsert new)
```

### Workspace

```
nexus CLI  →  POST /workspace/create-index  (multipart)
        │
        ▼
workspace_ingestion.py
        │  decode base64 header → user_id, email_id
        │  dedup check: (path_id + content_id) in Qdrant?  → skip if yes
        │  delete old chunks for path_id
        ▼
code_parser.py               (tree-sitter / regex / fallback)
        │  List[CodeChunk] with symbol, language, context header
        ▼
EmbeddingService             (dense + sparse in parallel)
        │
        ▼
workspace_qdrant_service.upsert_chunks
```

---

## Retrieval Pipeline

Both enterprise and workspace retrieval use the same hybrid pipeline:

```
Query
  │
  ▼
EmbeddingService.get_combined_embeddings   (dense + sparse in parallel)
  │
  ▼
Qdrant query_points
  ├── Prefetch: dense-vector  (HNSW, top_k × 4 candidates)
  └── Prefetch: sparse-vector (full_scan or index, top_k × 4 candidates)
  │
  ▼
RRF Fusion                   (Reciprocal Rank Fusion)
  │  top_k × 4 fused candidates
  ▼
RerankService.rerank         (cross-encoder, top_k final results)
  │
  ▼
Response
```

Fallback: if the reranker is unavailable, the endpoint falls back to returning the top-k RRF results directly (logged as a warning, not a 500).

---

## System Readiness Gate

On startup, all four components initialize in parallel:

```
asyncio.gather(
    qdrant_service.init_qdrant(),
    workspace_qdrant_service.init_collection(),
    embed_service.check_dense_connectivity(),
    embed_service.check_sparse_connectivity(),
    rerank_service.check_reranker_connectivity(),
)
```

Each connectivity check retries up to `RETRIES` times with `DELAY` seconds between attempts. Until all components report ready, every endpoint returns `503 Service Unavailable`. Check `/health` to monitor startup progress.

---

## Dependencies

```txt
fastapi
uvicorn[standard]
python-dotenv
pydantic
httpx
qdrant-client
langchain-community
langchain-core
langchain-text-splitters
pypdf
docx2txt
unstructured
tree-sitter==0.21.3
tree-sitter-languages==1.10.2
```

> **Note:** `tree-sitter` version must be pinned to `0.21.3`. `tree-sitter-languages==1.10.2` was compiled against this version. Using `tree-sitter>=0.22` will cause import failures.

---

## Running Locally

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Start Qdrant
docker run -p 6333:6333 qdrant/qdrant

# 3. Configure environment
cp .env.example .env
# Edit .env with your model URLs and Qdrant host

# 4. Start the server
python main.py
# or
uvicorn main:app --host 0.0.0.0 --port 9000
```

---

## Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 9000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
```

```yaml
# docker-compose.yml
services:
  rag-api:
    build: .
    ports:
      - "9000:9000"
    env_file: .env
    depends_on:
      - qdrant

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

volumes:
  qdrant_data:
```

---

## Production Checklist

- [ ] Pin `tree-sitter==0.21.3` in `requirements.txt`
- [ ] Set `QDRANT_ON_DISK=true` for collections larger than available RAM
- [ ] Tune `HNSW_EF` (query accuracy vs. latency) — start at `128`, raise for higher recall
- [ ] Set `QDRANT_INDEXING_THREADS` to a value less than your CPU core count to avoid I/O saturation during bulk ingestion
- [ ] Rotate the base64 encoding of workspace emails to a stronger scheme (HMAC or JWT) before exposing to the internet
- [ ] Add rate limiting on `/workspace/create-index` — each call reads a file and calls the embedding service
- [ ] Mount `temp_uploads/` to a fast ephemeral disk (tmpfs) — files are deleted immediately after ingestion
- [ ] Set `RETRIES=10` and `DELAY=5` in production where cold-start of model servers is slow
- [ ] Monitor `/health` in your load balancer health check — it reflects all component states
- [ ] For large repos, pre-warm the workspace collection with a full sync before enabling the LLM tool
