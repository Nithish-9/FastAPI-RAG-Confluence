import redis.asyncio as aioredis
import os

QUEUE_DEPTH_THRESHOLD = int(os.getenv("QUEUE_DEPTH_THRESHOLD", 1000))

class SystemState:
    def __init__(self):
        self.is_text_dense_model_ready = False
        self.is_code_dense_model_ready = False
        self.is_text_sparse_model_ready = False
        self.is_reranker_model_ready = False
        self.is_workspace_collection_ready = False
        self.is_enterprise_collection_ready = False
        self._redis: aioredis.Redis | None = None  
    
    def set_redis_client(self, client: aioredis.Redis) -> None:
        self._redis = client

    def set_enterprise_collection_state(self, is_ready):
        self.is_enterprise_collection_ready = is_ready
    
    def set_workspace_collection_state(self, is_ready):
        self.is_workspace_collection_ready = is_ready

    def set_reranker_model_state(self, is_ready):
        self.is_reranker_model_ready = is_ready

    def set_text_sparse_model_state(self, is_ready):
        self.is_text_sparse_model_ready = is_ready

    def set_text_dense_model_state(self, is_ready):
        self.is_text_dense_model_ready = is_ready
    
    def set_code_dense_model_state(self, is_ready):
        self.is_code_dense_model_ready = is_ready
    

    def is_system_ready(self) -> bool:
        return (
                self.is_enterprise_collection_ready and
                self.is_workspace_collection_ready and
                self.is_text_dense_model_ready and
                self.is_code_dense_model_ready and
                self.is_text_sparse_model_ready and
                self.is_reranker_model_ready
            )

    async def is_workspace_queue_healthy(self) -> bool:
        if self._redis is None:
            return False
        try:
            w_embed   = await self._redis.llen("workspace_embed")   # type: ignore[union-attr]
            w_dbwrite = await self._redis.llen("workspace_dbwrite") # type: ignore[union-attr]
            return w_embed < QUEUE_DEPTH_THRESHOLD and w_dbwrite < QUEUE_DEPTH_THRESHOLD
        except Exception:
            return False

    async def is_enterprise_queue_healthy(self) -> bool:
        if self._redis is None:
            return False
        try:
            e_embed   = await self._redis.llen("enterprise_embed")   # type: ignore[union-attr]
            e_dbwrite = await self._redis.llen("enterprise_dbwrite") # type: ignore[union-attr]
            return e_embed < QUEUE_DEPTH_THRESHOLD and e_dbwrite < QUEUE_DEPTH_THRESHOLD
        except Exception:
            return False
        
    def get_status(self):
        return {
            "text_dense": self.is_text_dense_model_ready,
            "code_dense": self.is_code_dense_model_ready,
            "text_sparse": self.is_text_sparse_model_ready,
            "reranker": self.is_reranker_model_ready,
            "workspace_kb": self.is_workspace_collection_ready,
            "enterprise_kb": self.is_enterprise_collection_ready
        }


system_state = SystemState()