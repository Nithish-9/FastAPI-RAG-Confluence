from fastapi import FastAPI, Request
import uvicorn
from service import wb_confluence_service 

server = FastAPI()

@server.post("/webhook/confluence")
async def ingest_confluence_webhook(request: Request):
    data = await request.json()
    await wb_confluence_service.extract(data)
    return {"status":"ok"}

@server.get("/rag/retrieve")
def retrieve_rag_data():
    return {"data": []}

if __name__ == "__main__":
    uvicorn.run("app:server", port=9900, reload=True)