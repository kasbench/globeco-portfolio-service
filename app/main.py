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
from prometheus_client import make_asgi_app
import logging
from app.config import settings
from app.logging_config import setup_logging, LoggingMiddleware, get_logger
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
from opentelemetry.metrics import set_meter_provider
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

logger.info(
    "Configuring OpenTelemetry metrics export",
    endpoint=otel_metrics_endpoint,
    export_interval_seconds=settings.otel_metrics_export_interval_seconds,
    export_timeout_seconds=settings.otel_metrics_export_timeout_seconds
)

# Create standard metric exporter
metric_exporter = OTLPMetricExporter(endpoint=otel_metrics_endpoint)

# Create metric reader with standard exporter
metric_reader = PeriodicExportingMetricReader(
    exporter=metric_exporter,
    export_interval_millis=settings.otel_metrics_export_interval_seconds * 1000,  # Convert to milliseconds
    export_timeout_millis=settings.otel_metrics_export_timeout_seconds * 1000     # Convert to milliseconds
)

meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[metric_reader]
)
set_meter_provider(meter_provider)

# Instrument HTTPX and logging globally
HTTPXClientInstrumentor().instrument()
LoggingInstrumentor().instrument(set_logging_format=True)

# Create FastAPI app
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

# Add structured logging middleware (before other middleware)
app.add_middleware(LoggingMiddleware, logger=logger)

# Add enhanced HTTP metrics middleware if enabled
if settings.enable_metrics:
    from app.monitoring import EnhancedHTTPMetricsMiddleware
    app.add_middleware(
        EnhancedHTTPMetricsMiddleware, 
        debug_logging=settings.metrics_debug_logging
    )
    logger.info("Enhanced HTTP metrics middleware enabled")
else:
    logger.info("Enhanced HTTP metrics middleware disabled")

# Log thread metrics configuration for debugging
logger.info(
    "Thread metrics configuration",
    enable_thread_metrics=settings.enable_thread_metrics,
    thread_metrics_update_interval=settings.thread_metrics_update_interval,
    thread_metrics_debug_logging=settings.thread_metrics_debug_logging
)

# Setup thread metrics if enabled
if settings.enable_thread_metrics:
    from app.monitoring import setup_thread_metrics
    result = setup_thread_metrics(
        enable_thread_metrics=settings.enable_thread_metrics,
        update_interval=settings.thread_metrics_update_interval,
        debug_logging=settings.thread_metrics_debug_logging
    )
    if result:
        logger.info("Thread metrics collection enabled successfully")
    else:
        logger.error("Thread metrics collection setup failed")
else:
    logger.info("Thread metrics collection disabled")

# Instrument FastAPI app
FastAPIInstrumentor().instrument_app(app)

# Add Prometheus /metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Add explicit route for /metrics (without trailing slash) with service_namespace label
@app.get("/metrics")
async def get_metrics():
    from fastapi.responses import Response
    from prometheus_client import generate_latest
    
    # Generate metrics and add service_namespace label
    metrics_output = generate_latest().decode('utf-8')
    
    # Add service_namespace label to all metrics
    lines = metrics_output.split('\n')
    modified_lines = []
    
    for line in lines:
        if line.startswith('#') or not line.strip():
            # Keep comments and empty lines as-is
            modified_lines.append(line)
        elif '{' in line:
            # Metric with existing labels - add service_namespace
            metric_name, rest = line.split('{', 1)
            labels, value = rest.split('}', 1)
            if labels:
                modified_line = f'{metric_name}{{service_namespace="{settings.service_namespace}",{labels}}}{value}'
            else:
                modified_line = f'{metric_name}{{service_namespace="{settings.service_namespace}"}}{value}'
            modified_lines.append(modified_line)
        elif ' ' in line:
            # Metric without labels - add service_namespace
            parts = line.split(' ', 1)
            if len(parts) == 2:
                metric_name, value = parts
                modified_line = f'{metric_name}{{service_namespace="{settings.service_namespace}"}} {value}'
                modified_lines.append(modified_line)
            else:
                modified_lines.append(line)
        else:
            modified_lines.append(line)
    
    modified_output = '\n'.join(modified_lines)
    
    return Response(
        content=modified_output,
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )

# Configure CORS to allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include both v1 and v2 API routers
app.include_router(api_v1.router)
app.include_router(api_v2.router)

@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    return {"message": "Hello World"}

@app.get("/health")
async def health():
    logger.info("Health check endpoint accessed")
    return {"status": "healthy", "service": "globeco-portfolio-service"} 