# System Architecture

AI-LaTeX Diagram Generator is a containerized Flask application that converts natural-language diagram requests into LaTeX TikZ, compiles the result into PDF, and renders PNG previews for the frontend.

## System Architecture

```mermaid
flowchart TD
    User[User Browser] --> Frontend[Static Frontend]
    Frontend --> Proxy[Nginx Reverse Proxy]
    Proxy --> API[Flask API on Gunicorn]
    API --> Validate[Request Validation]
    Validate --> Granite[IBM Granite on watsonx.ai]
    Granite --> Clean[TikZ Cleanup and Auto-Repair]
    Clean --> TikzValidate[TikZ Validation]
    TikzValidate --> Latex[LaTeX Compiler]
    Latex --> PDF[PDF Artifact]
    Latex --> PNG[PNG Preview]
    API --> Files[Generated Artifact Routes]
    Files --> Frontend
```

## Docker Deployment

```mermaid
flowchart TD
    Compose[Docker Compose] --> Backend[backend container]
    Compose --> Nginx[nginx container]
    Nginx --> StaticFiles[frontend static files]
    Nginx --> Backend
    Backend --> Gunicorn[Gunicorn workers]
    Gunicorn --> Flask[Flask app]
    Backend --> Generated[(generated_data volume)]
    Backend --> Uploads[(uploads_data volume)]
```

## Generate Request Flow

```mermaid
flowchart LR
    Request[POST /generate] --> JSON[Validate JSON Prompt]
    JSON --> GraniteRequest[Send Prompt to Granite]
    GraniteRequest --> TikZ[Receive TikZ]
    TikZ --> Clean[Clean and Normalize]
    Clean --> Validate[Validate TikZ]
    Validate --> Compile[Compile PDF]
    Compile --> Preview[Create PNG]
    Preview --> Response[Return JSON Artifact URLs]
```

## Sequence Diagram

```mermaid
sequenceDiagram
    participant Browser
    participant Nginx
    participant Flask
    participant Granite
    participant Compiler

    Browser->>Nginx: POST /generate
    Nginx->>Flask: Proxy API request
    Flask->>Flask: Validate prompt
    Flask->>Granite: Request TikZ
    Granite-->>Flask: TikZ response
    Flask->>Flask: Clean and validate TikZ
    Flask->>Compiler: Compile PDF and PNG
    Compiler-->>Flask: Artifact paths
    Flask-->>Nginx: JSON response
    Nginx-->>Browser: TikZ and artifact URLs
```

## Runtime Responsibilities

- Nginx serves frontend assets and proxies API routes.
- Gunicorn manages production Python workers.
- Flask validates requests, handles rate limits, and returns JSON responses.
- IBM Granite generates and repairs TikZ.
- LaTeX and Poppler produce PDF and PNG artifacts.
- Docker volumes preserve generated outputs and uploads across restarts.
