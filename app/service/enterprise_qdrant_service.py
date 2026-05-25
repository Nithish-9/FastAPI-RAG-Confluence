import uuid
import os
import asyncio 
import logging
import time

from typing import List
from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from service.rerank_service import rerank_service
from workers.chunk_io import stream_embedded_batch, safe_remove

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

ENTERPRISE_COLLECTION_DENSE_DIM = int(os.getenv("ENTERPRISE_COLLECTION_DENSE_DIM", 768))
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
QDRANT_RETRIES = int(os.getenv("QDRANT_RETRIES", 5))
QDRANT_TIMEOUT = int(os.getenv("QDRANT_TIMEOUT", 60))
RERANK_THRESHOLD = float(os.getenv("RERANK_THRESHOLD", "0.0"))

ENTERPRISE_COLLECTION = os.getenv("ENTERPRISE_COLLECTION", "Enterprise_Knowledge_Base")
FINAL_COLLECTION_NAME = f"{ENTERPRISE_COLLECTION}_{ENTERPRISE_COLLECTION_DENSE_DIM}"

QDRANT_INDEXING_THREADS = int(os.getenv("QDRANT_INDEXING_THREADS", 0))
DIST_STR = os.getenv("DENSE_DISTANCE", "COSINE").upper()
DISTANCE_METRIC = getattr(models.Distance, DIST_STR)

QDRANT_ON_DISK = os.getenv("QDRANT_ON_DISK", "true").lower() == "true"
HNSW_M = int(os.getenv("HNSW_M", 16))
HNSW_EF_CONSTRUCT = int(os.getenv("HNSW_EF_CONSTRUCT", 100))
HNSW_EF = int(os.getenv("HNSW_EF", 128))
SPARSE_THRESHOLD = int(os.getenv("SPARSE_FULL_SCAN_THRESHOLD", 1000))

class EnterpriseQdrantService:
    def __init__(self):
        self.client = QdrantClient(
            host=QDRANT_HOST, 
            port=QDRANT_PORT,
            timeout=60
        )
        self.collection_name = FINAL_COLLECTION_NAME
    
    async def init_collection(self, retries=QDRANT_RETRIES):
        return await asyncio.to_thread(self._init_collection_sync, retries)

    def _init_collection_sync(self, retries):
        logger.info(f"--- [EnterpriseQdrant] Initializing connection to {self.collection_name} ---")
        
        for attempt in range(retries):
            try:
                self.client.get_collection(self.collection_name)
                logger.info(
                    f"--- [EnterpriseQdrant] Collection '{self.collection_name}' exists. ---"
                )
                return True 
            
            except UnexpectedResponse as e:
                if e.status_code == 404:
                    logger.info("--- [EnterpriseQdrant] Creating new collection... ---")
                    self._create_collection()
                    return True 
                raise e
            except Exception as e:
                wait = min(2 ** (attempt + 1), 30) 
                
                if attempt < retries - 1:
                    logger.warning(f"[EnterpriseQdrant] Attempt {attempt+1} failed. Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"[EnterpriseQdrant] Max retries reached. Connection failed.")
        
        return False

    def _create_collection(self):
        logger.info(f"--- [EnterpriseQdrant] Creating collection: {self.collection_name} ---")
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                "dense-vector": models.VectorParams(
                    size=ENTERPRISE_COLLECTION_DENSE_DIM,
                    distance=DISTANCE_METRIC,
                    on_disk=QDRANT_ON_DISK,
                    hnsw_config=models.HnswConfigDiff(
                        m=HNSW_M,
                        ef_construct=HNSW_EF_CONSTRUCT,
                        on_disk=QDRANT_ON_DISK,
                        max_indexing_threads=QDRANT_INDEXING_THREADS
                    )
                )
            },
            sparse_vectors_config={
                "sparse-vector": models.SparseVectorParams(
                    index=models.SparseIndexParams(
                        on_disk=QDRANT_ON_DISK,
                        full_scan_threshold=SPARSE_THRESHOLD
                    )
                )
            }
        )
        self.client.create_payload_index(
            collection_name=self.collection_name,
            field_name="page_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        logger.info(f"--- [EnterpriseQdrant] Schema created with HNSW(M={HNSW_M}) and OnDisk={QDRANT_ON_DISK} ---")
        logger.info(
            f"--- [EnterpriseQdrant] Collection created with index on "
            f"[page_id] ---"
        )

    def close(self):
        logger.info("--- [EnterpriseQdrant] Closing client connection... ---")
        self.client.close()

    def check_doc_changed(self, page_id: str) -> bool:
        results, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=models.Filter(
                must=[models.FieldCondition(key="page_id", match=models.MatchValue(value=page_id))]
            ),
            limit=1,
            with_payload=False,
            with_vectors=False
        )
        return len(results) == 0

    def check_confluence_changed(self, page_id: str, new_hash: str) -> bool:
        results, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=models.Filter(
                must=[models.FieldCondition(key="page_id", match=models.MatchValue(value=page_id))]
            ),
            limit=1,
            with_payload=True,
            with_vectors=False
        )
        if not results:
            return True 
        payload = results[0].payload
        if payload is None:
            return True
        old_hash = payload.get("content_hash")
        return old_hash != new_hash
    

    def upsert_from_emb_file(
        self,
        emb_jsonl_path: str,
        page_id: str,
    ) -> dict:
        """
        Reads one .emb.jsonl batch, bulk-upserts to enterprise collection.
        Per-point isolation: bad point is skipped, rest of batch continues.
        """
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
                        f"[EnterpriseDBWrite] Skipping chunk_index="
                        f"{chunk.get('chunk_index')} — empty vector"
                    )
                    skipped += 1
                    continue

                idx      = chunk.get("chunk_index", 0)
                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{page_id}_{idx}"))

                payload = {**chunk.get("metadata", {}), "content": chunk.get("content", "")}

                points.append(
                    models.PointStruct(
                        id=point_id,
                        vector={
                            "dense-vector":  dense_vec,
                            "sparse-vector": models.SparseVector(
                                indices=sparse_idxs,
                                values=sparse_vals,
                            ),
                        },
                        payload=payload,
                    )
                )
            except Exception as e:
                logger.error(
                    f"[EnterpriseDBWrite] Skipping malformed record "
                    f"in {emb_jsonl_path}: {repr(e)}"
                )
                skipped += 1
                continue

        upserted = 0
        if points:
            try:
                enterprise_qdrant_service.client.upsert(
                    collection_name=enterprise_qdrant_service.collection_name,
                    points=points,
                )
                upserted = len(points)
                logger.info(
                    f"[EnterpriseDBWrite] Upserted {upserted} points "
                    f"page_id={page_id[:12]}... skipped={skipped}"
                )
            except Exception as e:
                logger.error(
                    f"[EnterpriseDBWrite] Qdrant upsert failed "
                    f"for {emb_jsonl_path}: {repr(e)}"
                )
                raise

        safe_remove(emb_jsonl_path)
        return {"upserted": upserted, "skipped": skipped}

    def delete_by_page_ids(self, page_ids: list[str]):
        if not page_ids:
            return
        must: List[models.Condition] = [
            models.FieldCondition(
                key="page_id",
                match=models.MatchAny(any=page_ids),
            ),
        ]
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.Filter(must=must),
        )
        logger.info(
            f"--- [EnterpriseQdrant] Deleted chunks for {len(page_ids)} page_id(s) "
        )

    async def hybrid_search(
        self,
        query_text: str,
        query_dense: list,
        query_sparse,
        limit: int = 5,
        page_id: str | None = None,
        chunk_index: int | None = None,
    ) -> list[dict]:

        filter_conditions: List[models.Condition] = []   
        if page_id:
            filter_conditions.append(
                models.FieldCondition(key="page_id", match=models.MatchValue(value=page_id))
            )
        if chunk_index is not None:
            filter_conditions.append(
                models.FieldCondition(key="chunk_index", match=models.MatchValue(value=chunk_index))
            )

        search_filter = models.Filter(must=filter_conditions) if filter_conditions else None
        candidate_limit = limit * 10 

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
            logger.error(f"--- [EnterpriseQdrant] Search timed out after {QDRANT_TIMEOUT}s ---")
            return []
        except Exception as e:
            logger.error(f"--- [EnterpriseQdrant] Search failed: {repr(e)} ---")
            return []

        candidates = []
        for point in response.points:
            if point.payload:
                candidates.append({
                    "content":   point.payload.get("content", ""),
                    "metadata":  point.payload,
                    "rrf_score": point.score, 
                })

        if not candidates:
            return []

        try:
            reranked = await rerank_service.rerank(
                query=query_text,
                documents=candidates,
                top_n=limit,
            )

            filtered = [
                r for r in reranked
                if (r.get("rerank_score") or 0) > RERANK_THRESHOLD
            ]

            if not filtered:
                logger.warning(
                    f"--- [EnterpriseQdrant] All {len(reranked)} results below "
                    f"rerank threshold {RERANK_THRESHOLD} — returning empty ---"
                )
                return []

            return filtered

        except Exception as e:
            logger.error(
                f"--- [EnterpriseQdrant] Reranking failed, falling back to RRF: {repr(e)} ---"
            )
            return candidates[:limit]
    
enterprise_qdrant_service = EnterpriseQdrantService()