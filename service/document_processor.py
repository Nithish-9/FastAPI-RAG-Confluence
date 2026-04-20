import os
import asyncio
import logging
from langchain_community.document_loaders import (
    ConfluenceLoader,
    PyPDFLoader, 
    Docx2txtLoader, 
    TextLoader, 
    UnstructuredFileLoader
)
from service.document_ingestion import ingestion_service 
from service.qdrant_service import qdrant_service
import hashlib
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

logger = logging.getLogger(__name__)

CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL")
EMAIL = os.getenv("EMAIL")
API_TOKEN = os.getenv("API_TOKEN")

async def extract(document_data: dict, document_type: str) -> None:
    if document_type == 'CONFLUENCE':
        page = document_data.get("page", {})
        page_id = str(page.get("id"))
    
        if not page_id or page_id == "None":
            logger.info("--- [Loader] Invalid Confluence page data ---")
            return
        
        await process_confluence_page(page_id)

    else:
        file_path = document_data.get("file_path")
        file_name = document_data.get("filename")
        if not file_path or not os.path.exists(file_path):
            logger.error(f"--- [Loader] File not found: {file_path} ---")
            return

        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == ".pdf":
                await process_documents(PyPDFLoader(file_path), file_name, ext)
            elif ext in [".docx", ".doc"]:
                await process_documents(Docx2txtLoader(file_path), file_name, ext)
            elif ext == ".txt":
                await process_documents(TextLoader(file_path), file_name, ext)
            else:
                await process_documents(UnstructuredFileLoader(file_path), file_name, ext)
        except Exception as e:
            logger.error(f"--- [Loader] File Loading Error: {repr(e)} ---")

async def process_confluence_page(page_id: str):
    loader = ConfluenceLoader(
        url=str(CONFLUENCE_BASE_URL),
        username=EMAIL,
        api_key=API_TOKEN,
        page_ids=[page_id] 
    )
    try:
        documents = await asyncio.to_thread(loader.load)
        if documents:
            combined_content = "\n".join([d.page_content for d in documents])
            master_doc = documents[0]
            master_doc.page_content = combined_content
            
            new_content_hash = hashlib.sha256(combined_content.encode()).hexdigest()
            master_doc.metadata.update({
                "source_type": "CONFLUENCE",
                "page_id": page_id,
                "filename": "",
                "content_hash": new_content_hash
            })

            if not qdrant_service.check_confluence_changed(page_id, new_content_hash):
                logger.info(f"--- [Ingestor] {page_id} unchanged. Skipping. ---")
                return

            await ingestion_service.ingest(master_doc, page_id)
    except Exception as e:
        logger.error(f"--- [Loader] Confluence Load Error: {repr(e)} ---")

async def process_documents(loader, file_name, file_extension):
    try:
        documents = await asyncio.to_thread(loader.load)
        if documents:
            combined_content = "\n".join([d.page_content for d in documents])
            master_doc = documents[0]
            master_doc.page_content = combined_content
            
            page_id = hashlib.sha256(combined_content.encode()).hexdigest()
            
            master_doc.metadata.update({
                "source_type": file_extension.replace(".", "").upper(),
                "page_id": page_id,
                "filename": file_name,
                "content_hash": page_id 
            })

            if not qdrant_service.check_doc_changed(page_id):
                logger.info(f"--- [Ingestor] {file_name} content already exists. Skipping. ---")
                return

            await ingestion_service.ingest(master_doc, page_id)
    except Exception as e:
        logger.error(f"--- [Loader] {file_extension} Load Error: {repr(e)} ---")