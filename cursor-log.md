Instructions:
- Log every request that you receive.
- Log every action that you take in an enumerated list.
- Follow the format provided below.  
- Add each new entry at the end.  NEVER delete or replace an entry.  Only add entries at the end.
- Make sure there are two blank lines between each section.
- Please remember these instructions.


Prompt: Sample prompt.  Do not delete.  Add new prompts after this one.
Actions:
1. Action 1
2. Action 2
3. Action 3


---

Prompt: Configure the project to connect to the MongoDB database on localhost at port 27017 and database `securities`. Please add an entry with this prompt and your actions in the cursor-log.md file following the instructions in the file.
Actions:
1. Reviewed the project structure and requirements documentation to confirm the correct MongoDB connection details.
2. Inspected app/config.py to check the current database configuration.
3. Updated the default database name in app/config.py to 'securities' as specified in the requirements, and added a clarifying comment.


Prompt: Please implement the APIs for security type using the requirements provided in @requirements.md. Please add an entry with this prompt and your actions in the cursor-log.md file following the instructions in the file.
Actions:
1. Reviewed requirements.md for securityType API and data model specifications.
2. Created app/models/security_type.py with the Beanie document for SecurityType, including all required fields and constraints.
3. Created app/schemas/security_type.py with Pydantic schemas for input and output DTOs.
4. Implemented app/services/security_type_service.py for CRUD operations and optimistic concurrency control.
5. Implemented app/api/routes.py with FastAPI endpoints for all required securityType operations, using the correct URI patterns and DTOs.
6. Updated app/main.py to initialize Beanie with the SecurityType model and include the API router.


Prompt: Please generate the Pytest tests for all the code you created in the previous step. Please add an entry with this prompt and your actions in the cursor-log.md file following the instructions in the file.
Actions:
1. Reviewed the implemented securityType API endpoints and requirements.
2. Created tests/test_security_type.py with Pytest async tests for all CRUD operations, optimistic concurrency, and error cases.
3. Used FastAPI's AsyncClient for endpoint testing and isolated the test database for clean test runs.


Prompt: Please update the README.md file with an introduction and full documentation on the security type data model and API. Please add an entry with this prompt and your actions in the cursor-log.md file following the instructions in the file.
Actions:
1. Reviewed the requirements and current README.md content.
2. Replaced the README.md with a comprehensive introduction, technology stack, data model, API documentation, example usage, and instructions for running and testing the service.


Prompt: Please create an OpenAPI schema `openapi.yaml' in the project root.  Please include the full specification for the security type API.  Please add an entry with this prompt and your actions in the cursor-log.md file following the instructions in the file.
Actions:
1. Reviewed the requirements and API documentation for the security type endpoints.
2. Created openapi.yaml in the project root with a complete OpenAPI 3.0.3 specification for all security type endpoints, request/response schemas, and error responses.


Prompt: Please update the openapi schema `openapi.yaml` with the spec for security.  Please add an entry with this prompt and your actions in the cursor-log.md file following the instructions in the file.
Actions:
1. Reviewed the requirements and current openapi.yaml for the securityType API.
2. Added all security endpoints (/securities, /security/{securityId}) to the OpenAPI spec, including GET, POST, PUT, and DELETE.
3. Added SecurityIn, SecurityOut, and SecurityTypeNested schemas to components.
4. Documented all request/response payloads, error responses, and optimistic concurrency for the security API.


Prompt: Please implement the APIs for security using the requirements provided in @requirements.md.  Use the code for security type as an example.  Strive for consistency.  Please add an entry with this prompt and your actions in the cursor-log.md file following the instructions in the file.
Actions:
1. Reviewed requirements.md and security type code for consistency.
2. Created app/models/security.py with the Beanie document for Security, including all required fields and constraints.
3. Created app/schemas/security.py with Pydantic schemas for input and output DTOs, including nested securityType for GET responses.
4. Implemented app/services/security_service.py for CRUD operations and optimistic concurrency control, including joins with SecurityType.
5. Updated app/api/routes.py to add all required security endpoints, following the same style as securityType.
6. Updated app/main.py to initialize Beanie with both Security and SecurityType models.


Prompt: Please add documentation for the security data model and API to readme.md.  Please add an entry with this prompt and your actions in the cursor-log.md file following the instructions in the file.
Actions:
1. Reviewed the README.md and requirements for the security data model and API.
2. Added a section for the security data model, including a table of fields and constraints.
3. Documented the security API endpoints, DTOs, and optimistic concurrency behavior.
4. Added example usage for all CRUD operations on the security API, following the style of the security type documentation.


Prompt: Please create a Dockerfile for this application.  Please add an entry with this prompt and your actions in the cursor-log.md file following the instructions in the file.
Actions:
1. Created a Dockerfile using the official Python 3.13-slim image.
2. Installed system dependencies and uv (universal package manager).
3. Copied the project files and installed Python dependencies with uv.
4. Exposed port 8000 and set the default command to run the FastAPI app with Uvicorn.
5. Added maintainer and application labels as required.


Prompt: I will be deploying this service to Kubernetes.  We need to implement liveness, readiness, and startup health checks.  What do you recommend for each?
Actions:
1. Added a new app/api/health.py router with /health/liveness, /health/readiness, and /health/startup   endpoints:
   - Liveness: Always returns 200 OK if the process is running.
   - Readiness/Startup: Check MongoDB connectivity and return 200 if reachable, 503 otherwise.
2. Included the health check router in your FastAPI app, so these endpoints are now available.


Prompt: Please create all the files necessary to deploy to this application as a service to Kubernetes.  Please include the liveness, readiness, and startup probes you just created.  The deployment should start with one instance of the service and should scale up to a maximum of 100 instances.  It should have up 100 millicores and 200 MiB of memory.  The name of the service is `globeco-security-service` in the `globeco` namespace.  You do not need to create the namespace. Please add an entry with this prompt and your actions in the cursor-log.md file following the instructions in the file.
Actions:
1. Created kubernetes/deployment.yaml with a Deployment for globeco-security-service, including resource requests/limits, liveness, readiness, and startup probes, and an HPA for autoscaling from 1 to 100 pods.
2. Created kubernetes/service.yaml with a ClusterIP Service exposing port 8000 for the deployment.


Prompt: Please document the health checks (liveness, readiness/startup) in the README.md file and the openapi.yaml OpenAPI spec.  Please add an entry with this prompt and your actions in the cursor-log.md file following the instructions in the file.
Actions:
1. Added a Health Checks section to README.md, documenting the liveness, readiness, and startup endpoints, their purpose, and example Kubernetes probe configuration.
2. Updated openapi.yaml to include /health/liveness, /health/readiness, and /health/startup endpoints, with response schemas and descriptions.


