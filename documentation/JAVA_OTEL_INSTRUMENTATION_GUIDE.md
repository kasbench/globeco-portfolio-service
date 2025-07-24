# Java OpenTelemetry Instrumentation Guide for GlobeCo Microservices

This guide describes the **standard, consistent way** to instrument any Spring Java microservice in the GlobeCo suite for metrics and distributed tracing. Follow these steps exactly to ensure all services are observable in the same way, making maintenance and debugging easier.

---

## 1. Add Required Dependencies

Edit your `build.gradle` and add the following dependencies to the `dependencies` block:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
implementation 'io.micrometer:micrometer-registry-otlp'
implementation 'io.micrometer:micrometer-tracing-bridge-otel'
implementation 'io.opentelemetry:opentelemetry-exporter-otlp:1.38.0'
```

- `spring-boot-starter-actuator`: Enables metrics and health endpoints.
- `micrometer-registry-otlp`: Exports metrics to OpenTelemetry Collector via OTLP.
- `micrometer-tracing-bridge-otel`: Bridges Spring tracing to OpenTelemetry.
- `opentelemetry-exporter-otlp`: Required for OTLP trace export.

---

## 2. Configure Telemetry in `application.properties`

Add the following properties to your `src/main/resources/application.properties` file. Replace only the service name/version/namespace as appropriate for your service; all other settings should remain identical for consistency.

### Metrics Export (OTLP)
```properties
# Micrometer OpenTelemetry (OTLP) Metrics Export
management.otlp.metrics.export.url=http://otel-collector-collector.monitoring.svc.cluster.local:4318/v1/metrics
management.otlp.metrics.export.step=1m
management.otlp.metrics.export.resource-attributes.service.name=YOUR-SERVICE-NAME
management.otlp.metrics.export.resource-attributes.service.version=1.0.0
management.otlp.metrics.export.resource-attributes.service.namespace=globeco
management.otlp.metrics.export.resource-attributes.service.instance.version=1.0.0
management.otlp.metrics.export.resource-attributes.service.instance.namespace=globeco
```

### Tracing Export (OTLP)
```properties
# OpenTelemetry Tracing Export (OTLP)
management.otlp.tracing.endpoint=http://otel-collector-collector.monitoring.svc.cluster.local:4318/v1/traces
management.otlp.tracing.resource-attributes.service.name=YOUR-SERVICE-NAME
management.otlp.tracing.resource-attributes.service.version=1.0.0
management.otlp.tracing.resource-attributes.service.namespace=globeco
management.otlp.tracing.resource-attributes.service.instance.namespace=globeco
management.otlp.tracing.sampling.probability=1.0
```

### Logging (Optional, for debugging export issues)
```properties
logging.level.io.micrometer.registry.otlp=DEBUG
logging.level.io.opentelemetry.exporter.otlp=DEBUG
```

---

## 3. What Gets Instrumented by Default?

- **Metrics:**
  - JVM, system, and Spring Boot metrics (memory, CPU, HTTP requests, cache, etc.)
  - Custom metrics can be added via Micrometer if needed.
- **Traces:**
  - All HTTP requests (controllers/endpoints) are traced automatically.
  - Spans are created for incoming requests and propagated downstream.
  - Custom spans can be added in business logic if needed (see below).

---

## 4. How to View Telemetry Data

- **Metrics:**
  - Collected by the OpenTelemetry Collector and forwarded to Prometheus.
  - View in Prometheus or Grafana dashboards.
- **Traces:**
  - Collected by the OpenTelemetry Collector and forwarded to Jaeger.
  - View in Jaeger UI (e.g., `http://jaeger.orchestration.svc.cluster.local:16686`).

---

## 5. How to Add Custom Spans (Optional)

If you want to trace specific business logic, inject and use the `io.micrometer.observation.ObservationRegistry` or OpenTelemetry's `Tracer` directly. For most services, the default HTTP tracing is sufficient.

---

## 6. Example: Consistent Configuration for a Service

**build.gradle**
```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
implementation 'io.micrometer:micrometer-registry-otlp'
implementation 'io.micrometer:micrometer-tracing-bridge-otel'
implementation 'io.opentelemetry:opentelemetry-exporter-otlp:1.38.0'
```

**application.properties**
```properties
management.otlp.metrics.export.url=http://otel-collector-collector.monitoring.svc.cluster.local:4318/v1/metrics
management.otlp.metrics.export.step=1m
management.otlp.metrics.export.resource-attributes.service.name=globeco-pricing-service
management.otlp.metrics.export.resource-attributes.service.version=1.0.0
management.otlp.metrics.export.resource-attributes.service.namespace=globeco
management.otlp.metrics.export.resource-attributes.service.instance.version=1.0.0
management.otlp.metrics.export.resource-attributes.service.instance.namespace=globeco

management.otlp.tracing.endpoint=http://otel-collector-collector.monitoring.svc.cluster.local:4318/v1/traces
management.otlp.tracing.resource-attributes.service.name=globeco-pricing-service
management.otlp.tracing.resource-attributes.service.version=1.0.0
management.otlp.tracing.resource-attributes.service.namespace=globeco
management.otlp.tracing.resource-attributes.service.instance.namespace=globeco
management.otlp.tracing.sampling.probability=1.0

logging.level.io.micrometer.registry.otlp=DEBUG
logging.level.io.opentelemetry.exporter.otlp=DEBUG
```

---

## 7. Verification Checklist

- [x] **Dependencies** in `build.gradle` match this guide exactly.
- [x] **Properties** in `application.properties` match this guide exactly (except for service name/version/namespace as appropriate).
- [x] **Endpoints** for metrics and traces use the OTLP HTTP endpoint: `http://otel-collector-collector.monitoring.svc.cluster.local:4318`.
- [x] **Resource attributes** are set for service name, version, and namespace for both metrics and traces.
- [x] **Sampling probability** for traces is set to `1.0` (all traces exported).

---

## 8. References
- See `documentation/OTEL_CONFIGURATION_GUIDE.md` for OpenTelemetry Collector setup and troubleshooting.
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/)
- [Jaeger](https://www.jaegertracing.io/)
- [Prometheus](https://prometheus.io/)
- [Micrometer](https://micrometer.io/)

---

**By following this guide, every Spring Java microservice in the GlobeCo suite will be instrumented in a consistent, maintainable, and debuggable way.**
