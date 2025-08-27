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
    
    # Thread Metrics Configuration
    enable_thread_metrics: bool = Field(default=True, description="Enable thread worker metrics collection")
    thread_metrics_update_interval: float = Field(default=1.0, description="Thread metrics update interval in seconds")
    thread_metrics_debug_logging: bool = Field(default=False, description="Enable debug logging for thread metrics collection")
    
    # Service Namespace Label
    service_namespace: str = Field(default="globeco", description="Service namespace label for metrics")
    
    # OpenTelemetry Metrics Export Configuration
    otel_metrics_export_interval_seconds: int = Field(default=10, description="OpenTelemetry metrics export interval in seconds")
    otel_metrics_export_timeout_seconds: int = Field(default=5, description="OpenTelemetry metrics export timeout in seconds")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings() 