
import httpx
import base64
import os
from dotenv import load_dotenv

processed_pages = set()
load_dotenv()
CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL")
EMAIL = os.getenv("EMAIL")
API_TOKEN = os.getenv("API_TOKEN")

async def extract(confluence_data):
    page = confluence_data.get("page", {})
    page_id = page.get("id")
    version = page.get("version", 0)
    if page_id is None:
        print("Invalid page data")
        return
    
    if version == 1:
        event = "CREATE"
    elif version > 1 and confluence_data.get("updateTrigger") == "edit_page":
        event = "UPDATE"
    else:
        event = "UNKNOWN"

    print("Webhook Event Recieved: ",confluence_data)

    doc_key = (page_id, version)
    if doc_key in processed_pages:
        print(f"Skipping duplicate event for page {page_id} version {version}")
        return

    if event in ["CREATE", "UPDATE"]:
        content = await get_page_content(page_id)
        return content
    return None



async def get_page_content(page_id):
    auth_string = f"{EMAIL}:{API_TOKEN}"
    auth_bytes = auth_string.encode("ascii")
    auth_b64 = base64.b64encode(auth_bytes).decode("ascii")
    HEADERS = {
        "Authorization": f"Basic {auth_b64}",
        "Accept": "application/json"
    }
    url = f"{CONFLUENCE_BASE_URL}/wiki/rest/api/content/{page_id}?expand=body.storage"
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            print(data)
            content = data.get("body", {}).get("storage", {}).get("value", "")
            print(f"Page {page_id} content fetched successfully!")
            return content
        else:
            print(f"Failed to fetch page {page_id}: {resp.status_code}, {resp.text}")
            return None