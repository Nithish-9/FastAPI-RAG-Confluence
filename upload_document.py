import os
import requests
import logging
import sys 

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

API_URL = "http://localhost:9900/documentupload" 

def upload_document(source_dir):
    if not os.path.isdir(source_dir):
        logger.error(f"Error: '{source_dir}' is not a valid directory.")
        return

    files_processed = 0
    
    logger.info(f"Scanning directory: {os.path.abspath(source_dir)}")

    for filename in os.listdir(source_dir):
        file_path = os.path.join(source_dir, filename)
        
        if os.path.isdir(file_path):
            continue

        logger.info(f" Starting upload for: {filename}")

        try:
            with open(file_path, "rb") as f:
                files = {"file": (filename, f, "application/octet-stream")}
                
                response = requests.post(API_URL, files=files, timeout=60)
                
                if response.status_code == 200:
                    logger.info(f" Success! Server response: {response.json()}")
                    files_processed += 1
                else:
                    logger.error(f" Failed: {filename} | Status: {response.status_code} | Msg: {response.text}")
                    
        except requests.exceptions.ConnectionError:
            logger.error(" Connection Refused: Is the FastAPI server running?")
            return
        except Exception as e:
            logger.error(f" Error processing {filename}: {str(e)}")

    logger.info(f"--- Total files uploaded: {files_processed} ---")

if __name__ == "__main__":

    if len(sys.argv) > 1:
        target_dir = sys.argv[1]
    else:
        target_dir = "."
        logger.info("No path provided, defaulting to current directory (.)")

    upload_document(target_dir)