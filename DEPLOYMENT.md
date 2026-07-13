# Cloud Deployment Guide

This guide deploys the AI LaTeX Diagram Generator with Docker, Gunicorn, and Nginx.

## Deployment URL

Production URL: `pending-cloud-deployment`

Replace this value after the selected cloud platform creates the public HTTPS URL.

## Container Options

Use one of these deployment modes:

- `docker-compose.yml`: local or VM deployment with separate `backend` and `nginx` containers.
- `Dockerfile.cloud`: single-container public-cloud deployment with Nginx listening on `$PORT` and proxying to Gunicorn on `$APP_PORT`.

For Render, Railway, Google Cloud Run, and Azure App Service, use `Dockerfile.cloud` so Gunicorn and Nginx stay together in one deployable container.

## Production Environment Variables

Configure these as cloud secrets or protected environment variables:

| Variable | Required | Production value |
| --- | --- | --- |
| `IBM_API_KEY` | Yes | IBM watsonx.ai API key. |
| `IBM_PROJECT_ID` | Yes | IBM watsonx.ai project ID. |
| `IBM_URL` | Yes | IBM watsonx.ai service URL. |
| `MODEL_ID` | No | `ibm/granite-4-h-small` unless using another enabled model. |
| `VALIDATE_ENV_ON_START` | Yes | `true` |
| `LOG_LEVEL` | No | `INFO` |
| `MAX_PROMPT_LENGTH` | No | `3000` |
| `MAX_UPLOAD_SIZE` | No | `10485760` |
| `REQUEST_TIMEOUT` | No | `60` or higher on smaller instances. |
| `WORKERS` | No | `2` for small instances; increase with CPU. |
| `APP_PORT` | No | `5000` |
| `PORT` | Platform | Let the platform inject this when available. |
| `RATELIMIT_STORAGE_URI` | No | Use Redis-compatible storage for multi-instance production. |

Do not store IBM credentials in `.env`, Docker build arguments, Dockerfile instructions, or committed files.

## Health Check

Use:

```text
/health
```

Expected response:

```json
{
  "status": "healthy",
  "service": "AI LaTeX Diagram Generator",
  "model": "IBM Granite 4 H Small",
  "version": "1.0.0"
}
```

## HTTPS

Render, Railway, Google Cloud Run, and Azure App Service provide managed HTTPS at the public edge. `Dockerfile.cloud` runs HTTP inside the container and lets the platform terminate TLS before proxying traffic to Nginx.

## Automatic Restart

Managed platforms restart failed containers automatically. For local or VM deployments, `docker-compose.yml` sets `restart: unless-stopped` for both `backend` and `nginx`.

## Render

Render supports Docker-based deploys from a repository Dockerfile.

1. Create a new Web Service.
2. Connect the GitHub repository.
3. Set runtime/language to Docker.
4. Set Dockerfile path to `Dockerfile.cloud`.
5. Set health check path to `/health`.
6. Add production secrets:
   - `IBM_API_KEY`
   - `IBM_PROJECT_ID`
   - `IBM_URL`
   - `VALIDATE_ENV_ON_START=true`
   - optional values from the environment table.
7. Deploy.
8. Copy the Render HTTPS service URL into the README deployment URL section.

Post-deploy verification:

```bash
export APP_URL="https://your-render-service.onrender.com"
curl --fail "$APP_URL/health"
```

## Railway

Railway supports Dockerfile-based builds from a repository.

1. Create a new Railway project from the GitHub repository.
2. Configure the service to build with `Dockerfile.cloud`.
3. Add the IBM watsonx.ai secrets and production variables.
4. Ensure the service uses the platform-provided public domain.
5. Confirm Railway injects `PORT`; `Dockerfile.cloud` Nginx listens on that value.
6. Deploy.
7. Copy the Railway HTTPS service URL into the README deployment URL section.

Post-deploy verification:

```bash
export APP_URL="https://your-service.up.railway.app"
curl --fail "$APP_URL/health"
```

## Google Cloud Run

Cloud Run injects `PORT` into the ingress container and terminates TLS at the platform edge.

1. Build and push the cloud image:

```bash
docker build -f Dockerfile.cloud \
  -t REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY/ai-latex-diagram-generator:1.0.0 .

docker push REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY/ai-latex-diagram-generator:1.0.0
```

2. Deploy to Cloud Run:

```bash
gcloud run deploy ai-latex-diagram-generator \
  --image REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY/ai-latex-diagram-generator:1.0.0 \
  --region REGION \
  --allow-unauthenticated \
  --set-env-vars VALIDATE_ENV_ON_START=true,APP_PORT=5000,LOG_LEVEL=INFO \
  --set-secrets IBM_API_KEY=IBM_API_KEY:latest,IBM_PROJECT_ID=IBM_PROJECT_ID:latest,IBM_URL=IBM_URL:latest
```

3. Configure startup or HTTP health probe path as `/health` if probes are enabled.
4. Copy the Cloud Run HTTPS URL into the README deployment URL section.

Post-deploy verification:

```bash
export APP_URL="https://your-cloud-run-url"
curl --fail "$APP_URL/health"
```

## Azure App Service

Azure App Service custom containers can receive runtime settings as App Settings.

1. Build and push the cloud image to Azure Container Registry:

```bash
az acr build \
  --registry ACR_NAME \
  --image ai-latex-diagram-generator:1.0.0 \
  --file Dockerfile.cloud .
```

2. Create or configure a Linux Web App for Containers using that image.
3. Set App Settings:

```bash
az webapp config appsettings set \
  --resource-group RESOURCE_GROUP \
  --name APP_NAME \
  --settings \
    WEBSITES_PORT=8080 \
    PORT=8080 \
    APP_PORT=5000 \
    VALIDATE_ENV_ON_START=true \
    IBM_API_KEY="..." \
    IBM_PROJECT_ID="..." \
    IBM_URL="..."
```

4. Enable the App Service health check path `/health`.
5. HTTPS is available on the default `azurewebsites.net` domain and custom domains with managed certificates.
6. Copy the Azure HTTPS URL into the README deployment URL section.

Post-deploy verification:

```bash
export APP_URL="https://APP_NAME.azurewebsites.net"
curl --fail "$APP_URL/health"
```

## Functional Verification

Run these checks against the deployed URL.

### Health

```bash
curl --fail "$APP_URL/health"
```

### Uploads

```bash
curl --fail -X POST "$APP_URL/upload" \
  -F "file=@path/to/small-diagram.png"
```

Use any small PNG, JPG, or JPEG file.

### IBM Granite, PDF, and PNG Generation

```bash
curl --fail -X POST "$APP_URL/generate" \
  -H "Content-Type: application/json" \
  -d "{\"prompt\":\"Draw a simple flowchart with Start, Process, and End.\"}"
```

Confirm the JSON response has:

- `"success": true`
- non-empty `tikz`
- `pdf` URL
- `png` URL
- `tex` URL

Then fetch the generated files:

```bash
curl --fail -o diagram.pdf "$APP_URL/generated/pdf/<job_id>.pdf"
curl --fail -o diagram.png "$APP_URL/generated/images/<job_id>.png"
curl --fail -o diagram.tex "$APP_URL/generated/latex/<job_id>.tex"
```

This verifies IBM Granite integration, LaTeX PDF generation, PNG preview generation, and generated artifact routing.

## Persistence Notes

The app writes generated files to local container storage by default. For portfolio demos, this is usually acceptable. For production use, configure persistent disks, mounted storage, or object storage for generated artifacts and uploads.
