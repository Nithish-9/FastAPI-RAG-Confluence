from fastapi import FastAPI, Request
import uvicorn

server = FastAPI()

@server.post("/webhook/confluence")
async def ingest_confluence_webhook(request: Request):
    data = await request.json()
    print("Webhook Event Recieved: ",data)
    return {"status": "ingested"}

@server.get("/rag/retrieve")
def retrieve_rag_data():
    return {"data": []}

if __name__ == "__main__":
    uvicorn.run("app:server", port=9900, reload=True)