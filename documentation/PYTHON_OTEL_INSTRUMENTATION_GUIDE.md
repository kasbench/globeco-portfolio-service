# Python OpenTelemetry Instrumentation Guide for GlobeCo Microservices

This guide describes the **standard, consistent way** to instrument any Python microservice in the GlobeCo suite for metrics and distributed tracing. Follow these steps exactly to ensure all services are observable in the same way, making maintenance and debugging easier.

---

## 1. Add Required Dependencies

Add the following packages to your `pyproject.toml` (or install via pip):

```toml
[project]
dependencies = [
    # ... other dependencies ...
    "opentelemetry-api>=1.34.0",
    "opentelemetry-sdk>=1.34.0",
    "opentelemetry-instrumentation>=0.55b1",
    "opentelemetry-exporter-otlp>=1.34.0",
    "opentelemetry-instrumentation-fastapi>=0.55b1",
    "opentelemetry-instrumentation-httpx>=0.55b1",
    "opentelemetry-instrumentation-logging>=0.55b1",
    "prometheus_client>=0.22.0",
]
```

- `opentelemetry-api`, `opentelemetry-sdk`: Core OpenTelemetry APIs and SDK.
- `opentelemetry-exporter-otlp`: OTLP exporter for traces and metrics.
- `opentelemetry-instrumentation-fastapi`: Auto-instrument FastAPI apps.
- `opentelemetry-instrumentation-httpx`: Auto-instrument HTTPX client calls.
- `opentelemetry-instrumentation-logging`: Correlate logs with traces.
- `prometheus_client`: Exposes `/metrics` endpoint for Prometheus scraping.

---

## 2. Configure Telemetry in Your Application

Add the following code to your FastAPI app startup (see `app/main.py` for a working example):

```python
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

# Set resource attributes (customize service.name/version/namespace as needed)
resource = Resource.create({
    "service.name": "YOUR-SERVICE-NAME",
    # Optionally add version/namespace if desired
    # "service.version": "1.0.0",
    # "service.namespace": "globeco",
})

# Tracing setup (gRPC and HTTP exporters)
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer_provider = trace.get_tracer_provider()
tracer_provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporterGRPC(endpoint="otel-collector-collector.monitoring.svc.cluster.local:4317", insecure=True)
))
tracer_provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporterHTTP(endpoint="http://otel-collector-collector.monitoring.svc.cluster.local:4318/v1/traces")
))

# Metrics setup (gRPC and HTTP exporters)
from opentelemetry.metrics import set_meter_provider
meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[
        PeriodicExportingMetricReader(
            OTLPMetricExporterGRPC(endpoint="otel-collector-collector.monitoring.svc.cluster.local:4317", insecure=True)
        ),
        PeriodicExportingMetricReader(
            OTLPMetricExporterHTTP(endpoint="http://otel-collector-collector.monitoring.svc.cluster.local:4318/v1/metrics")
        )
    ]
)
set_meter_provider(meter_provider)

# Instrument FastAPI, HTTPX, and logging
FastAPIInstrumentor().instrument_app(app)
HTTPXClientInstrumentor().instrument()
LoggingInstrumentor().instrument(set_logging_format=True)

# Add Prometheus /metrics endpoint
app.mount("/metrics", make_asgi_app())
```

- **Endpoints:**
  - Traces: `otel-collector-collector.monitoring.svc.cluster.local:4317` (gRPC) and `http://otel-collector-collector.monitoring.svc.cluster.local:4318/v1/traces` (HTTP)
  - Metrics: `otel-collector-collector.monitoring.svc.cluster.local:4317` (gRPC) and `http://otel-collector-collector.monitoring.svc.cluster.local:4318/v1/metrics` (HTTP)
- **No authentication** is required (insecure mode).
- **Resource attributes**: Always set `service.name`. Optionally set `service.version` and `service.namespace` for more granularity.

---

## 3. What Gets Instrumented by Default?

- **Metrics:**
  - Python runtime, system, and FastAPI metrics (requests, latency, etc.)
  - Prometheus `/metrics` endpoint exposes metrics for scraping
  - Custom metrics can be added via OpenTelemetry or Prometheus if needed
- **Traces:**
  - All FastAPI HTTP requests are traced automatically
  - Outbound HTTPX requests are traced
  - Logs can be correlated with traces
  - Custom spans can be added in business logic if needed (see below)

---

## 4. How to View Telemetry Data

- **Metrics:**
  - Collected by the OpenTelemetry Collector and forwarded to Prometheus
  - View in Prometheus or Grafana dashboards
  - Scrape `/metrics` endpoint for Prometheus metrics
- **Traces:**
  - Collected by the OpenTelemetry Collector and forwarded to Jaeger
  - View in Jaeger UI (e.g., `http://jaeger.orchestration.svc.cluster.local:16686`)

---

## 5. How to Add Custom Spans or Metrics (Optional)

- **Custom Spans:**
  ```python
  from opentelemetry import trace
  tracer = trace.get_tracer(__name__)
  with tracer.start_as_current_span("my-custom-span"):
      # Your business logic here
  ```
- **Custom Metrics:**
  ```python
  from opentelemetry.metrics import get_meter
  meter = get_meter(__name__)
  counter = meter.create_counter("my_counter")
  counter.add(1, {"key": "value"})
  ```

For most services, the default HTTP tracing and metrics are sufficient.

---

## 6. Logging Telemetry Exports (Optional, for debugging)

You can enable info-level logging of every metrics export to the collector by setting the environment variable:

```bash
export OTEL_METRICS_LOGGING_ENABLED=true
```

This will log summary information about each export (metric count, resource attributes, exporter type, and export result). See `app/main.py` for the implementation.

---

## 7. Example: Consistent Configuration for a Service

**pyproject.toml**
```toml
[project]
dependencies = [
    # ... other dependencies ...
    "opentelemetry-api>=1.34.0",
    "opentelemetry-sdk>=1.34.0",
    "opentelemetry-instrumentation>=0.55b1",
    "opentelemetry-exporter-otlp>=1.34.0",
    "opentelemetry-instrumentation-fastapi>=0.55b1",
    "opentelemetry-instrumentation-httpx>=0.55b1",
    "opentelemetry-instrumentation-logging>=0.55b1",
    "prometheus_client>=0.22.0",
]
```

**main.py** (snippet)
```python
resource = Resource.create({
    "service.name": "globeco-portfolio-service"
})
# ... rest as above ...
```

---

## 8. Verification Checklist

- [x] **Dependencies** in `pyproject.toml` match this guide exactly
- [x] **Endpoints** for metrics and traces use the OTLP HTTP/gRPC endpoints: `otel-collector-collector.monitoring.svc.cluster.local:4317` and `http://otel-collector-collector.monitoring.svc.cluster.local:4318`
- [x] **Resource attributes** are set for service name (and optionally version/namespace)
- [x] **Prometheus /metrics endpoint** is exposed for scraping
- [x] **Sampling**: All traces are exported by default (no sampling config needed for full export)
- [x] **Logging**: Info-level logging of metrics export is enabled if `OTEL_METRICS_LOGGING_ENABLED=true`

---

## 9. References
- See `documentation/OTEL_CONFIGURATION_GUIDE.md` for OpenTelemetry Collector setup and troubleshooting.
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/)
- [Jaeger](https://www.jaegertracing.io/)
- [Prometheus](https://prometheus.io/)
- [OpenTelemetry Python SDK](https://opentelemetry.io/docs/instrumentation/python/)

---

**By following this guide, every Python microservice in the GlobeCo suite will be instrumented in a consistent, maintainable, and debuggable way.**
