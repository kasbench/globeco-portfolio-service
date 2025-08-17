# Enhanced Thread Metrics

## Background
- This microservice runs in Kubernetes
- This microservice feeds the OpenTelemetry Collector with is scraped by Prometheus.
- This service is already instrumented for standard and enhanced (custom) metrics.  Build on the existing scaffolding.  Do not start from scratch.  Please be careful not to break existing metrics or pipelines.  The scope of this project is limited to adding new custom metrics using the existing scaffolding.
- This microservice is in a suite of microservices called the GlobeCo suite, which is used for benchmarking.  Metrics are extremely important.  This is not a production application.
- Microservices are written in Java, Go, Python, and TypeScript.  Consistency between services is a key goal.
- The purpose of this enhancement is to capture the following metrics:
  - `http.workers.active`
  - `http.workers.total`
  - `http.workers.max_configured`
  - `http_requests_queued`
- These metrics will be used to better understand failures where this service can no longer process incoming requests.
- Please examine the Dockerfile to see how this application is packaged for deployment.  It is important to understand how the application is deployed and how the Dockerfile is used to build the image.
- Kubernetes manifests are in the /k8s directory.  Please examine these manifests to understand how the application is deployed and how the Kubernetes resources are configured.
- Please develop a streamlined plan that front-loads production of the metrics so that I can test in Kubernetes.  Once I see the metrics, I may want additional changes.  I don't want to go too deep before vetting that these are the metrics we need.



## New metrics to be produced


### `http.workers.active`
**Definition**: The number of threads currently executing requests or performing work. These are threads that have been assigned a task from the queue and are actively processing it.

**Implementation**: Count threads with status "RUNNING" or "BUSY" - threads that have accepted a connection/request and are currently handling it (parsing HTTP, executing business logic, generating response, etc.).

### `http.workers.total` 
**Definition**: The total number of threads currently alive in the thread pool, regardless of their state (idle, busy, or waiting).

**Implementation**: Count all threads in the pool including:
- Active/busy threads processing requests
- Idle threads waiting for work
- Threads that may be temporarily blocked or waiting

This represents the actual instantaneous thread pool size.

### `http.workers.max_configured`
**Definition**: The maximum number of threads that can be created in the thread pool as configured. This is a static configuration value.

**Implementation**: Return the configured maximum thread pool size limit. This value typically doesn't change during runtime unless the application is reconfigured. It represents the upper bound on `tomcat.threads.current`.

### `http_requests_queued`
**Definition**: The number of pending requests/tasks waiting in the queue to be assigned to an available thread.

**Implementation**: Count queued work items that have been accepted by the server but are waiting for a thread to become available to process them. When all threads are busy and new requests arrive, they get queued here.

## Documentation

Keep track of the steps taken to implement this enhancement in a new document.  Update the document after each step.  This document will be extremely useful when we apply this change to other microservices in this suite.