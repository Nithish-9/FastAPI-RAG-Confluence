import uuid
import os
from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from service.rerank_service import rerank_service
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

logger = logging.getLogger(__name__)

class QdrantService:
    def __init__(self):
        self.client = QdrantClient(
            host=os.getenv("QDRANT_HOST", "localhost"), 
            port=int(os.getenv("QDRANT_PORT", 6333))
        )
        self.collection_name = "enterprise_knowledge_base"



    def init_qdrant(self, retries=5, delay=5):
        logger.info(f"--- [Qdrant] Initializing connection to {self.collection_name} ---")
        
        for attempt in range(retries):
            try:
                self.client.get_collection(self.collection_name)
                logger.info(f"--- [Qdrant] Collection '{self.collection_name}' already exists. ---")
                return True 

            except UnexpectedResponse as e:
                if e.status_code == 404:
                    logger.info(f"--- [Qdrant] Collection not found. Creating new schema... ---")
                    self.create_collection()
                    return True 
                else:
                    logger.warning(f"[Qdrant] Unexpected response (Attempt {attempt+1}): {e}")
            
            except Exception as e:
                logger.warning(f"[Qdrant] Connection attempt {attempt+1} failed. Retrying in {delay}s...")
            
            time.sleep(delay)

        logger.error("--- [Qdrant] Initialization FAILED: Could not connect to database. ---")
        return False

    def create_collection(self):
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                "dense-vector": models.VectorParams(
                    size=768,
                    distance=models.Distance.COSINE
                )
            },
            sparse_vectors_config={
                "sparse-vector": models.SparseVectorParams(
                    index=models.SparseIndexParams(on_disk=True)
                )
            }
        )

        self.client.create_payload_index(
            collection_name=self.collection_name,
            field_name="page_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        
        logger.info(f"--- [Qdrant] Collection and Page ID Index created. ---")
    
    def close(self):
        logger.info("--- [Qdrant] Closing client connection... ---")
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

    def upsert_chunks(self, chunks, dense_vecs, sparse_vecs):
        points = []
        for i, chunk in enumerate(chunks):
            sparse_dict = models.SparseVector(
                indices=sparse_vecs[i].indices.tolist(),
                values=sparse_vecs[i].values.tolist()
            )
            
            page_id = chunk.metadata["page_id"]
            idx = chunk.metadata["chunk_index"]
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{page_id}_{idx}"))

            points.append(models.PointStruct(
                id=point_id,
                vector={
                    "dense-vector": dense_vecs[i].tolist(), 
                    "sparse-vector": sparse_dict 
                },
                payload={**chunk.metadata, "content": chunk.page_content}
            ))

        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )

    def delete_chunks(self, page_id: str):
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.Filter(
                must=[models.FieldCondition(key="page_id", match=models.MatchValue(value=page_id))]
            )
        )

    async def hybrid_search(self, query_text, query_dense, query_sparse, limit=5, alpha=0.5, page_id=None, chunk_index=None):
        filter_conditions = []
        if page_id:
            filter_conditions.append(models.FieldCondition(key="page_id", match=models.MatchValue(value=page_id)))
        if chunk_index is not None:
            filter_conditions.append(models.FieldCondition(key="chunk_index", match=models.MatchValue(value=chunk_index)))

        search_filter = models.Filter(must=filter_conditions) if filter_conditions else None

        candidate_limit = limit * 4 

        sparse_query = models.SparseVector(
            indices=query_sparse.indices.tolist(),
            values=query_sparse.values.tolist()
        )

        response = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                models.Prefetch(
                    query=query_dense,
                    using="dense-vector",
                    limit=candidate_limit,
                    filter=search_filter
                ),
                models.Prefetch(
                    query=sparse_query,
                    using="sparse-vector",
                    limit=candidate_limit,
                    filter=search_filter
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=candidate_limit
        )

        candidates = []
        for point in response.points:
            if point.payload:
                candidates.append({
                    "content": point.payload.get("content", ""),
                    "metadata": point.payload,
                    "rrf_score": point.score
                })

        if not candidates:
            return []

        try:
            
            final_results = await rerank_service.rerank(
                query=query_text, 
                documents=candidates, 
                top_n=limit
            )
            return final_results
            
        except Exception as e:
            logger.error(f"--- [Qdrant] Reranking failed, falling back to RRF: {e} ---")
            return candidates[:limit]
    
qdrant_service = QdrantService()