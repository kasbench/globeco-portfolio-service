from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as OTLPSpanExporterGRPC
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as OTLPSpanExporterHTTP
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter as OTLPMetricExporterGRPC
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter as OTLPMetricExporterHTTP
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
# Prometheus client removed - using OpenTelemetry only
import logging
from app.config import settings
from app.logging_config import setup_logging, get_logger
import os

# Setup structured JSON logging
logger = setup_logging(log_level=settings.log_level)

# OpenTelemetry resource with k8s-friendly attributes
resource = Resource.create({
    "service.name": "globeco-portfolio-service",
    "service.version": "1.0.0",
    "service.namespace": "globeco",
    "k8s.pod.name": os.getenv("MY_POD_NAME", os.getenv("HOSTNAME", "unknown")),
    "k8s.pod.ip": os.getenv("MY_POD_IP", "unknown"),
    "k8s.namespace.name": "globeco",
    "k8s.deployment.name": "globeco-portfolio-service",
    "k8s.node.name": os.getenv("MY_NODE_NAME", "unknown")
})

# Get OpenTelemetry endpoints from environment variables with fallbacks
otel_grpc_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "otel-collector.monitor.svc.cluster.local:4317")
otel_http_endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://otel-collector.monitor.svc.cluster.local:4318/v1/traces")

# Tracing setup (gRPC and HTTP exporters)
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer_provider = trace.get_tracer_provider()
tracer_provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporterGRPC(endpoint=otel_grpc_endpoint, insecure=True)
))
tracer_provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporterHTTP(endpoint=otel_http_endpoint)
))

# Get metrics endpoint from environment variables with fallback
otel_metrics_endpoint = os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "http://otel-collector.monitor.svc.cluster.local:4318/v1/metrics")

# Metrics setup - use standard exporter without custom logging
from opentelemetry import metrics
from opentelemetry.metrics import set_meter_provider
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

logger.info(
    "Configuring OpenTelemetry metrics export",
    endpoint=otel_metrics_endpoint,
    export_interval_seconds=settings.otel_metrics_export_interval_seconds,
    export_timeout_seconds=settings.otel_metrics_export_timeout_seconds
)

# Create standard metric exporter with additional logging
try:
    metric_exporter = OTLPMetricExporter(endpoint=otel_metrics_endpoint)
    logger.info(
        "OpenTelemetry metric exporter created successfully",
        endpoint=otel_metrics_endpoint,
        exporter_type="OTLPMetricExporter"
    )
except Exception as e:
    logger.error(
        "Failed to create OpenTelemetry metric exporter",
        endpoint=otel_metrics_endpoint,
        error=str(e),
        error_type=type(e).__name__,
        exc_info=True
    )
    raise

# Create metric reader with standard exporter
try:
    metric_reader = PeriodicExportingMetricReader(
        exporter=metric_exporter,
        export_interval_millis=settings.otel_metrics_export_interval_seconds * 1000,  # Convert to milliseconds
        export_timeout_millis=settings.otel_metrics_export_timeout_seconds * 1000     # Convert to milliseconds
    )
    logger.info(
        "OpenTelemetry metric reader created successfully",
        export_interval_millis=settings.otel_metrics_export_interval_seconds * 1000,
        export_timeout_millis=settings.otel_metrics_export_timeout_seconds * 1000,
        reader_type="PeriodicExportingMetricReader"
    )
except Exception as e:
    logger.error(
        "Failed to create OpenTelemetry metric reader",
        export_interval_seconds=settings.otel_metrics_export_interval_seconds,
        export_timeout_seconds=settings.otel_metrics_export_timeout_seconds,
        error=str(e),
        error_type=type(e).__name__,
        exc_info=True
    )
    raise

meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[metric_reader]
)
set_meter_provider(meter_provider)

# Initialize OpenTelemetry metrics after meter provider is set up
from app.monitoring import initialize_otel_metrics

# Log the current meter provider before initializing custom metrics
current_meter_provider = metrics.get_meter_provider()
logger.info(
    "Current meter provider before custom metrics initialization",
    meter_provider_type=type(current_meter_provider).__name__,
    meter_provider_id=id(current_meter_provider),
    is_same_as_configured=current_meter_provider is meter_provider
)

otel_metrics_initialized = initialize_otel_metrics()
logger.info(
    "OpenTelemetry metrics initialization completed",
    success=otel_metrics_initialized,
    meter_provider_set=True,
    configured_meter_provider_id=id(meter_provider),
    current_meter_provider_id=id(current_meter_provider)
)

# Instrument HTTPX and logging globally
HTTPXClientInstrumentor().instrument()
LoggingInstrumentor().instrument(set_logging_format=True)

# Create FastAPI app
from fastapi import FastAPI
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from app.models import Portfolio
from app import api_v1, api_v2
from app.database import create_indexes
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(
        database=client[settings.mongodb_db],
        document_models=[Portfolio],
    )
    # Create database indexes for optimal search performance
    await create_indexes()
    yield

app = FastAPI(lifespan=lifespan)

# Initialize environment-based configuration and middleware factory
from app.environment_config import initialize_config_manager, initialize_feature_flags
from app.middleware_factory import create_middleware_stack

# Initialize configuration management
config_manager = initialize_config_manager()
feature_flags = initialize_feature_flags(config_manager)

logger.info(
    "Environment configuration initialized",
    environment=config_manager.current_environment,
    config_summary=config_manager.get_config_summary(),
    observability_flags=feature_flags.get_observability_summary()
)

# Create environment-appropriate middleware stack
create_middleware_stack(app, config_manager)

# Instrument FastAPI app
FastAPIInstrumentor().instrument_app(app)

# Include both v1 and v2 API routers
app.include_router(api_v1.router)
app.include_router(api_v2.router)

@app.get("/")
async def root():
    logger.debug("Root endpoint accessed")
    return {"message": "Hello World"}

@app.get("/health")
async def health():
    logger.debug("Health check endpoint accessed")
    return {"status": "healthy", "service": "globeco-portfolio-service"} 