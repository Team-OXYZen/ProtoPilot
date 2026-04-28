import logging
from fastapi import FastAPI
from dotenv import load_dotenv
from api.routes.chat import router as chat_router
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

app = FastAPI(title="ProtoPilot API")
app.include_router(chat_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "ProtoPilot API is running"}

@app.get("/health")
def health():
    return {"ok": True}