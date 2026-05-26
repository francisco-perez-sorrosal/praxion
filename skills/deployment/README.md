# deployment

Application deployment guidance from local Docker Compose through cloud PaaS to AI-native GPU platforms. Covers Docker Compose patterns (watch mode, profiles, GPU passthrough, health checks), reverse proxies, secrets management, PaaS/cloud/Kubernetes targets, and AI/ML model serving.

## When to Use

- Writing or reviewing `compose.yaml`, `Dockerfile`, or `Caddyfile`
- Choosing a deployment platform (Railway, Render, Fly.io, Cloud Run, ECS, Modal, CoreWeave)
- Configuring GPU passthrough or AI/ML model serving (Ollama, vLLM)
- Setting up secrets management (`.env`, SOPS+age, 1Password CLI)
- Deploying to Kubernetes or self-hosted PaaS (Coolify, CapRover)
- Deciding between deployment levels (dev server → dev Compose → prod-like Compose → single-server production)
- Updating `.ai-state/SYSTEM_DEPLOYMENT.md` after deployment changes

## Activation

Activates automatically when working on deployment configuration files (`compose.yaml`, `Dockerfile`, `Caddyfile`, etc.) or discussing platform selection, reverse proxy setup, GPU workloads, or containerized deployment.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Decision framework, deployment primitives, Docker Compose patterns, dev-to-production spectrum, platform quick reference |
| `references/local-deployment.md` | Docker Compose deep-dive, process managers, macOS container runtimes |
| `references/reverse-proxy-and-tls.md` | Caddy, nginx, Traefik patterns; mkcert for local HTTPS |
| `references/ai-ml-serving.md` | Ollama, vLLM, GPU memory estimation, model serving patterns |
| `references/secrets-management.md` | .env, direnv, SOPS+age, 1Password CLI progression |
| `references/paas-deployment.md` | Railway, Render, Fly.io, Vercel patterns and config examples |
| `references/self-hosted-paas.md` | Coolify, CapRover, Docker Compose as PaaS descriptor |
| `references/cloud-containers.md` | Cloud Run, ECS/Fargate, Azure Container Apps |
| `references/kubernetes-patterns.md` | When K8s is warranted, essential patterns, managed K8s comparison |
| `references/ai-native-platforms.md` | Modal, CoreWeave, RunPod, Nebius, GPU marketplace |
| `references/gpu-compute-budgeting.md` | GPU compute budget enforcement patterns for ML training |
| `references/deployment-documentation.md` | `SYSTEM_DEPLOYMENT.md` lifecycle, section ownership, staleness mitigation |
| `contexts/typescript.md` | TypeScript/Node.js deployment: multi-stage Dockerfile, pnpm, Node 22 LTS |
| `assets/` | Starter templates: `compose-web-db.yaml`, `compose-ai-serving.yaml`, `Caddyfile.*`, `systemd-compose.service` |

## Related Skills

- [`cicd`](../cicd/) -- pipeline automation that triggers deployments; DORA metrics
- [`observability`](../observability/) -- instrumentation and monitoring for deployed services
- [`performance-architecture`](../performance-architecture/) -- capacity planning and scaling decisions
- [`python-development`](../python-development/) -- uvicorn, gunicorn, uv, pixi for Python services
- [`api-design`](../api-design/) -- service boundary contracts that shape deployment topology
