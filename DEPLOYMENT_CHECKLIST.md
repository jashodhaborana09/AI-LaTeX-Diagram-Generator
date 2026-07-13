# Deployment Checklist

Use this checklist for production or portfolio deployments.

## Required Configuration

- [ ] `IBM_API_KEY`
- [ ] `IBM_PROJECT_ID`
- [ ] `IBM_URL`
- [ ] `VALIDATE_ENV_ON_START=true`
- [ ] `LOG_LEVEL=INFO`
- [ ] `MAX_PROMPT_LENGTH=3000`
- [ ] `MAX_UPLOAD_SIZE=10485760`
- [ ] `REQUEST_TIMEOUT=60`
- [ ] `WORKERS` sized for the deployment plan

## Container

- [ ] Build from the included `Dockerfile`.
- [ ] Confirm the container binds to `0.0.0.0:$PORT`.
- [ ] Confirm the platform health check points to `/health`.
- [ ] Confirm generated artifact storage is persistent when required.
- [ ] Confirm logs are collected from stdout and stderr.

## Reverse Proxy and HTTPS

- [ ] Nginx proxies `/health`, `/generate`, `/upload`, `/refine`, and `/generated/`.
- [ ] HTTPS is terminated by the platform load balancer or self-managed Nginx certificate config.
- [ ] Upload body limit matches `MAX_UPLOAD_SIZE`.
- [ ] Security headers are present.

## Operations

- [ ] Rate limit storage is appropriate for the deployment topology.
- [ ] IBM credentials are stored as secrets, not committed files.
- [ ] Generated files are backed up or cleaned up according to the deployment policy.
- [ ] Monitoring checks `/health`.
- [ ] Rollback image or previous release tag is available.
