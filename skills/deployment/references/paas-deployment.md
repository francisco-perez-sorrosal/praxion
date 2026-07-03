# PaaS Deployment

Platform-as-a-Service deployment patterns for Railway, Render, Fly.io, and Vercel. Back to [SKILL.md](../SKILL.md).

## Platform Comparison

| Feature | Railway | Render | Fly.io | Vercel |
|---------|---------|--------|--------|--------|
| **Best for** | Backends, databases | Full-stack apps | Global edge | Frontend, serverless |
| **Deploy from** | GitHub, CLI, Docker | GitHub, Docker | CLI (`flyctl`), Docker | GitHub, CLI |
| **Auto-detect** | Nixpacks (most languages) | Native runtimes + Docker | Dockerfile required | Framework presets |
| **Databases** | PostgreSQL, MySQL, Redis | PostgreSQL, Redis | Fly Postgres (self-managed) | External only (Neon, Supabase) |
| **Scaling** | Vertical auto-scale | Manual + auto-scale | Horizontal (Machines API) | Automatic (serverless) |
| **Regions** | US, EU, Asia | US, EU (limited) | 35+ worldwide | Edge network |
| **Free tier** | $5 trial credit | 750 hours/month | $5 free allowance | Hobby plan |
| **Pricing model** | Usage-based (CPU/memory/egress) | Instance hours | Per-machine + egress | Per-invocation |

## Railway

Agent-facing integration — installing Railway's first-party Claude Code plugin/MCP, per-context auth, environment and PR-environment lifecycle, CI wiring — lives in [railway.md](railway.md). This section covers platform basics.

### Project Structure

Railway organizes work into **projects** containing **services** and **environments** (staging, production).

```bash
# Install CLI
npm install -g @railway/cli

# Login and link to project
railway login
railway init          # New project
railway link          # Existing project
```

### Configuration

Railway auto-detects language and framework via Nixpacks. Override with `railway.toml`:

```toml
[build]
builder = "nixpacks"
buildCommand = "npm run build"

[deploy]
startCommand = "npm start"
healthcheckPath = "/health"
healthcheckTimeout = 300
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

### Environment Variables

```bash
railway variables set DATABASE_URL="postgresql://..."
railway variables set --environment production API_KEY="sk-..."
```

Variables are scoped per environment. Use **reference variables** to share across services: `${{service-name.VARIABLE_NAME}}`.

### Deployment

```bash
railway up              # Deploy from local
railway up --detach     # Deploy without watching logs
```

GitHub integration: push to the linked branch triggers automatic deployment. Set up via the Railway dashboard.

### Database Services

```bash
railway add             # Interactive service picker
# Select PostgreSQL, MySQL, or Redis
```

Connection strings are auto-injected as environment variables (`DATABASE_URL`, `REDIS_URL`).

### Gotchas

- **Sleep on free tier**: Services sleep after 10 minutes of inactivity. First request after sleep takes 5-15 seconds.
- **Ephemeral filesystem**: Local file writes are lost on redeploy. Use volumes for persistent storage.
- **Build timeouts**: Default 20 minutes. Long builds (ML dependencies) may need `nixpacksPlan` optimization.

## Render

### Configuration

Render uses `render.yaml` (Infrastructure as Code) or dashboard configuration:

```yaml
services:
  - type: web
    name: my-api
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
    healthCheckPath: /health
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: my-db
          property: connectionString
    autoDeploy: true

databases:
  - name: my-db
    plan: starter
    databaseName: myapp
```

### Service Types

| Type | Use Case | Example |
|------|----------|---------|
| **Web Service** | HTTP servers, APIs | FastAPI, Express |
| **Background Worker** | Queue consumers, cron | Celery, Bull |
| **Static Site** | SPAs, documentation | React, Vite |
| **Cron Job** | Scheduled tasks | Data sync, cleanup |
| **Private Service** | Internal-only services | gRPC backends |

### Deploy Commands

```bash
# Render CLI (limited compared to Railway)
render deploys list --service srv-abc123
render deploys create --service srv-abc123
```

Primary deployment is via GitHub integration -- push to branch triggers deploy.

### Gotchas

- **Cold starts on free tier**: Services spin down after 15 minutes. Cold start can take 30+ seconds.
- **No SSH access**: Cannot debug on the running instance. Use logs and health checks.
- **Region limitations**: Fewer regions than Railway or Fly.io. US-West and EU-Central only for most plans.

## Fly.io

### Core Concepts

Fly.io runs Docker containers as **Machines** in 35+ global regions. The `fly.toml` config defines the deployment:

```toml
app = "my-app"
primary_region = "iad"

[build]
  dockerfile = "Dockerfile"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 1

[checks]
  [checks.health]
    type = "http"
    port = 8000
    path = "/health"
    interval = "10s"
    timeout = "2s"

[[vm]]
  size = "shared-cpu-1x"
  memory = "512mb"
```

### Deployment

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Create and deploy
fly launch            # Interactive setup (creates fly.toml + Dockerfile)
fly deploy            # Deploy from local
fly deploy --remote-only  # Build on Fly's builders (no local Docker needed)
```

### Multi-Region

```bash
fly regions add cdg sin      # Add Paris and Singapore
fly scale count 2 --region iad,cdg   # 2 machines per region
```

Fly automatically routes users to the nearest region. Use `fly-replay` header to redirect reads to the primary region for database consistency.

### Volumes (Persistent Storage)

```bash
fly volumes create data --size 10 --region iad

# In fly.toml:
[mounts]
  source = "data"
  destination = "/app/data"
```

Volumes are per-region and per-machine. They do not replicate automatically.

### Gotchas

- **Machines API complexity**: Fly.io is powerful but more complex than Railway/Render. The Machines API is lower-level than typical PaaS.
- **Fly Postgres is self-managed**: Unlike Railway/Render managed databases, Fly Postgres requires you to handle backups, upgrades, and failover.
- **Volume limitations**: Volumes are bound to a single machine in a single region. Multi-region apps need separate volumes per region.
- **Builder costs**: Remote builders consume compute time. Large Docker images with ML dependencies can be expensive to build.

## Vercel

### Best For

Frontend applications, serverless API routes, and static sites. Not suitable for long-running backends, WebSockets, or stateful services.

### Configuration

```json
// vercel.json
{
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "framework": "vite",
  "functions": {
    "api/**/*.ts": {
      "memory": 1024,
      "maxDuration": 30
    }
  },
  "rewrites": [
    { "source": "/api/:path*", "destination": "/api/:path*" },
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

### Serverless Functions

```typescript
// api/users/[id].ts
import type { VercelRequest, VercelResponse } from "@vercel/node";

export default async function handler(
  req: VercelRequest,
  res: VercelResponse,
) {
  const { id } = req.query;
  const user = await fetchUser(id as string);
  return res.status(200).json(user);
}
```

### Gotchas

- **10-second default timeout**: Serverless functions time out at 10s (free), 60s (Pro), 300s (Enterprise). Not suitable for long-running tasks.
- **No persistent connections**: WebSockets, SSE, and long-polling do not work in serverless functions. Use Edge Functions or external services.
- **Cold starts**: First invocation after idle period adds 200-500ms latency.
- **No background workers**: Vercel is request-response only. Use external services (Inngest, Trigger.dev) for background jobs.

## Decision Matrix

| Scenario | Recommended | Why |
|----------|-------------|-----|
| Python API + PostgreSQL | Railway | Best DX, auto-managed DB, usage pricing |
| Full-stack Next.js app | Vercel | Native framework support, edge network |
| Multi-region API | Fly.io | 35+ regions, Machines API |
| Static site + API | Render | Simple setup, free tier for static sites |
| Quick prototype | Railway | Fastest from zero to deployed |
| Budget-constrained | Render free tier | Most generous free compute hours |
| Global low-latency | Fly.io | Edge deployment, auto-routing |

## Compose-to-PaaS Migration

When migrating from Docker Compose to PaaS:

1. **Extract service configs**: Each Compose service becomes a PaaS service
2. **Replace database services**: Use managed databases (Railway/Render) instead of containerized PostgreSQL
3. **Move env vars**: Transfer `.env` values to PaaS environment variable management
4. **Update connection strings**: Replace `service-name:port` hostnames with managed database URLs
5. **Remove volumes**: Use managed storage or object storage (S3, R2) for persistent data
6. **Health checks**: Map Compose `healthcheck` to PaaS health check configuration
