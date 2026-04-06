# Framework Signatures

Recognition patterns for common frameworks organized by language ecosystem. Each entry provides detection signals, key files to read first, typical architecture pattern, and directory layout. Back-reference: [../SKILL.md](../SKILL.md)

## Python

### Django

- **Detection**: `django` in dependencies, `settings.py` or `DJANGO_SETTINGS_MODULE`, `urls.py`, `manage.py`
- **Key files**: `settings.py` (config), `urls.py` (routing), `models.py` (data layer), `views.py` (handlers)
- **Architecture**: MTV (Model-Template-View), similar to MVC
- **Layout**: `project/settings.py`, `app_name/models.py`, `app_name/views.py`, `app_name/urls.py`, `templates/`
- **What to investigate**: URL routing tree, installed apps list, middleware stack, database backends, REST framework if present (DRF)

### FastAPI

- **Detection**: `fastapi` in dependencies, `app = FastAPI()` pattern, `uvicorn` in run config
- **Key files**: `main.py` or `app.py` (app factory), `routers/` (endpoint groups), `models.py` or `schemas.py` (Pydantic models)
- **Architecture**: Async-first REST API, router-based organization
- **Layout**: `app/main.py`, `app/routers/`, `app/models/`, `app/dependencies.py`
- **What to investigate**: Router structure, dependency injection, Pydantic models, middleware, OpenAPI config

### Flask

- **Detection**: `flask` in dependencies, `Flask(__name__)` pattern, `@app.route` decorators
- **Key files**: `app.py` or `__init__.py` with Flask app factory, `routes/` or view files
- **Architecture**: Microframework, blueprint-based modularization
- **Layout**: `app/__init__.py`, `app/routes/`, `app/models.py`, `templates/`
- **What to investigate**: Blueprint registration, extensions used, template engine, database integration

### Streamlit

- **Detection**: `streamlit` in dependencies, `st.` calls, `streamlit run` in scripts
- **Key files**: `app.py` or `Home.py`, `pages/` directory for multi-page apps
- **Architecture**: Script-based UI, top-to-bottom execution model
- **Layout**: `app.py`, `pages/*.py`, `utils/`, `data/`
- **What to investigate**: Page structure, state management (`st.session_state`), data loading patterns, caching

## JavaScript / TypeScript

### React

- **Detection**: `react` in package.json dependencies, `jsx`/`tsx` files, `src/App.tsx`
- **Key files**: `src/App.tsx` (root component), `src/index.tsx` (entry point), `src/components/`
- **Architecture**: Component tree, unidirectional data flow
- **Layout**: `src/components/`, `src/hooks/`, `src/pages/`, `src/store/`, `src/utils/`
- **What to investigate**: State management (Redux, Zustand, Context), routing (React Router), data fetching (React Query, SWR), component hierarchy

### Next.js

- **Detection**: `next` in dependencies, `next.config.*` at root, `pages/` or `app/` directory
- **Key files**: `next.config.js` (config), `app/layout.tsx` or `pages/_app.tsx` (root), `middleware.ts`
- **Architecture**: File-based routing, SSR/SSG/ISR rendering strategies
- **Layout (App Router)**: `app/`, `app/layout.tsx`, `app/page.tsx`, `app/api/` (route handlers)
- **Layout (Pages Router)**: `pages/`, `pages/_app.tsx`, `pages/api/` (API routes)
- **What to investigate**: Routing convention (App vs Pages), rendering strategy per route, API routes, middleware, data fetching

### Express

- **Detection**: `express` in dependencies, `app.listen(` pattern, `app.use(` middleware chain
- **Key files**: `app.js`/`server.js` (entry), `routes/` (route definitions), `middleware/`
- **Architecture**: Middleware pipeline, router-based
- **Layout**: `src/routes/`, `src/middleware/`, `src/controllers/`, `src/models/`
- **What to investigate**: Middleware stack order, route organization, error handling middleware, template engine if any

### Nest.js

- **Detection**: `@nestjs/core` in dependencies, `@Module()` decorators, `main.ts` with `NestFactory`
- **Key files**: `src/main.ts` (bootstrap), `src/app.module.ts` (root module), `*.module.ts`, `*.controller.ts`, `*.service.ts`
- **Architecture**: Module-based, dependency injection, decorator-driven (Angular-inspired)
- **Layout**: `src/module-name/module-name.module.ts`, `src/module-name/module-name.controller.ts`, `src/module-name/module-name.service.ts`
- **What to investigate**: Module hierarchy, providers/services, guards, interceptors, pipes

## Rust

### Actix-web

- **Detection**: `actix-web` in Cargo.toml, `HttpServer::new` pattern, `#[actix_web::main]`
- **Key files**: `src/main.rs` (server setup), `src/routes/` or `src/handlers/`
- **Architecture**: Actor-based async web framework
- **Layout**: `src/main.rs`, `src/routes.rs`, `src/handlers/`, `src/models/`, `src/middleware/`
- **What to investigate**: Route configuration, extractors, middleware, error handling, state management

### Axum

- **Detection**: `axum` in Cargo.toml, `Router::new()` pattern, `tokio::main`
- **Key files**: `src/main.rs` (router setup), `src/routes/`, `src/handlers/`
- **Architecture**: Tower-based, type-safe routing
- **Layout**: `src/main.rs`, `src/routes/`, `src/extractors/`, `src/models/`
- **What to investigate**: Router nesting, extractors, layers/middleware, shared state pattern

### Tokio (async runtime)

- **Detection**: `tokio` in Cargo.toml, `#[tokio::main]`, `tokio::spawn`
- **Key files**: `src/main.rs`, any file with `async fn` and `.await`
- **Architecture**: Async runtime -- usually paired with a framework above
- **What to investigate**: Task spawning patterns, channel usage, synchronization primitives

## Go

### Standard Library HTTP

- **Detection**: `net/http` imports, `http.ListenAndServe`, `http.HandleFunc`
- **Key files**: `main.go`, `cmd/*/main.go`, `internal/handler/`
- **Architecture**: Handler-based, standard library patterns
- **Layout**: `cmd/`, `internal/`, `pkg/` (Go project layout convention)
- **What to investigate**: Handler registration, middleware chain, internal vs pkg boundary

### Gin

- **Detection**: `github.com/gin-gonic/gin` in go.mod, `gin.Default()`, `r.GET(`
- **Key files**: `main.go`, `routes/`, `handlers/`, `middleware/`
- **Architecture**: Express-like middleware pipeline
- **What to investigate**: Route groups, middleware, binding/validation, error handling

### Echo / Fiber

- **Detection**: `github.com/labstack/echo` or `github.com/gofiber/fiber` in go.mod
- **Key files**: Same patterns as Gin -- `main.go`, `routes/`, `handlers/`
- **What to investigate**: Similar to Gin but check framework-specific middleware and context patterns

## Java / Kotlin

### Spring Boot

- **Detection**: `spring-boot-starter` in pom.xml/build.gradle, `@SpringBootApplication`, `application.properties`/`application.yml`
- **Key files**: `*Application.java` (main class), `application.yml`, `*Controller.java`, `*Service.java`, `*Repository.java`
- **Architecture**: Layered (Controller-Service-Repository), annotation-driven DI
- **Layout**: `src/main/java/com/company/project/controller/`, `service/`, `repository/`, `model/`, `config/`
- **What to investigate**: Annotation-based config, Spring profiles, security config, JPA entities, Actuator endpoints

### Quarkus

- **Detection**: `quarkus` in pom.xml/build.gradle, `@ApplicationScoped`, `application.properties` with `quarkus.*`
- **Key files**: `*Resource.java` (JAX-RS endpoints), `application.properties`
- **Architecture**: Microservice-optimized, CDI-based DI, native compilation support
- **What to investigate**: Extensions used, dev services, reactive vs imperative, native build config

## Ruby

### Rails

- **Detection**: `Gemfile` with `rails`, `config/routes.rb`, `app/` with `controllers/`, `models/`, `views/`
- **Key files**: `config/routes.rb` (routing), `app/models/` (Active Record), `app/controllers/`, `db/schema.rb`
- **Architecture**: MVC with convention-over-configuration
- **Layout**: `app/controllers/`, `app/models/`, `app/views/`, `config/`, `db/`, `lib/`, `spec/`/`test/`
- **What to investigate**: Route definitions, model associations, concerns, service objects pattern, test framework (RSpec vs Minitest)
