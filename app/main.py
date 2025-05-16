from fastapi import FastAPI
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from app.models import Portfolio
from app.api import router as api_router

async def lifespan(app: FastAPI):
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(
        database=client[settings.mongodb_db],
        document_models=[Portfolio],
    )
    yield

app = FastAPI(lifespan=lifespan)

app.include_router(api_router)

@app.get("/")
async def root():
    return {"message": "Hello World"} 