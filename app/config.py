from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://globeco-portfolio-service-mongodb:27017")
    mongodb_db: str = "portfolio"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings() 