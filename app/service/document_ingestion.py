import asyncio
import logging
from langchain_core.documents import Document 
from service.document_chunking import documentChunker
from service.generate_embedding import embed_service
from service.enterprise_qdrant_service import enterprise_qdrant_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

logger = logging.getLogger(__name__)

class DocumentIngestionService:
    async def ingest(self, master_doc: Document, page_id: str) -> None:

        current_hash = master_doc.metadata.get("content_hash")
        
        if not current_hash:
            raise ValueError(f"Incomplete metadata: Missing content_hash for {page_id}")

        logger.info(f"--- [Ingestor] Beginning Ingestion for: {page_id} ---")

        try:
            chunks = await asyncio.to_thread(
                documentChunker.process_document, 
                master_doc, 
                current_hash
            )
            
            if not chunks:
                logger.warning(f"--- [Ingestor] No chunks generated for {page_id}. Aborting. ---")
                return


            logger.info(f"--- [Ingestor] Generating embeddings for {len(chunks)} chunks ---")
            texts = [c.page_content for c in chunks]
            dense_vecs, sparse_vecs = await embed_service.get_combined_embeddings(texts)


            try:
                logger.info(f"--- [Ingestor] Removing stale data for {page_id} ---")
                await asyncio.to_thread(enterprise_qdrant_service.delete_chunks, page_id)
                
                logger.info(f"--- [Ingestor] Upserting {len(chunks)} new chunks to Qdrant ---")
                await asyncio.to_thread(
                    enterprise_qdrant_service.upsert_chunks, 
                    chunks, 
                    dense_vecs, 
                    sparse_vecs
                )
            except Exception as db_error:
                logger.critical(
                    f"--- [Ingestor] DATABASE INCONSISTENCY: {page_id} was deleted but "
                    f"upsert failed. Error: {repr(db_error)} ---"
                )
                raise db_error
            
            logger.info(f"--- [Ingestor] Successfully synchronized {page_id} to Qdrant ---")

        except Exception as e:
            logger.error(f"--- [Ingestor] Ingestion pipeline failed for {page_id}: {repr(e)} ---")
            raise e


ingestion_service = DocumentIngestionService()