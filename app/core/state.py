
class SystemState:
    def __init__(self):
        self.is_dense_model_ready = False
        self.is_sparse_model_ready = False
        self.is_reranker_model_ready = False
        self.is_vectordb_ready = False

    def set_vector_db_state(self, is_ready):
        self.is_vectordb_ready = is_ready

    def set_reranker_model_state(self, is_ready):
        self.is_reranker_model_ready = is_ready

    def set_sparse_model_state(self, is_ready):
        self.is_sparse_model_ready = is_ready

    def set_dense_model_state(self, is_ready):
        self.is_dense_model_ready = is_ready

    def is_system_ready(self) -> bool:
        return (
                self.is_vectordb_ready and
                self.is_dense_model_ready and
                self.is_sparse_model_ready and
                self.is_reranker_model_ready
            )
        
    def get_status(self):
        return {
            "dense": self.is_dense_model_ready,
            "sparse": self.is_sparse_model_ready,
            "reranker": self.is_reranker_model_ready,
            "vectordb": self.is_vectordb_ready
        }


system_state = SystemState()