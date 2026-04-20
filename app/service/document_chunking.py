import logging
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_core.documents import Document

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
            chunk_overlap=100
        )

    def process_document(self, doc: Document, content_hash: str):

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
                        url_parts = source_url.split("/")
                        if len(url_parts) >= 4:
                            space_key = url_parts[-4]
                    except Exception:
                        space_key = "UNKNOWN"

                chunk.metadata.update({
                    "page_id": doc.metadata.get("page_id"),
                    "source_type": source_type,
                    "filename": doc.metadata.get("filename", ""),
                    "space_key": space_key,
                    "url": source_url,
                    "last_modified": doc.metadata.get("when", "N/A"),
                    "content_hash": content_hash,
                    "chunk_index": global_chunk_count
                })
                
                final_chunks.append(chunk)
                global_chunk_count += 1
                
        logger.info(f"--- [Chunker] Generated {len(final_chunks)} chunks for ID: {doc.metadata.get('page_id')} ---")
        return final_chunks
    

documentChunker = DocumentChunker()