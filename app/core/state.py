
class SystemState:
    def __init__(self):
        self.is_text_dense_model_ready = False
        self.is_code_dense_model_ready = False
        self.is_text_sparse_model_ready = False
        self.is_reranker_model_ready = False
        self.is_workspace_collection_ready = False
        self.is_enterprise_collection_ready = False

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