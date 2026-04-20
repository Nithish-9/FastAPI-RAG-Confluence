import logging
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_core.documents import Document

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

class DocumentChunker:
    def __init__(self):
        self.header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "Header 1"),
                ("##", "Header 2"),
                ("###", "Header 3"),
            ]
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, 
            chunk_overlap=100,
            add_start_index=True
        )

    def process_document(self, doc: Document, content_hash: str):
        if not doc.page_content or not doc.page_content.strip():
            logger.warning(f"--- [Chunker] Document {doc.metadata.get('page_id')} is empty. ---")
            return []

        sections = self.header_splitter.split_text(doc.page_content)

        final_chunks = []
        global_chunk_count = 0 

        for section in sections:
            sub_chunks = self.text_splitter.split_documents([section])
            
            for chunk in sub_chunks:
                source_type = doc.metadata.get("source_type", "FILE")
                source_url = doc.metadata.get("source", "")
                
                space_key = "N/A"
                if source_type == "CONFLUENCE" and source_url:
                    try:
                        if "/display/" in source_url:
                            space_key = source_url.split("/display/")[1].split("/")[0]
                        elif "/spaces/" in source_url:
                            space_key = source_url.split("/spaces/")[1].split("/")[0]
                    except Exception:
                        space_key = "UNKNOWN"

                new_metadata = {
                    "page_id": doc.metadata.get("page_id"),
                    "source_type": source_type,
                    "filename": doc.metadata.get("filename", ""),
                    "space_key": space_key,
                    "url": source_url,
                    "last_modified": doc.metadata.get("when", "N/A"),
                    "content_hash": content_hash,
                    "chunk_index": global_chunk_count,
                }
                
                new_metadata.update(chunk.metadata)
                
                chunk.metadata = new_metadata
                final_chunks.append(chunk)
                global_chunk_count += 1
                
        logger.info(f"--- [Chunker] Generated {len(final_chunks)} chunks for ID: {doc.metadata.get('page_id')} ---")
        return final_chunks

documentChunker = DocumentChunker()