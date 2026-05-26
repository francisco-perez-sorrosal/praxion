# Deployment — TypeScript/Node.js Context

Node.js production deployment patterns. Assumes the `deployment` SKILL.md body is
loaded for the platform decision framework and Compose primitives. Back to [SKILL.md](../SKILL.md).

For **package manager setup** (pnpm, volta, workspace config), see
[`node-prj-mgmt/contexts/typescript.md`](../../node-prj-mgmt/contexts/typescript.md).

For **build tool configuration** (Biome, ESLint, tsc, Vitest), see
[`typescript-development/contexts/typescript.md`](../../typescript-development/contexts/typescript.md).

---

## Multi-Stage Dockerfile — Node 22 LTS

The canonical pattern for TypeScript services: a builder stage compiles TypeScript,
a runner stage ships only the compiled JavaScript and production dependencies.

```dockerfile
# syntax=docker/dockerfile:1

# ── Stage 1: build ──────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

# Install pnpm (enable corepack in Node 22)
RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

# Copy manifests first for layer-cache efficiency
COPY package.json pnpm-lock.yaml ./

# fetch: populate the virtual store without touching node_modules
# --frozen-lockfile ensures the lock is not implicitly updated
RUN pnpm fetch --frozen-lockfile

# install: resolve from the prefetched virtual store (no network)
# --offline guarantees the build is reproducible even in air-gapped envs
RUN pnpm install --offline

COPY . .

# type-check + compile (tsc emits to dist/)
RUN pnpm run build

# ── Stage 2: production runner ───────────────────────────────────────────────
FROM node:22-alpine AS runner

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

ENV NODE_ENV=production

COPY package.json pnpm-lock.yaml ./

# --omit=dev installs only production dependencies
# NOTE: --only=production is deprecated since npm v9; use --omit=dev instead
RUN pnpm install --prod --frozen-lockfile

# Copy compiled output from builder stage
COPY --from=builder /app/dist ./dist

EXPOSE 3000

# Run directly with node; add PM2 or cluster mode if process management is needed
CMD ["node", "dist/index.js"]
```

### Key points

| Aspect | This pattern | Python equivalent |
|--------|-------------|-------------------|
| Compile step | `tsc` emits to `dist/` | Optional (`mypy`/`pyright` do not emit) |
| Prod-only deps | `pnpm install --prod` / `--omit=dev` | `pip install --no-dev` / `uv sync --no-dev` |
| Base image | `node:22-alpine` | `python:3.12-slim` |
| Process manager | `node dist/index.js` (PM2 optional) | `gunicorn` + uvicorn workers |
| Lock file | `pnpm-lock.yaml` | `uv.lock` / `requirements.txt` |

**Node version pinning in Docker**: always pin the major version in the `FROM` line
(`node:22-alpine` not `node:lts-alpine`). `node:lts` shifts silently when Node 24
becomes LTS. Use `node:22-alpine3.21` for a fully reproducible build.

**`--experimental-strip-types` alternative**: Node 22.6+ can run TypeScript source
directly by stripping type annotations at runtime (no decorators, no enums, no
`paths` aliases). Suitable for single-file scripts or simple services with no build
step; not recommended for applications with complex types or monorepo setups.

---

## pnpm in Docker Containers

The `pnpm fetch` + `pnpm install --offline` pattern avoids re-downloading packages on
every image rebuild.

```
Layer                                          Invalidated when
─────────────────────────────────────────────────────────────────
COPY package.json pnpm-lock.yaml ./            lock file changes
RUN pnpm fetch --frozen-lockfile               lock file changes
RUN pnpm install --offline                     lock file changes
COPY . .                                       any source change
RUN pnpm run build                             any source change
```

This ordering keeps the expensive `pnpm fetch` layer cached across source-only changes.
When only `.ts` files change, Docker reuses the first three layers.

**`corepack enable`**: Node 22 ships corepack by default but it is not activated.
`corepack enable` + `corepack prepare pnpm@latest --activate` pins pnpm without a
global `npm install -g pnpm`, keeping the base image clean.

**Monorepo builds** — when building a single workspace package from a pnpm monorepo:

```dockerfile
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages/my-service/package.json ./packages/my-service/
RUN pnpm fetch --frozen-lockfile
RUN pnpm install --offline --filter my-service...
```

The `--filter` flag limits installation to the target package and its workspace
dependencies. Without `--filter`, all workspace packages install, bloating the image.

---

## Health Check Conventions

Node.js services should expose two endpoints for container-level and load-balancer
health probing.

| Endpoint | Purpose | Response | When returns 5xx |
|----------|---------|----------|------------------|
| `GET /health` | Liveness — is the process alive? | `{ "status": "ok" }` | Process is in a bad state and should restart |
| `GET /ready` | Readiness — can the service serve traffic? | `{ "status": "ready" }` | Dependencies (DB, cache) not yet connected |

**Express pattern**:

```typescript
import { Router } from 'express';

const healthRouter = Router();

// Liveness — only checks the process itself
healthRouter.get('/health', (_req, res) => {
  res.json({ status: 'ok' });
});

// Readiness — checks upstream dependencies
healthRouter.get('/ready', async (_req, res) => {
  try {
    await db.raw('SELECT 1');   // or equivalent ping
    res.json({ status: 'ready' });
  } catch {
    res.status(503).json({ status: 'unavailable' });
  }
});

export { healthRouter };
```

**Dockerfile health check**:

```dockerfile
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
  CMD wget -qO- http://localhost:3000/health || exit 1
```

`wget` is available in `node:22-alpine`; `curl` is not installed by default.

---

## `compose.yaml` for Node Services

```yaml
services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
      target: runner            # use the final stage for production
    ports:
      - "3000:3000"
    environment:
      NODE_ENV: production
      DATABASE_URL: "postgresql://postgres:postgres@db:5432/app"
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:3000/health"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 512M

  db:
    image: postgres:17-alpine
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

**Development hot-reload** via Compose watch (no rebuild on `.ts` file changes when
using a dev server like `tsx --watch` or `ts-node-dev`):

```yaml
  api:
    build:
      context: .
      target: builder           # use the builder stage for dev
    command: pnpm run dev       # starts tsx --watch or similar
    develop:
      watch:
        - action: sync
          path: ./src
          target: /app/src
        - action: rebuild
          path: ./package.json
```

---

## Railway Deployment for Node Apps

Railway auto-detects Node.js projects via Nixpacks (looks for `package.json`). No
`railway.toml` is required for basic deployments.

**`railway.toml` for TypeScript projects**:

```toml
[build]
builder = "nixpacks"
buildCommand = "pnpm install && pnpm run build"

[deploy]
startCommand = "node dist/index.js"
healthcheckPath = "/health"
healthcheckTimeout = 300
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

**Node-specific Railway gotchas**:

- **Nixpacks installs with npm by default** even when `pnpm-lock.yaml` is present.
  Override with `NIXPACKS_PKGS=nodejs_20 pnpm` in Railway environment variables, or
  provide an explicit `buildCommand` that calls `pnpm install` directly.
- **`dist/` is not committed** — Railway must build on its side. Confirm `build` in
  `scripts` runs `tsc` or equivalent bundler. Without a build step, `node dist/index.js`
  fails with ENOENT.
- **Environment variable access**: Railway injects `PORT` at runtime. Always bind to
  `process.env.PORT ?? 3000` rather than a hardcoded port.

---

## Fly.io Deployment for Node Apps

Fly.io requires a `Dockerfile`. Use the multi-stage pattern above. `fly launch`
generates `fly.toml` and detects the Dockerfile automatically.

**`fly.toml` for a Node API**:

```toml
[build]
  dockerfile = "Dockerfile"

[http_service]
  internal_port = 3000
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 0    # scale-to-zero on free tier

  [http_service.concurrency]
    type = "requests"
    hard_limit = 250

[[vm]]
  memory = "256mb"
  cpu_kind = "shared"
  cpus = 1
```

**Fly health checks** are declared in `fly.toml`:

```toml
[[http_service.checks]]
  interval = "10s"
  timeout = "5s"
  grace_period = "15s"
  method = "GET"
  path = "/health"
```

**Node-specific Fly.io gotchas**:

- **`auto_stop_machines = true` causes cold starts** on the free tier (~2-5 seconds).
  For latency-sensitive APIs, set `min_machines_running = 1`.
- **`PORT` is injected at runtime** — same as Railway. Never hardcode `3000` as the
  only binding; always fall back to `process.env.PORT`.
- **Build happens on Fly's remote builders** by default (`fly deploy --remote-only`).
  Local build (`fly deploy --local-only`) requires Docker installed and can be faster
  for large images.
- **Alpine vs Debian base**: `node:22-alpine` produces smaller images but `node:22`
  (Debian) avoids occasional glibc/musl compatibility issues with native addons
  (e.g., `sharp`, `canvas`). Default to Alpine; switch to Debian only if a native
  addon fails.

---

## Key Differences from Python Deployment

This section supplements the general skill body for teams migrating from Python.

| Concern | Python | Node/TypeScript |
|---------|--------|-----------------|
| Runtime install | `pip install -r requirements.txt` | `pnpm install --prod` |
| Dev-only flag | `pip install --no-dev` | `pnpm install --prod` (`--omit=dev`) |
| Application entry | `gunicorn main:app` | `node dist/index.js` |
| Type checking | `mypy` / `pyright` (non-emitting) | `tsc --noEmit` (separate from build) |
| Build output | `.pyc` bytecache (implicit) | `dist/` (explicit `tsc` emit) |
| Process manager | gunicorn workers | PM2 (optional); `node` directly is common |
| Signal handling | SIGTERM via gunicorn | Handle `process.on('SIGTERM', ...)` explicitly |
| Graceful shutdown | gunicorn timeout | `server.close()` + drain open connections |
