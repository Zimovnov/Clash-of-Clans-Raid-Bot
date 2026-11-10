# OCI Deployment Readiness

Production remains on the current VPS until a separate cutover.

The shared infrastructure repository runs this project as:

- `clashinfobot-db`: private PostgreSQL;
- `clashinfobot-api`: internal-only API;
- `clashinfobot-bot`: Telegram polling and scheduler.

GitOps deployment is defined in `.github/workflows/oci-deploy.yml` and remains disabled until repository variable `OCI_GITOPS_ENABLED=true` is set after test-bot, restore and rollback acceptance.

Required GitHub secrets: `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET`, `OCI_SSH_PRIVATE_KEY`, `OCI_TAILSCALE_IP`.
PostgreSQL and the API remain private inside the OCI Docker network.

`pip-audit` temporarily ignores `CVE-2026-34993` and `CVE-2026-47265` because
the current aiogram release requires `aiohttp<3.14`. ClashInfoBot uses aiohttp
only for outbound calls. Remove both exceptions as soon as aiogram supports
aiohttp 3.14 or newer.
