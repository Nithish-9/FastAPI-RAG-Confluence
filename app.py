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
        await asyncio.gather(
            loop.run_in_executor(executor, qdrant_service.init_infrastructure),
            loop.run_in_executor(executor, embed_service.load_dense_model),
            loop.run_in_executor(executor, embed_service.load_sparse_model),
            loop.run_in_executor(executor, rerank_service.load_reranker_model)
        )
        logger.info("--- [SYSTEM] Components Ready !!! ---")
    except Exception as e:
        logger.error(f"--- [SYSTEM] Initialization Failed: {e} ---")

    yield 
    
    logger.info("--- [SYSTEM] Shutting down ---")
    qdrant_service.close()
    executor.shutdown(wait=True)

app = FastAPI(lifespan=lifespan)

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
        asyncio.run(document_processor.extract(data, "CONFLUENCE"))
    except Exception as e:
        logger.error(f"Confluence Worker Error: {str(e)}")


@app.post("/documentupload")
async def upload_document(file: UploadFile = File(...)):

    original_name = file.filename or "unknown_file"
    _, ext = os.path.splitext(original_name)
    
    file_id = str(uuid.uuid4())
    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    
    temp_file_path = os.path.join(temp_dir, f"{file_id}{ext}")

    try:
        with open(temp_file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
            
        document_data = {
            "file_path": temp_file_path,
            "filename": original_name
        }

        loop = asyncio.get_running_loop()
        loop.run_in_executor(executor, run_file_ingestion_sync, document_data)

        return {"status": "success", "message": f"File {original_name} uploaded successfully"}
    
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during upload")

def run_file_ingestion_sync(data):
    try:
        asyncio.run(document_processor.extract(data, "FILE"))
    except Exception as e:
        logger.error(f"File Worker Error: {str(e)}")
    finally:
        if os.path.exists(data["file_path"]):
            os.remove(data["file_path"])
            logger.info(f"--- [CLEANUP] Deleted temp file: {data['file_path']} ---")


@app.post("/rag/retrieve")
async def retrieve_rag_data(request: RAGQueryRequest):
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
            detail="An error occurred during retrieval."
        )

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=9900, reload=True)