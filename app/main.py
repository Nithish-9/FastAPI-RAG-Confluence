import os
import logging
import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()
from core.config_validator import validate_config

try:
    validate_config()
except Exception as e:
    print(f"FATAL: Configuration Error -> {repr(e)}")
    exit(1)

import uvicorn
from fastapi import FastAPI
from service.generate_embedding import embed_service
from service.enterprise_qdrant_service import enterprise_qdrant_service
from service.workspace_qdrant_service import workspace_qdrant_service
from core.state import system_state
from service.rerank_service import rerank_service
from router.workspace_router import router as workspace_router
from router.enterprise_router import router as enterprise_router
from service.model_services import close_http_client

PORT = int(os.getenv("APP_PORT", 9000))
UVICORN_WORKERS = int(os.getenv("UVICORN_WORKERS", 4))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("--- [SYSTEM] Starting API Server ---")

    init_task = asyncio.create_task(initialize_all_components())

    def on_init_complete(task):
        try:
            task.result()
        except Exception as e:
            logger.error(
                f"--- [SYSTEM] CRITICAL: Background initialization failed: {repr(e)} ---"
            )

    init_task.add_done_callback(on_init_complete)
    logger.info(f"--- [SYSTEM] Startup sequence initiated (Port: {PORT}) ---")

    yield

    logger.info("--- [SYSTEM] Shutting down ---")
    enterprise_qdrant_service.close()
    workspace_qdrant_service.close()
    await close_http_client()
    logger.info("--- [SYSTEM] Shutdown complete ---")


app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health():
    return system_state.get_status()

app.include_router(workspace_router)
app.include_router(enterprise_router)

async def initialize_all_components():
    results = await asyncio.gather(
        enterprise_qdrant_service.init_collection(),
        workspace_qdrant_service.init_collection(),
        embed_service.check_dense_connectivity("text"),
        embed_service.check_dense_connectivity("code"),
        embed_service.check_sparse_connectivity(),
        rerank_service.check_reranker_connectivity(),
        return_exceptions=True,
    )

    is_enterprise_qdrant = results[0] if not isinstance(results[0], Exception) else False
    is_workspace_qdrant  = results[1] if not isinstance(results[1], Exception) else False
    is_text_dense        = results[2] if not isinstance(results[2], Exception) else False
    is_code_dense        = results[3] if not isinstance(results[3], Exception) else False  
    is_text_sparse       = results[4] if not isinstance(results[4], Exception) else False  
    is_rerank            = results[5] if not isinstance(results[5], Exception) else False  

    system_state.set_enterprise_collection_state(is_enterprise_qdrant)
    system_state.set_workspace_collection_state(is_workspace_qdrant)   
    system_state.set_text_dense_model_state(is_text_dense)
    system_state.set_code_dense_model_state(is_code_dense)
    system_state.set_text_sparse_model_state(is_text_sparse)
    system_state.set_reranker_model_state(is_rerank)

    if not all([is_enterprise_qdrant, is_workspace_qdrant, is_text_dense,
                is_code_dense, is_text_sparse, is_rerank]):
        logger.error(
            f"Initialization Failed: "
            f"EQ:{is_enterprise_qdrant} WQ:{is_workspace_qdrant} "
            f"TD:{is_text_dense} CD:{is_code_dense} "
            f"TS:{is_text_sparse} R:{is_rerank}"
        )
    else:
        logger.info("--- [SYSTEM] Core Infra Ready: All Systems Go ---")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False,workers=UVICORN_WORKERS)