from fastapi import FastAPI, Request
import uvicorn
from service import wb_confluence_service 
from models.rag_model import RAGQueryRequest
from service.embedding_service import embed_service
from service.qdrant_service import qdrant_service
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
import logging
import asyncio
from contextlib import asynccontextmanager
from core.concurrency import executor
from dotenv import load_dotenv

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
    
    await asyncio.gather(
        loop.run_in_executor(executor, qdrant_service.init_infrastructure),
        loop.run_in_executor(executor, embed_service.load_dense_model),
        loop.run_in_executor(executor, embed_service.load_sparse_model)
    )
    logger.info("--- [SYSTEM] Components Ready !!! ---")

    yield 
    
    logger.info("--- [SYSTEM] Shutting down ---")
    qdrant_service.close()
    executor.shutdown(wait=True)

server = FastAPI(lifespan=lifespan)


@server.post("/webhook/confluence")
async def ingest_confluence_webhook(request: Request):
    try:
        data = await request.json()
        loop = asyncio.get_running_loop()
        loop.run_in_executor(executor, run_ingestion_sync, data)
        
        return {"status": "success", "message": "Ingestion process started"}
    except Exception as e:
        logger.error(f"Webhook Submission Failed: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": "Failed to submit webhook"}
        )

def run_ingestion_sync(data):
    try:
        asyncio.run(wb_confluence_service.extract(data))
    except Exception as e:
        logger.error(f"Background Worker Error: {str(e)}")

@server.post("/rag/retrieve")
async def retrieve_rag_data(request: RAGQueryRequest):
    logger.info(f"--- RAG Request Received ---")
    logger.info(f"Query: {request.query}")
    
    try:
        dense_vecs, sparse_vecs = await embed_service.get_combined_embeddings([request.query])
        
        results = await qdrant_service.hybrid_search(
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

    except ConnectionError:
        logger.error("Qdrant connection refused.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector database is currently unreachable."
        )
    except Exception as e:
        logger.error(f"RAG Retrieval Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during retrieval: {str(e)}"
        )

if __name__ == "__main__":
    uvicorn.run("app:server", port=9900, reload=True)