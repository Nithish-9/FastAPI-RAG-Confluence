import os
import requests
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

API_URL = "http://localhost:9900/documentupload" 
SOURCE_DIR = "." 

def upload_document():
    if not os.path.exists(SOURCE_DIR):
        logger.error(f"Directory '{SOURCE_DIR}' not found. Please create it and add files.")
        return

    files_processed = 0
    
    for filename in os.listdir(SOURCE_DIR):
        file_path = os.path.join(SOURCE_DIR, filename)
        
        if os.path.isdir(file_path):
            continue

        logger.info(f" Starting upload for: {filename}")

        try:
            with open(file_path, "rb") as f:
                files = {"file": (filename, f, "application/octet-stream")}
                
                response = requests.post(API_URL, files=files, timeout=60)
                
                if response.status_code == 200:
                    logger.info(f" Success! Server : {response.json()}")
                    files_processed += 1
                else:
                    logger.error(f" Failed: {filename} | Status: {response.status_code} | Msg: {response.text}")
                    
        except requests.exceptions.ConnectionError:
            logger.error(" Connection Refused ")
            return
        except Exception as e:
            logger.error(f" Error processing {filename}: {str(e)}")

    logger.info(f"--- Total files uploaded: {files_processed} ---")

if __name__ == "__main__":
    upload_document()