---
name: deployment
description: >
  Application deployment: local Docker Compose, PaaS, cloud containers,
  Kubernetes, AI-native GPU platforms. Covers deployment primitives, Docker
  Compose patterns (watch mode, profiles, GPU passthrough, health checks),
  dev-to-production spectrum, reverse proxy, secrets, AI/ML model serving.
  Use when deploying an app, writing compose.yaml or Dockerfile, setting up
  a production server, choosing a hosting platform, configuring Caddy or
  nginx, deploying AI models with Ollama or vLLM, GPU passthrough, managing
  secrets, choosing PaaS (Render, Railway, Fly.io, Vercel), deploying to
  Cloud Run, ECS, Modal, CoreWeave, or writing systemd units for Compose.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "Platform Quick Reference"
---

# Deployment

Opinionated guidance for deploying applications -- from local Docker Compose through cloud PaaS to AI-native GPU platforms. Docker Compose is the gravity center: start local, extend outward.

**Content boundary:**
- **This skill** = deployment target configuration (what to deploy, where, how to configure it)
- **CI/CD skill** = pipeline automation (how to trigger deployments from GitHub Actions)
- **Observability skill** = instrumentation strategy (how to monitor deployed services)
- **Performance-architecture skill** = capacity planning (how to size resources)

**Satellite files** (loaded on-demand):

- [references/local-deployment.md](references/local-deployment.md) -- Docker Compose deep-dive, process managers, macOS container runtimes, container vs native trade-offs
- [references/reverse-proxy-and-tls.md](references/reverse-proxy-and-tls.md) -- Caddy (recommended), nginx, Traefik patterns, mkcert for local HTTPS
- [references/ai-ml-serving.md](references/ai-ml-serving.md) -- Ollama, vLLM, GPU memory, model serving patterns, Python environment isolation
- [references/secrets-management.md](references/secrets-management.md) -- .env, direnv, SOPS+age, 1Password CLI, progression from solo to team
- [references/paas-deployment.md](references/paas-deployment.md) -- Render, Railway, Fly.io, Vercel patterns and config examples
- [references/self-hosted-paas.md](references/self-hosted-paas.md) -- Coolify, CapRover, Docker Compose as PaaS descriptor
- [references/cloud-containers.md](references/cloud-containers.md) -- Cloud Run, ECS/Fargate, Azure Container Apps
- [references/kubernetes-patterns.md](references/kubernetes-patterns.md) -- when K8s is warranted, basic patterns, managed K8s comparison
- [references/ai-native-platforms.md](references/ai-native-platforms.md) -- Modal, CoreWeave, RunPod, Nebius, GPU marketplace

**Starter templates** (in `assets/`):

- `compose-web-db.yaml` -- Python/Node web app + PostgreSQL + Redis
- `compose-ai-serving.yaml` -- Ollama with GPU + API gateway
- `Caddyfile.local` -- reverse proxy with mkcert TLS
- `Caddyfile.production` -- automatic HTTPS via Let's Encrypt
- `systemd-compose.service` -- systemd unit for Compose lifecycle

## Gotchas

- **Compose `version:` field is obsolete** -- modern `compose.yaml` files start with `services:` directly. Drop the `version:` key and rename `docker-compose.yml` to `compose.yaml`
- **TGI is in maintenance mode (Dec 2025)** -- HuggingFace recommends vLLM or SGLang. Do not recommend TGI for new deployments
- **Missing health checks cause cascading startup failures** -- `depends_on` without `condition: service_healthy` only waits for container start, not readiness. Always pair with health checks
- **GPU memory underestimation** -- an 8B parameter model at FP16 needs ~16GB VRAM; add KV cache overhead (~4.5GB at 32K context). Consumer GPUs (RTX 4090, 24GB) max out at ~13B FP16
- **Secrets in environment variables committed to git** -- `.env` files must be gitignored. Use `.env.example` with empty values as the committed template
- **Docker Desktop licensing** -- Docker Desktop is commercial ($5/user/month for businesses 250+ employees). Consider OrbStack (macOS) or Colima (open-source) as alternatives
- **Port 5432 conflicts** -- if PostgreSQL is installed locally AND in Docker, port conflicts are silent until connection errors appear. Use non-default host ports in compose: `"5433:5432"`
- **`docker compose up` without `-d` blocks the terminal** -- always use `docker compose up -d` for background operation, then `docker compose logs -f` for streaming logs
- **Caddy vs nginx default behavior** -- Caddy enables HTTPS by default (even locally with self-signed certs). If you want plain HTTP for local dev, use `http://` explicitly in the Caddyfile
- **Deployment doc drift in Direct/Lightweight tier** -- when modifying `compose.yaml`, `Dockerfile`, `Caddyfile`, or `.env.example` outside a pipeline (Direct/Lightweight work), check if `.ai-state/SYSTEM_DEPLOYMENT.md` exists and update the affected sections. Pipeline agents handle this automatically; the main agent must do it manually

## Deployment Primitives

Seven universal concepts that every deployment target expresses differently. Use this vocabulary when discussing deployment regardless of platform.

| Primitive | What It Answers | Docker Compose | PaaS (Render/Railway) | Kubernetes |
|-----------|----------------|----------------|----------------------|------------|
| **Compute** | What runs the code? | `services.*.image` or `build` | Runtime auto-detection | `Pod` spec |
| **Networking** | How does traffic reach it? | `ports`, service name DNS | Platform-managed, custom domains | `Service`, `Ingress` |
| **Storage** | Where does data persist? | `volumes` (named/bind) | Managed databases | `PersistentVolumeClaim` |
| **Configuration** | How does it know its environment? | `environment`, `env_file` | Platform env vars UI/CLI | `ConfigMap`, `Secret` |
| **Health** | How does the platform know it works? | `healthcheck` | `healthcheckPath` | `readinessProbe`, `livenessProbe` |
| **Scaling** | How does it handle load? | `deploy.replicas`, `resources` | Platform-managed autoscaling | `HorizontalPodAutoscaler` |
| **Dependencies** | What else does it need? | Other services in `compose.yaml` | Managed add-ons (databases, caches) | Separate deployments, operators |

## Decision Framework

Start here when choosing a deployment target. The framework is opinionated -- defaults are recommended starting points, not the only options.

### Q1: Local development or production?

**Local** --> Docker Compose (continue to [Local-First Core](#local-first-core) below)

**Production** --> continue to Q2

### Q2: Do you need GPU / AI model serving?

**Yes, locally** --> Docker Compose + GPU passthrough --> [ai-ml-serving.md](references/ai-ml-serving.md)

**Yes, cloud** --> **Modal** (simplest) or CoreWeave (if K8s team) --> [ai-native-platforms.md](references/ai-native-platforms.md)

**No** --> continue to Q3

### Q3: How many services?

**1 service** --> PaaS: **Railway** (backends) or **Render** (full-stack) --> [paas-deployment.md](references/paas-deployment.md)

**2-4 services** --> PaaS or Cloud Run (GCP) / ECS (AWS) depending on budget

**5+ services** --> Cloud containers or Kubernetes --> [cloud-containers.md](references/cloud-containers.md), [kubernetes-patterns.md](references/kubernetes-patterns.md)

### Q4: Want to manage servers?

**No (zero-ops)** --> PaaS: Railway, Render, or Fly.io (global edge)

**Own hardware** --> Docker Compose + systemd, or self-hosted PaaS (Coolify) --> [self-hosted-paas.md](references/self-hosted-paas.md)

**Cloud managed** --> Cloud Run (GCP, simplest) or ECS/Fargate (AWS)

### Q5: Budget constraint?

**$0-20/month** --> Railway/Render free tier, or single VPS + Compose

**$20-200/month** --> PaaS or small Cloud Run / ECS setup

**Enterprise** --> Cloud containers or managed K8s with IaC (Terraform/Pulumi)

### Default Recommendations

For most projects, start here:

| Scenario | Recommended | Why |
|----------|-------------|-----|
| Local development | Docker Compose | Universal standard, team-friendly |
| Simple production web app | Railway or Render | Near-zero config, managed infra |
| Production with own servers | Docker Compose + Caddy + systemd | Simple, proven, no orchestrator |
| GPU/AI model serving (local) | Ollama in Docker Compose | Simplest path, good dev UX |
| GPU/AI model serving (cloud) | Modal | Python-native, scale-to-zero |
| Global edge deployment | Fly.io | 35+ regions, Machines API |
| Microservices (5+) | GKE Autopilot or ECS | Managed orchestration |

## Local-First Core

Docker Compose is the default for local multi-service deployment. Modern Compose (`compose.yaml`, no `version:` field) with these patterns:

### Minimal Web + Database

```yaml
services:
  app:
    build: .
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: "postgresql://postgres:postgres@db:5432/app"
    depends_on:
      db:
        condition: service_healthy
    develop:
      watch:
        - action: sync
          path: ./src
          target: /app/src
        - action: rebuild
          path: ./requirements.txt

  db:
    image: postgres:17
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: app
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
```

### Key Compose Patterns

**Watch mode** (eliminates rebuild cycles):
- `sync` -- hot-sync files to container (frameworks with hot reload)
- `rebuild` -- rebuild image on dependency changes
- `sync+restart` -- sync files then restart container (config changes)

Run with: `docker compose up --watch`

**Profiles** (optional services without separate files):

```yaml
services:
  redis:
    image: redis:7-alpine
    profiles: ["cache"]
  mailhog:
    image: mailhog/mailhog
    profiles: ["debug"]
```

Enable with: `docker compose --profile cache --profile debug up`

**Resource limits** (prevent a single service from exhausting the host):

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 1G
        reservations:
          cpus: "0.5"
          memory: 256M
```

**GPU passthrough** (for AI/ML workloads):

```yaml
services:
  ollama:
    image: ollama/ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    volumes:
      - ollama_data:/root/.ollama
    ports: ["11434:11434"]
```

## Dev-to-Production Spectrum

Four levels on a single machine. Move up when you hit the trigger condition.

### Level 1: Dev Server

```
uvicorn main:app --reload    # or: npm run dev
```

SQLite or in-memory. No proxy. No TLS. **Trigger to move up:** need a database, second service, or team collaboration.

### Level 2: Dev Compose

```
docker compose up --watch
```

PostgreSQL in Docker. Service networking. Watch mode for hot reload. **Trigger to move up:** need production-like behavior, TLS, or load testing.

### Level 3: Prod-Like Compose

- gunicorn + uvicorn workers (no `--reload`)
- Caddy reverse proxy with mkcert TLS
- Health checks, resource limits, restart policies
- Structured logging

**Trigger to move up:** deploying to a real server for users.

### Level 4: Single-Server Production

- Same Compose file with production environment overrides
- Caddy with automatic HTTPS (Let's Encrypt)
- systemd managing Compose lifecycle (`systemd-compose.service` template)
- Monitoring, backups, log rotation

See [local-deployment.md](references/local-deployment.md) for full details on each level.

## Python Serving Patterns

| Mode | Command | Workers | Use Case |
|------|---------|---------|----------|
| Development | `uvicorn main:app --reload` | 1 | Local dev with hot reload |
| Simple production | `uvicorn main:app --workers 4` | 4 | Simple deployments |
| Full production | `gunicorn main:app -k uvicorn.workers.UvicornWorker -w 4` | Managed | Production with process management |

**Worker count:** `2 * CPU_CORES + 1` for I/O-bound workloads; `CPU_CORES` for CPU-bound.

**Always put gunicorn behind a reverse proxy** (Caddy recommended) for TLS termination, static file serving, and request buffering.

## Platform Quick Reference

When ready to move beyond local deployment:

| Category | Platforms | When to Use | Reference |
|----------|-----------|-------------|-----------|
| **PaaS** | Railway, Render, Fly.io, Vercel | Simple apps, small teams, fast time-to-deploy | [paas-deployment.md](references/paas-deployment.md) |
| **Self-hosted PaaS** | Coolify, CapRover | PaaS experience on your own servers | [self-hosted-paas.md](references/self-hosted-paas.md) |
| **Cloud containers** | Cloud Run, ECS/Fargate, Azure Container Apps | Managed scaling, cloud-native apps | [cloud-containers.md](references/cloud-containers.md) |
| **Kubernetes** | GKE, EKS, AKS | 5+ services, complex networking, team has K8s expertise | [kubernetes-patterns.md](references/kubernetes-patterns.md) |
| **AI-native** | Modal, CoreWeave, RunPod, Nebius | GPU workloads, model serving, ML training | [ai-native-platforms.md](references/ai-native-platforms.md) |

## Project Deployment Documentation

This skill provides generic deployment *knowledge* (primitives, patterns, decision framework). Each project captures its specific deployment *state* in `.ai-state/SYSTEM_DEPLOYMENT.md` -- a living document maintained by the agent pipeline.

**Template**: [`assets/SYSTEM_DEPLOYMENT_TEMPLATE.md`](assets/SYSTEM_DEPLOYMENT_TEMPLATE.md) -- 10-section template with Mermaid diagrams, FMA tables, and runbook structure. The systems-architect creates the initial document from this template during Phase 3 when the project has deployable components.

**Methodology**: [`references/deployment-documentation.md`](references/deployment-documentation.md) -- living document lifecycle, section ownership model, and staleness mitigation strategy.

When loaded, agents working on deployment should check for `.ai-state/SYSTEM_DEPLOYMENT.md` and read current state before making deployment decisions. The document is complementary to ADRs -- it captures *what is deployed now*; ADRs capture *why those decisions were made*.

## Integration with Other Skills

- [CI/CD](../cicd/SKILL.md) -- pipeline automation that triggers deployments
- [Observability](../observability/SKILL.md) -- instrumentation for deployed services
- [Performance Architecture](../performance-architecture/SKILL.md) -- capacity planning and scaling decisions
- [Python Development](../python-development/SKILL.md) -- Python-specific tooling (uvicorn, gunicorn, uv, pixi)
- [API Design](../api-design/SKILL.md) -- service boundary contracts that shape deployment topology
