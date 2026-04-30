# Enterprise Hybrid RAG Pipeline

A high-performance, production-ready Retrieval-Augmented Generation (RAG) backend built with **FastAPI** and **Qdrant**. This pipeline implements a sophisticated two-stage retrieval process—combining Dense and Sparse embeddings with Cross-Encoder Reranking—to deliver state-of-the-art search accuracy for local documents and Confluence wikis.

---

## 🚀 Key Features

- **Hybrid Search**: Combines semantic understanding (Dense vectors) with keyword precision (Sparse vectors) using Reciprocal Rank Fusion (RRF).
- **Two-Stage Retrieval**: Initial vector search followed by a precision reranking step using a Cross-Encoder model.
- **Multi-Source Ingestion**:
  - **Confluence**: Automated ingestion via webhooks with smart change detection.
  - **Files**: Support for `PDF`, `DOCX`, `DOC`, `TXT`, and Unstructured data.
- **Intelligent Chunking**: Markdown-aware splitting that preserves document hierarchy (H1–H3 headers) and ensures semantic continuity with configurable overlaps.
- **Production Resilience**:
  - **Self-Healing**: Exponential backoff retries for all AI inference and database calls.
  - **Deduplication**: Content hashing (SHA-256) to skip re-indexing of unchanged files.
  - **Connectivity Guard**: Strict startup validation ensures the API won't accept queries if models are offline.

---

## 🏗️ System Architecture

```
Ingestion Layer → Processing Layer → Embedding Layer → Storage Layer → Retrieval Layer
(Files/Confluence)  (Hash + Chunk)    (BGE + SPLADE)   (Qdrant/HNSW)  (Hybrid Search + Rerank)
```

1. **Ingestion Layer** — Loaders extract text from files or Confluence.
2. **Processing Layer** — Documents are hashed for deduplication and split into semantic chunks.
3. **Embedding Layer** — Parallel generation of BGE (Dense) and SPLADE (Sparse) vectors.
4. **Storage Layer** — Chunks and metadata are indexed in Qdrant with HNSW optimization.
5. **Retrieval Layer** — Hybrid search filters results, scored by a Jina Reranker before being returned.

---

## 📂 Project Structure

```
.
├── app/
│   ├── core/               # Config validation & Global System State
│   ├── schemas/            # Pydantic DTOs (Dense, Sparse, Rerank, RAG)
│   ├── services/           # Ingestion, Chunking, Embeddings, Qdrant & Rerank logic
│   └── main.py             # FastAPI entry point & lifespan management
├── docker-compose.yml      # 5-Service orchestration (API + DB + 3 Models)
├── Dockerfile              # Python 3.13-slim build specification
├── qdrant_config.yml       # Vector DB production configuration
└── requirements.txt        # Python dependencies
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI (Python 3.13) |
| Vector Database | Qdrant v1.17.0 |
| Dense Embeddings | BGE-Small |
| Sparse Embeddings | SPLADE |
| Reranker | Jina Cross-Encoder |
| Inference Client | HTTPX + Tenacity (Async) |
| Processing | LangChain & Unstructured |
| Deployment | Docker Compose |

---

## ⚙️ Environment Configuration

### Vector Database (Qdrant)

| Variable | Default | Description |
|---|---|---|
| `QDRANT_HOST` | `qdrant` | Hostname of the DB container |
| `QDRANT_PORT` | `6333` | Qdrant port |
| `DENSE_MODEL_DIM` | `384` | Must match embedding model output |
| `QDRANT_ON_DISK` | `true` | Enables on-disk storage |
| `DENSE_DISTANCE` | `COSINE` | Distance metric for vector comparison |
| `HNSW_M` | `16` | HNSW graph parameter |
| `HNSW_EF` | `128` | Search efficiency parameter |

### Inference Services

| Variable | Default | Description |
|---|---|---|
| `DENSE_HOSTED` | `false` | Set to `true` to use external APIs |
| `DENSE_URL` | `http://mis-dense-bge-small:8000` | Dense embedding service URL |
| `SPARSE_HOSTED` | `false` | |
| `SPARSE_URL` | `http://mis-sparse-splade-pp:8000` | Sparse embedding service URL |
| `RERANKER_HOSTED` | `false` | |
| `RERANKER_URL` | `http://mis-reranker-jina:8000` | Reranker service URL |
| `EMBED_BATCH_SIZE` | `32` | Batch size for embedding calls |
| `MAX_RERANK_CANDIDATES` | `100` | Max candidates passed to reranker |

### HTTP & Connection Settings

| Variable | Default | Description |
|---|---|---|
| `HTTP_TOTAL_TIMEOUT` | `120.0` | Total request timeout (seconds) |
| `HTTP_MAX_CONNECTIONS` | `100` | Max concurrent HTTP connections |
| `INFERENCE_MAX_RETRIES` | `3` | Max retries on inference failure |

---

## 🚢 Deployment

### Prerequisites

- Docker and Docker Compose installed.
- Sufficient RAM to host local inference models (Dense, Sparse, Rerank).

### Quick Start

```bash
# Build the application
docker build -t rag-fastapi:1.2.0 .

# Start the full stack
docker-compose up -d

# Check system logs
docker logs -f rag-fastapi
```

The system will initialize **5 containers**:

| # | Container | Role | Port |
|---|---|---|---|
| 1 | `rag-fastapi` | Core API gateway | `9001` |
| 2 | `qdrant` | Vector database | `6333` |
| 3 | `mis-dense-bge-small` | Dense embedding engine | — |
| 4 | `mis-sparse-splade-pp` | Sparse/Lexical embedding engine | — |
| 5 | `mis-reranker-jina` | Cross-encoder reranking engine | — |

> **Note:** Docker-native healthchecks ensure the API only receives traffic after all models have finished loading their weights (`start-period: 600s`).

---

## 🔌 API Reference

### 1. System Health

```
GET /health
```

Returns `200 OK` if all 4 core components (Dense, Sparse, Rerank, VectorDB) are ready.

### 2. File Ingestion

```
POST /documentupload
Content-Type: multipart/form-data
```

| Field | Type | Description |
|---|---|---|
| `file` | `File` | The document to ingest (`PDF`, `DOCX`, `DOC`, `TXT`) |

**Process:** Saves to temp → hashes content → checks for changes → chunks → embeds → indexes.

### 3. Confluence Sync

```
POST /webhook/confluence
```

Background task that fetches the latest page content, compares hashes, and updates the index only if changes are detected.

### 4. Hybrid Search (RAG)

```
POST /rag/retrieve
Content-Type: application/json
```

```json
{
  "query": "How do I set up my developer environment?",
  "top_k": 5,
  "page_id": "optional_id_to_scope_search",
  "chunk_index": 0
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | `string` | ✅ | The search question |
| `top_k` | `integer` | ✅ | Number of results to return |
| `page_id` | `string` | ❌ | Scope to a specific Confluence page |
| `chunk_index` | `integer` | ❌ | Starting chunk offset |

---

## 🔧 Reliability & Tuning

| Mechanism | Detail |
|---|---|
| **Retry Logic** | `tenacity` with exponential backoff (min 2s, max 10s) |
| **Connection Pooling** | `httpx.Limits` — 100 max connections, 20 keep-alive |
| **Candidate Truncation** | Reranker processes top `MAX_RERANK_CANDIDATES` (default: 100) only |
| **Healthchecks** | Docker-native checks delay traffic until model weights are fully loaded |
