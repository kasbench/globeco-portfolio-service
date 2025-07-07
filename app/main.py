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

# OpenTelemetry resource
resource = Resource.create({
    "service.name": "globeco-portfolio-service"
})

# Tracing setup (gRPC and HTTP exporters)
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer_provider = trace.get_tracer_provider()
tracer_provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporterGRPC(endpoint="otel-collector.monitor.svc.cluster.local:4317", insecure=True)
))
tracer_provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporterHTTP(endpoint="http://otel-collector.monitor.svc.cluster.local:4318/v1/traces")
))

# Metrics setup (gRPC and HTTP exporters)
from opentelemetry.metrics import set_meter_provider
meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[
        PeriodicExportingMetricReader(
            OTLPMetricExporterGRPC(endpoint="otel-collector.monitor.svc.cluster.local:4317", insecure=True)
        ),
        PeriodicExportingMetricReader(
            OTLPMetricExporterHTTP(endpoint="http://otel-collector.monitor.svc.cluster.local:4318/v1/metrics")
        )
    ]
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

# Instrument FastAPI app
FastAPIInstrumentor().instrument_app(app)

# Add Prometheus /metrics endpoint
app.mount("/metrics", make_asgi_app())

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
    return {"message": "Hello World"} 