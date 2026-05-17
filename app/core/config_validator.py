import os
import logging

logger = logging.getLogger(__name__)

def get_env_bool(key: str, default: str = "false") -> bool:
    return os.getenv(key, default).lower() == "true"

def get_env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default

def validate_config():

    errors = []

    if not os.getenv("QDRANT_HOST"):
        errors.append("QDRANT_HOST is missing.")
    
    if not os.getenv("ENTERPRISE_COLLECTION_DENSE_DIM"):
        errors.append("ENTERPRISE_COLLECTION_DENSE_DIM must be set for Enterprise collection schema alignment.")
    
    if not os.getenv("WORKSPACE_COLLECTION_DENSE_DIM"):
        errors.append("WORKSPACE_COLLECTION_DENSE_DIM must be set for Workspace collection schema alignment.")
    
    for prefix in ["TEXT_DENSE","CODE_DENSE","TEXT_SPARSE", "RERANKER"]:
        is_hosted = get_env_bool(f"{prefix}_HOSTED")
        url = os.getenv(f"{prefix}_URL")
        
        if not url:
            errors.append(f"{prefix}_URL is missing.")
        
        if is_hosted:
            if not os.getenv(f"{prefix}_API_KEY"):
                errors.append(f"{prefix} is set to HOSTED but {prefix}_API_KEY is missing.")
            if not os.getenv(f"{prefix}_MODEL"):
                errors.append(f"{prefix} is set to HOSTED but {prefix}_MODEL name is missing.")
    
    if not os.getenv("CONFLUENCE_BASE_URL") or not os.getenv("API_TOKEN"):
        logger.warning("Confluence credentials missing; ingest might fail.")

    if errors:
        error_msg = "\n".join([f"  - {err}" for err in errors])
        raise ValueError(f"Configuration Validation Failed:\n{error_msg}")

    logger.info("--- [Config] Environment validation successful. ---")
