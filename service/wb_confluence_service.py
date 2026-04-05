import os
import hashlib
import asyncio
from langchain_community.document_loaders import ConfluenceLoader
from service.confluence_page_processor import documentProcessor
from service.embedding_service import embed_service
from service.qdrant_service import qdrant_service 
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

logger = logging.getLogger(__name__)

CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL")
EMAIL = os.getenv("EMAIL")
API_TOKEN = os.getenv("API_TOKEN")

async def extract(confluence_data: dict) -> None:
    page = confluence_data.get("page", {})
    page_id = str(page.get("id"))
    
    if not page_id or page_id == "None":
        logger.info("--- [Worker] Invalid page data received ---")
        return

    doc = await get_page_content(page_id)
    if not doc:
        return

    new_content_hash = hashlib.sha256(doc.page_content.encode()).hexdigest()
    
    if not qdrant_service.check_if_changed(page_id, new_content_hash):
        logger.info(f"--- [Worker] Page {page_id} unchanged. Skipping. ---")
        return

    logger.info(f"--- [Worker] Processing Page {page_id} ---")

    chunks = await asyncio.to_thread(documentProcessor.process_document, doc, new_content_hash)
    texts = [c.page_content for c in chunks]
    
    dense_vecs, sparse_vecs = await embed_service.get_combined_embeddings(texts)

    try:
        await asyncio.to_thread(qdrant_service.delete_chunks, page_id)
        await asyncio.to_thread(qdrant_service.upsert_chunks, chunks, dense_vecs, sparse_vecs)
        
        logger.info(f"--- [Worker] Successfully synchronized Page {page_id} ---")
    except Exception as e:
        logger.info(f"--- [Worker] Qdrant Error for Page {page_id}: {e} ---")

async def get_page_content(page_id: str):
    loader = ConfluenceLoader(
        url=str(CONFLUENCE_BASE_URL),
        username=EMAIL,
        api_key=API_TOKEN,
        page_ids=[page_id] 
    )
    
    try:
        documents = await asyncio.to_thread(loader.load)
        if documents:
            return documents[0] 
        return None
    except Exception as e:
        logger.info(f"--- [Worker] Confluence Load Error: {e} ---")
        return None