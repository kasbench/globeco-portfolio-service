from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os

class Settings(BaseSettings):
    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://globeco-portfolio-service-mongodb:27017")
    mongodb_db: str = "portfolio"
    otel_metrics_logging_enabled: bool = bool(os.getenv("OTEL_METRICS_LOGGING_ENABLED", "False").lower() in ("1", "true", "yes"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Enhanced HTTP Metrics Configuration
    enable_metrics: bool = Field(default=True, description="Enable enhanced HTTP metrics collection")
    metrics_debug_logging: bool = Field(default=False, description="Enable debug logging for metrics collection")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings() 