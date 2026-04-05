from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

class DocumentProcessor:
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

    def process_document(self, doc,content_hash):
        
        sections = self.header_splitter.split_text(doc.page_content)

        final_chunks = []
        global_chunk_count = 0 

        for section in sections:
            sub_chunks = self.text_splitter.split_documents([section])
            
            for chunk in sub_chunks:
                chunk.metadata.update({
                    "page_id": str(doc.metadata.get("id")),
                    "space_key": doc.metadata.get("source").split("/")[-4],
                    "url": doc.metadata.get("source"),
                    "last_modified": doc.metadata.get("when"),
                    "content_hash": content_hash,
                    "chunk_index": global_chunk_count
                })
                
                final_chunks.append(chunk)
                global_chunk_count += 1
                
        return final_chunks
    
documentProcessor = DocumentProcessor()