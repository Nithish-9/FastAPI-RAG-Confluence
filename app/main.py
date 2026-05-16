import os
import uuid
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
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from service import document_processor
from schemas.rag_dto import RAGQueryRequest
from service.generate_embedding import embed_service
from service.enterprise_qdrant_service import enterprise_qdrant_service
from service.workspace_qdrant_service import workspace_qdrant_service
from core.state import system_state
from service.rerank_service import rerank_service
from router.workspace_router import router as workspace_router
from service.model_services import close_http_client

PORT = int(os.getenv("APP_PORT", 9000))

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
            logger.info("--- [SYSTEM] Core Infra Ready: All Systems Go ---")
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

app.include_router(workspace_router)


async def initialize_all_components():
    results = await asyncio.gather(
        asyncio.to_thread(enterprise_qdrant_service.init_collection),
        asyncio.to_thread(workspace_qdrant_service.init_collection),
        embed_service.check_dense_connectivity(),
        embed_service.check_sparse_connectivity(),
        rerank_service.check_reranker_connectivity(),
        return_exceptions=True,
    )

    is_qdrant           = results[0] if not isinstance(results[0], Exception) else False
    is_workspace_qdrant = results[1] if not isinstance(results[1], Exception) else False
    is_dense            = results[2] if not isinstance(results[2], Exception) else False
    is_sparse           = results[3] if not isinstance(results[3], Exception) else False
    is_rerank           = results[4] if not isinstance(results[4], Exception) else False

    system_state.set_vector_db_state(is_qdrant and is_workspace_qdrant)
    system_state.set_dense_model_state(is_dense)
    system_state.set_sparse_model_state(is_sparse)
    system_state.set_reranker_model_state(is_rerank)

    if not all([is_qdrant, is_workspace_qdrant, is_dense, is_sparse, is_rerank]):
        logger.error(
            f"Initialization Failed: "
            f"Q:{is_qdrant} WQ:{is_workspace_qdrant} "
            f"D:{is_dense} S:{is_sparse} R:{is_rerank}"
        )


@app.get("/health")
async def health():
    return system_state.get_status()


@app.post("/webhook/confluence")
async def ingest_confluence_webhook(request: Request):
    data = await request.json()
    asyncio.create_task(_background_task(data, "CONFLUENCE"))
    return {"status": "success", "message": "Confluence ingestion queued"}


@app.post("/documentupload")
async def upload_document(file: UploadFile = File(...)):
    if not system_state.is_system_ready():
        return JSONResponse(
            status_code=503,
            content={"status": "loading", "message": "Services unavailable or warming up"},
        )

    file_id = str(uuid.uuid4())
    temp_path = os.path.join(
        "temp_uploads",
        f"{file_id}{os.path.splitext(file.filename or '')[1]}",
    )
    os.makedirs("temp_uploads", exist_ok=True)

    with open(temp_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            buffer.write(chunk)

    doc_data = {"file_path": temp_path, "filename": file.filename}
    asyncio.create_task(_background_task(doc_data, "FILE"))

    return {"status": "success", "message": f"File {file.filename} queued"}


async def _background_task(data: dict, source_type: str):
    """
    Async background task — runs the document processor and cleans up temp
    files. Uses asyncio.to_thread for any blocking I/O inside document_processor.
    """
    try:
        await document_processor.extract(data, source_type)
    except Exception as e:
        logger.error(f"Worker Error [{source_type}]: {repr(e)}")
    finally:
        if source_type == "FILE":
            f_path = data.get("file_path", "")
            if f_path and os.path.exists(f_path):
                try:
                    os.remove(f_path)
                    logger.info(f"Cleanup: Removed {f_path}")
                except Exception as e:
                    logger.warning(f"Cleanup Failed for {f_path}: {e}")


@app.post("/rag/retrieve")
async def retrieve_rag_data(request: RAGQueryRequest):
    if not system_state.is_system_ready():
        raise HTTPException(
            status_code=503, detail="Search infrastructure is not fully ready"
        )

    try:
        dense_vecs, sparse_vecs = await embed_service.get_combined_embeddings(
            [request.query]
        )
        results = await enterprise_qdrant_service.hybrid_search(
            query_text=request.query,
            query_dense=dense_vecs[0],
            query_sparse=sparse_vecs[0],
            limit=request.top_k,
            page_id=request.page_id,
            chunk_index=request.chunk_index,
        )
        return {"status": "success", "count": len(results), "data": results}
    except Exception as e:
        logger.error(f"RAG Error: {repr(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False,workers=4)