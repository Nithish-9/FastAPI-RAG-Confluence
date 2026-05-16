
from typing import List

import logging
import os
import time
import uuid
import asyncio

from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from service.rerank_service import rerank_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

DENSE_MODEL_DIM = int(os.getenv("DENSE_MODEL_DIM", 768))
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
QDRANT_RETRIES = int(os.getenv("RETRIES", 5))
QDRANT_TIMEOUT = int(os.getenv("QDRANT_TIMEOUT", 60))

WORKSPACE_COLLECTION = os.getenv(
    "WORKSPACE_COLLECTION", "Workspace_Knowledge_Base"
)
FINAL_COLLECTION_NAME = f"{WORKSPACE_COLLECTION}_{DENSE_MODEL_DIM}"

QDRANT_INDEXING_THREADS = int(os.getenv("QDRANT_INDEXING_THREADS", 0))
DIST_STR = os.getenv("DENSE_DISTANCE", "COSINE").upper()
DISTANCE_METRIC = getattr(models.Distance, DIST_STR)

QDRANT_ON_DISK = os.getenv("QDRANT_ON_DISK", "true").lower() == "true"
HNSW_M = int(os.getenv("HNSW_M", 16))
HNSW_EF_CONSTRUCT = int(os.getenv("HNSW_EF_CONSTRUCT", 100))
HNSW_EF = int(os.getenv("HNSW_EF", 128))
SPARSE_THRESHOLD = int(os.getenv("SPARSE_FULL_SCAN_THRESHOLD", 1000))


class WorkspaceQdrantService:
    def __init__(self):
        self.client = QdrantClient(
            host=QDRANT_HOST,
            port=QDRANT_PORT,
            timeout=60,
        )
        self.collection_name = FINAL_COLLECTION_NAME
    
    async def init_collection(self, retries=QDRANT_RETRIES):
        return await asyncio.to_thread(self._init_collection_sync, retries)

    def _init_collection_sync(self, retries: int) -> bool:
        logger.info(f"--- [WorkspaceQdrant] Initializing '{self.collection_name}' ---")

        for attempt in range(retries):
            try:
                self.client.get_collection(self.collection_name)
                logger.info(
                    f"--- [WorkspaceQdrant] Collection '{self.collection_name}' exists. ---"
                )
                return True

            except UnexpectedResponse as e:
                if e.status_code == 404:
                    logger.info("--- [WorkspaceQdrant] Creating new collection... ---")
                    self._create_collection()
                    return True
                raise e
            except Exception as e:
                wait = min(2 ** (attempt + 1), 30) 
                
                if attempt < retries - 1:
                    logger.warning(f"[WorkspaceQdrant] Attempt {attempt+1} failed. Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"[WorkspaceQdrant] Max retries reached. Connection failed.")

        return False

    def _create_collection(self):
        logger.info(f"--- [WorkspaceQdrant] Creating collection: {self.collection_name} ---")
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                "dense-vector": models.VectorParams(
                    size=DENSE_MODEL_DIM,
                    distance=DISTANCE_METRIC,
                    on_disk=QDRANT_ON_DISK,
                    hnsw_config=models.HnswConfigDiff(
                        m=HNSW_M,
                        ef_construct=HNSW_EF_CONSTRUCT,
                        on_disk=QDRANT_ON_DISK,
                        max_indexing_threads=QDRANT_INDEXING_THREADS,
                    ),
                )
            },
            sparse_vectors_config={
                "sparse-vector": models.SparseVectorParams(
                    index=models.SparseIndexParams(
                        on_disk=QDRANT_ON_DISK,
                        full_scan_threshold=SPARSE_THRESHOLD,
                    )
                )
            },
        )

        for field_name in ("user_id", "workspace_id", "path_id"):
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        logger.info(f"--- [WorkspaceQdrant] Schema created with HNSW(M={HNSW_M}) and OnDisk={QDRANT_ON_DISK} ---")

        logger.info(
            f"--- [WorkspaceQdrant] Collection created with indexes on "
            f"[user_id, workspace_id, path_id] ---"
        )

    def close(self):
        logger.info("--- [WorkspaceQdrant] Closing client connection... ---")
        self.client.close()

    def is_already_indexed(self, user_id: str, workspace_id : str, path_id: str, content_id: str) -> bool:
        """
        Returns True if a point with this exact (user_id + workspace_id + path_id + content_id) exists.
        user_id is mandatory — prevents a dedup hit on another user's identical path/content.
        Used to skip re-ingestion when file content hasn't changed.
        """
        must: List[models.Condition] = [
            models.FieldCondition(
                key="user_id", match=models.MatchValue(value=user_id)
            ),
            models.FieldCondition(
                key="workspace_id", match=models.MatchValue(value=workspace_id)
            ),
            models.FieldCondition(
                key="path_id", match=models.MatchValue(value=path_id)
            ),
            models.FieldCondition(
                key="content_id", match=models.MatchValue(value=content_id)
            ),
        ]
        results, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=models.Filter(must=must),
            limit=1,
            with_payload=False,
            with_vectors=False,
        )
        return len(results) > 0

    def delete_by_path_ids(self, user_id: str, path_ids: list[str]):
        """
        Bulk-delete all chunks for the given path_ids, scoped to user_id.
        user_id is mandatory — prevents a user from deleting another user's chunks
        even if path_ids were somehow guessed or collided.
        """
        if not path_ids:
            return
        must: List[models.Condition] = [
            models.FieldCondition(
                key="user_id", match=models.MatchValue(value=user_id)
            ),
            models.FieldCondition(
                key="path_id",
                match=models.MatchAny(any=path_ids),
            ),
        ]
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.Filter(must=must),
        )
        logger.info(
            f"--- [WorkspaceQdrant] Deleted chunks for {len(path_ids)} path_id(s) "
            f"user={user_id[:12]}... ---"
        )

    def upsert_chunks(
        self,
        chunks,     
        dense_vecs: list,
        sparse_vecs: list,
        user_id: str,
        email_id: str,
        content_id: str,
        workspace_id: str,
        path_id: str,
        path: str,
        file_name: str,
        file_extension: str,
    ):
        points = []
        for i, chunk in enumerate(chunks):
            sparse_dict = models.SparseVector(
                indices=sparse_vecs[i].indices,
                values=sparse_vecs[i].values,
            )
            # Deterministic point ID: user_id scoped — prevents cross-user point ID collision
            # even if two users index identical files at the same path.
            point_id = str(
                uuid.uuid5(uuid.NAMESPACE_DNS, f"{user_id}_{path_id}_{chunk.chunk_index}")
            )
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector={
                        "dense-vector": dense_vecs[i],
                        "sparse-vector": sparse_dict,
                    },
                    payload={
                        # Identity / isolation
                        "user_id": user_id,
                        "email_id": email_id,
                        "workspace_id": workspace_id,
                        "path_id": path_id,
                        "path": path,
                        # File metadata
                        "file_name": file_name,
                        "file_extension": file_extension,
                        "content_id": content_id,
                        # Chunk metadata (from tree-sitter)
                        "chunk_index": chunk.chunk_index,
                        "symbol": chunk.symbol,
                        "language": chunk.language,
                        # Content stored for retrieval
                        "content": chunk.content,   # header + code (shown to LLM)
                        "raw_content": chunk.raw_content,  # code only (for debug)
                    },
                )
            )

        self.client.upsert(collection_name=self.collection_name, points=points)
        logger.info(
            f"--- [WorkspaceQdrant] Upserted {len(points)} chunks "
            f"for path_id={path_id[:12]}... ---"
        )

    async def hybrid_search(
        self,
        query_text: str,
        query_dense: list[float],
        query_sparse,           # SparseVector schema object
        user_id: str,
        workspace_id: str,
        top_k: int = 5,
        path_id: str | None = None,
        chunk_index: int | None = None,
    ) -> list[dict]:
        """
        Hybrid RRF search scoped to user_id + workspace_id.
        Optional path_id and chunk_index narrow the scope further (LLM follow-up calls).
        Results are reranked before return.
        """
        # Build mandatory + optional filters
        must_conditions: List[models.Condition] = [
            models.FieldCondition(
                key="user_id", match=models.MatchValue(value=user_id)
            ),
            models.FieldCondition(
                key="workspace_id", match=models.MatchValue(value=workspace_id)
            ),
        ]
        if path_id:
            must_conditions.append(
                models.FieldCondition(
                    key="path_id", match=models.MatchValue(value=path_id)
                )
            )
        if chunk_index is not None:
            must_conditions.append(
                models.FieldCondition(
                    key="chunk_index", match=models.MatchValue(value=chunk_index)
                )
            )

        search_filter = models.Filter(must=must_conditions)
        candidate_limit = top_k * 4

        sparse_query = models.SparseVector(
            indices=query_sparse.indices,
            values=query_sparse.values,
        )

        try:
            async with asyncio.timeout(QDRANT_TIMEOUT):
                response = self.client.query_points(
                collection_name=self.collection_name,
                    prefetch=[
                        models.Prefetch(
                            query=query_dense,
                            using="dense-vector",
                            limit=candidate_limit,
                            filter=search_filter,
                            params=models.SearchParams(hnsw_ef=HNSW_EF),
                        ),
                        models.Prefetch(
                            query=sparse_query,
                            using="sparse-vector",
                            limit=candidate_limit,
                            filter=search_filter,
                        ),
                    ],
                    query=models.FusionQuery(fusion=models.Fusion.RRF),
                    limit=candidate_limit,
                )
        except TimeoutError:
            logger.error(f"--- [WorkspaceQdrant] Search timed out after {QDRANT_TIMEOUT}s ---")
            return []
        except Exception as e:
            logger.error(f"--- [WorkspaceQdrant] Search failed to execute: {repr(e)} ---")
            return []

        candidates = []
        for point in response.points:
            if point.payload:
                candidates.append({
                    "content":        point.payload.get("content", ""),
                    "metadata":       point.payload,
                    "rrf_score":      point.score,
                    "file_name":      point.payload.get("file_name", ""),
                    "file_extension": point.payload.get("file_extension", ""),
                    "path":           point.payload.get("path", ""),
                    "path_id":        point.payload.get("path_id", ""),
                    "workspace_id":   point.payload.get("workspace_id", ""),
                    "chunk_index":    point.payload.get("chunk_index", 0),
                    "content_id":     point.payload.get("content_id", ""),
                    "symbol":         point.payload.get("symbol"),
                    "language":       point.payload.get("language"),
                })

        if not candidates:
            return []

        try:
            reranked = await rerank_service.rerank(
                query=query_text,
                documents=candidates,
                top_n=top_k,
            )
            return reranked
        except Exception as e:
            logger.error(
                f"--- [WorkspaceQdrant] Reranking failed, falling back to RRF: {repr(e)} ---"
            )
            return candidates[:top_k]


workspace_qdrant_service = WorkspaceQdrantService()
