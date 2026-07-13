# Security Policy

## Supported Version

Security updates are accepted for the current public release line.

| Version | Supported |
| --- | --- |
| 1.0.x | Yes |

## Reporting a Vulnerability

Please do not open public issues for vulnerabilities involving secrets, authentication, file handling, container configuration, or dependency exposure.

Report security concerns privately to the project maintainer. Include:

- A clear description of the issue.
- Steps to reproduce.
- Affected routes, files, or deployment settings.
- Any relevant logs with secrets removed.

## Security Expectations

- Never commit `.env` files, IBM API keys, project IDs, or private certificates.
- Keep `VALIDATE_ENV_ON_START=true` in production.
- Use HTTPS at the platform or reverse-proxy layer.
- Use a persistent rate-limit backend such as Redis for multi-instance production deployments.
- Rotate IBM watsonx.ai credentials if they are exposed.
