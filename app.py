import os
import uuid
import logging
import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv

import uvicorn
from fastapi import FastAPI, Request, UploadFile, File, HTTPException, status
from fastapi.responses import JSONResponse

from service import document_processor
from models.rag_model import RAGQueryRequest
from service.generate_embedding import embed_service
from service.qdrant_service import qdrant_service
from core.concurrency import executor
from core.state import system_state
from service.rerank_service import rerank_service

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)



@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    logger.info("--- [SYSTEM] Initializing Components ---")

    try:
        is_qdrant_ready = await loop.run_in_executor(
            executor, qdrant_service.init_qdrant
        )

        if not is_qdrant_ready:
            logger.error("--- [SYSTEM] Qdrant not ready. Shutting down ---")
            raise RuntimeError("Qdrant initialization failed")
        
        system_state.set_vector_db_state(is_qdrant_ready)

        task = asyncio.create_task(preload_models())

        def handle_task_result(task):
            try:
                task.result()
            except Exception as e:
                logger.error(f"--- [SYSTEM] Background preload crashed: {e} ---")

        task.add_done_callback(handle_task_result)

        logger.info("--- [SYSTEM] Core Infra Ready ---")

    except Exception as e:
        logger.error(f"--- [SYSTEM] Initialization Failed: {e} ---")

    yield

    logger.info("--- [SYSTEM] Shutting down ---")
    qdrant_service.close()
    executor.shutdown(wait=True)


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return system_state.get_status()



async def preload_models():
    loop = asyncio.get_running_loop()
    logger.info("--- [SYSTEM] Loading Models in Background ---")

    try:
        is_dense_ready, is_sparse_ready, is_reranker_ready = await asyncio.gather(
            loop.run_in_executor(executor, embed_service.load_dense_model),
            loop.run_in_executor(executor, embed_service.load_sparse_model),
            loop.run_in_executor(executor, rerank_service.load_reranker_model)
        )

        system_state.set_dense_model_state(is_dense_ready)
        system_state.set_sparse_model_state(is_sparse_ready)
        system_state.set_reranker_model_state(is_reranker_ready)

        if all([is_dense_ready, is_sparse_ready, is_reranker_ready]):
            logger.info("--- [SYSTEM] All Models Ready ---")
        else:
            logger.warning(
                f"--- [SYSTEM] Partial readiness | "
                f"Dense: {is_dense_ready}, "
                f"Sparse: {is_sparse_ready}, "
                f"Reranker: {is_reranker_ready} ---"
            )

    except Exception as e:
        logger.error(f"--- [SYSTEM] Model preload failed: {e} ---")



@app.post("/webhook/confluence")
async def ingest_confluence_webhook(request: Request):
    try:
        data = await request.json()
        loop = asyncio.get_running_loop()

        loop.run_in_executor(executor, run_confluence_ingestion, data)

        return {"status": "success", "message": "Confluence ingestion started"}

    except Exception as e:
        logger.error(f"Webhook Submission Failed: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": "Failed to submit webhook"}
        )


def run_confluence_ingestion(data):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(document_processor.extract(data, "CONFLUENCE"))
    except Exception as e:
        logger.error(f"Confluence Worker Error: {str(e)}")


@app.post("/documentupload")
async def upload_document(file: UploadFile = File(...)):

    if not system_state.is_system_ready():
        return JSONResponse(
            status_code=503,
            content={"status": "loading", "message": "System is warming up"}
        )

    original_name = file.filename or "unknown_file"
    _, ext = os.path.splitext(original_name)

    file_id = str(uuid.uuid4())
    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)

    temp_file_path = os.path.join(temp_dir, f"{file_id}{ext}")

    try:
        with open(temp_file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                buffer.write(chunk)

        document_data = {
            "file_path": temp_file_path,
            "filename": original_name
        }

        loop = asyncio.get_running_loop()
        loop.run_in_executor(executor, run_file_ingestion_sync, document_data)

        return {
            "status": "success",
            "message": f"File {original_name} uploaded successfully"
        }

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")


def run_file_ingestion_sync(data):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(document_processor.extract(data, "FILE"))

    except Exception as e:
        logger.error(f"File Worker Error: {str(e)}")

    finally:
        if os.path.exists(data["file_path"]):
            os.remove(data["file_path"])
            logger.info(f"--- [CLEANUP] Deleted temp file: {data['file_path']} ---")


@app.post("/rag/retrieve")
async def retrieve_rag_data(request: RAGQueryRequest):

    if not system_state.is_system_ready():
        return JSONResponse(
            status_code=503,
            content={"status": "loading", "message": "System is warming up"}
        )

    try:
        dense_vecs, sparse_vecs = await embed_service.get_combined_embeddings([request.query])

        results = await qdrant_service.hybrid_search(
            query_text=request.query,
            query_dense=dense_vecs[0],
            query_sparse=sparse_vecs[0],
            limit=request.top_k,
            alpha=request.alpha,
            page_id=request.page_id,
            chunk_index=request.chunk_index
        )

        return {
            "status": "success",
            "count": len(results),
            "data": results
        }

    except Exception as e:
        logger.error(f"RAG Retrieval Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Retrieval failed"
        )



if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=9900, reload=True)