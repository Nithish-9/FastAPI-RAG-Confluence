import os
import uuid
import logging
import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

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

PORT = int(os.getenv("APP_PORT", 9900))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
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
            logger.error(f"--- [SYSTEM] CRITICAL: Background initialization failed: {e} ---")

    init_task.add_done_callback(on_init_complete)
    
    logger.info(f"--- [SYSTEM] Startup sequence initiated (Port: {PORT}) ---")
    
    yield

    logger.info("--- [SYSTEM] Shutting down ---")
    qdrant_service.close()
    executor.shutdown(wait=True)

app = FastAPI(lifespan=lifespan)

async def initialize_all_components():
    loop = asyncio.get_running_loop()
    
    results = await asyncio.gather(
        loop.run_in_executor(executor, qdrant_service.init_qdrant),
        loop.run_in_executor(executor, embed_service.load_dense_model),
        loop.run_in_executor(executor, embed_service.load_sparse_model),
        loop.run_in_executor(executor, rerank_service.load_reranker_model),
        return_exceptions=True 
    )

    is_qdrant = results[0] if not isinstance(results[0], Exception) else False
    is_dense  = results[1] if not isinstance(results[1], Exception) else False
    is_sparse = results[2] if not isinstance(results[2], Exception) else False
    is_rerank = results[3] if not isinstance(results[3], Exception) else False


    system_state.set_vector_db_state(is_qdrant)
    system_state.set_dense_model_state(is_dense)
    system_state.set_sparse_model_state(is_sparse)
    system_state.set_reranker_model_state(is_rerank)

    if not all(results):
        error_msg = f"Partial Success - Q:{is_qdrant} D:{is_dense} S:{is_sparse} R:{is_rerank}"
        raise RuntimeError(error_msg)

@app.get("/health")
async def health():
    return system_state.get_status()

@app.post("/webhook/confluence")
async def ingest_confluence_webhook(request: Request):
    data = await request.json()
    asyncio.get_running_loop().run_in_executor(executor, run_worker_task, data, "CONFLUENCE")
    return {"status": "success", "message": "Confluence ingestion queued"}

@app.post("/documentupload")
async def upload_document(file: UploadFile = File(...)):
    if not system_state.is_system_ready():
        return JSONResponse(status_code=503, content={"status": "loading", "message": "System warming up"})

    file_id = str(uuid.uuid4())
    temp_path = os.path.join("temp_uploads", f"{file_id}{os.path.splitext(file.filename or '')[1]}")
    os.makedirs("temp_uploads", exist_ok=True)

    with open(temp_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            buffer.write(chunk)

    doc_data = {"file_path": temp_path, "filename": file.filename}
    asyncio.get_running_loop().run_in_executor(executor, run_worker_task, doc_data, "FILE")
    
    return {"status": "success", "message": f"File {file.filename} queued for processing"}

def run_worker_task(data, source_type):
    try:
        asyncio.run(document_processor.extract(data, source_type))
    except Exception as e:
        logger.error(f"Worker Error [{source_type}]: {e}")
    finally:
        if source_type == "FILE" and os.path.exists(data.get("file_path", "")):
            os.remove(data["file_path"])
            logger.info(f"Cleanup: Removed {data['file_path']}")

@app.post("/rag/retrieve")
async def retrieve_rag_data(request: RAGQueryRequest):
    if not system_state.is_system_ready():
        raise HTTPException(status_code=503, detail="Models still loading")

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
        return {"status": "success", "count": len(results), "data": results}
    except Exception as e:
        logger.error(f"RAG Error: {e}")
        raise HTTPException(status_code=500, detail="Retrieval failed")

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=False)