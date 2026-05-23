
from typing import List

import logging
import os
import time
import uuid
import asyncio

from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from service.rerank_service import rerank_service
from workers.chunk_io import stream_embedded_batch, safe_remove

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

WORKSPACE_COLLECTION_DENSE_DIM = int(os.getenv("WORKSPACE_COLLECTION_DENSE_DIM", 768))
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
QDRANT_RETRIES = int(os.getenv("RETRIES", 5))
QDRANT_TIMEOUT = int(os.getenv("QDRANT_TIMEOUT", 60))
RERANK_THRESHOLD = float(os.getenv("RERANK_THRESHOLD", "0.0"))

WORKSPACE_COLLECTION = os.getenv(
    "WORKSPACE_COLLECTION", "Workspace_Knowledge_Base"
)
FINAL_COLLECTION_NAME = f"{WORKSPACE_COLLECTION}_{WORKSPACE_COLLECTION_DENSE_DIM}"

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
                    size=WORKSPACE_COLLECTION_DENSE_DIM,
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

    def delete_by_path_ids(self, user_id: str, workspace_id:str,path_ids: list[str]):
        if not path_ids:
            return
        must: List[models.Condition] = [
            models.FieldCondition(
                key="user_id", match=models.MatchValue(value=user_id)
            ),
            models.FieldCondition(
                key="workspace_id", match=models.MatchValue(value=workspace_id)
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


    def upsert_from_emb_file(
        self,
        emb_jsonl_path: str,
        upsert_meta: dict,
    ) -> dict:
        """
        Reads one .emb.jsonl batch file from disk, builds Qdrant PointStructs,
        bulk-upserts in one call, then deletes the batch file.
        """
        user_id        = upsert_meta["user_id"]
        email_id       = upsert_meta["email_id"]
        content_id     = upsert_meta["content_id"]
        workspace_id   = upsert_meta["workspace_id"]
        path_id        = upsert_meta["path_id"]
        path           = upsert_meta["path"]
        file_name      = upsert_meta["file_name"]
        file_extension = upsert_meta["file_extension"]

        points  = []
        skipped = 0

        for record in stream_embedded_batch(emb_jsonl_path):
            try:
                chunk       = record["chunk"]
                dense_vec   = record["dense_vec"]
                sparse_idxs = record["sparse_indices"]
                sparse_vals = record["sparse_values"]

                if not dense_vec or not sparse_idxs:
                    logger.warning(
                        f"[WorkspaceQdrant] Skipping chunk_index="
                        f"{chunk.get('chunk_index')} — empty vector"
                    )
                    skipped += 1
                    continue

                point_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_DNS,
                        f"{user_id}_{path_id}_{chunk['chunk_index']}",
                    )
                )
                points.append(
                    models.PointStruct(
                        id=point_id,
                        vector={
                            "dense-vector": dense_vec,
                            "sparse-vector": models.SparseVector(
                                indices=sparse_idxs,
                                values=sparse_vals,
                            ),
                        },
                        payload={
                            "user_id":        user_id,
                            "email_id":       email_id,
                            "workspace_id":   workspace_id,
                            "path_id":        path_id,
                            "path":           path,
                            "file_name":      file_name,
                            "file_extension": file_extension,
                            "content_id":     content_id,
                            "chunk_index":    chunk["chunk_index"],
                            "symbol":         chunk.get("symbol"),
                            "language":       chunk.get("language"),
                            "content":        chunk["content"],
                            "raw_content":    chunk.get("raw_content", ""),
                        },
                    )
                )
            except Exception as e:
                logger.error(
                    f"[WorkspaceQdrant] Skipping malformed record in "
                    f"{emb_jsonl_path}: {repr(e)}"
                )
                skipped += 1
                continue

        upserted = 0
        if points:
            try:
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=points,
                )
                upserted = len(points)
                logger.info(
                    f"[WorkspaceQdrant] Upserted {upserted} points "
                    f"path_id={path_id[:12]}... skipped={skipped}"
                )
            except Exception as e:
                logger.error(
                    f"[WorkspaceQdrant] Upsert failed for {emb_jsonl_path}: {repr(e)}"
                )
                raise

        safe_remove(emb_jsonl_path)
        return {"upserted": upserted, "skipped": skipped}

    async def hybrid_search(
        self,
        query_text: str,
        query_dense: list[float],
        query_sparse,
        user_id: str,
        workspace_id: str,
        top_k: int = 5,
        path_id: str | None = None,
        chunk_index: int | None = None,
    ) -> list[dict]:

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
        candidate_limit = top_k * 10 

        sparse_query = models.SparseVector(
            indices=query_sparse.indices,
            values=query_sparse.values,
        )

        try:
            async with asyncio.timeout(QDRANT_TIMEOUT):
                response = await asyncio.to_thread( 
                    self.client.query_points,
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
            logger.error(
                f"--- [WorkspaceQdrant] Search timed out after {QDRANT_TIMEOUT}s ---"
            )
            return []
        except Exception as e:
            logger.error(f"--- [WorkspaceQdrant] Search failed: {repr(e)} ---")
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

            filtered = [
                r for r in reranked
                if (r.get("rerank_score") or 0) > RERANK_THRESHOLD 
            ]

            if not filtered:
                logger.warning(
                    f"--- [WorkspaceQdrant] All {len(reranked)} results below "
                    f"rerank threshold {RERANK_THRESHOLD} — returning empty ---"
                )
                return []

            return filtered

        except Exception as e:
            logger.error(
                f"--- [WorkspaceQdrant] Reranking failed, falling back to RRF: {repr(e)} ---"
            )
            return candidates[:top_k]


workspace_qdrant_service = WorkspaceQdrantService()
