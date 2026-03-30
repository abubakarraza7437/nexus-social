# SocialOS — Complete Engineering Reference

**Version:** 2.0.0 | **Status:** Production Architecture | **Date:** 2026-03-30

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture — High Level](#2-architecture--high-level)
3. [Architecture — Low Level & Request Flow](#3-architecture--low-level--request-flow)
4. [Technology Stack — Decisions & Trade-offs](#4-technology-stack--decisions--trade-offs)
5. [Django Settings Architecture](#5-django-settings-architecture)
6. [Database Design](#6-database-design)
7. [Multi-Tenant Architecture](#7-multi-tenant-architecture)
8. [Authentication & Security](#8-authentication--security)
9. [REST API Layer](#9-rest-api-layer)
10. [Real-Time Layer — Django Channels & WebSockets](#10-real-time-layer--django-channels--websockets)
11. [Async Task System — Celery](#11-async-task-system--celery)
12. [Event Bus — Redis Streams vs Kafka](#12-event-bus--redis-streams-vs-kafka)
13. [Caching Strategy](#13-caching-strategy)
14. [Token Encryption — AES-256-GCM](#14-token-encryption--aes-256-gcm)
15. [Application Modules](#15-application-modules)
16. [Utilities — Deep Dive](#16-utilities--deep-dive)
17. [Docker & Container Architecture](#17-docker--container-architecture)
18. [Health & Observability](#18-health--observability)
19. [Development Workflow](#19-development-workflow)
20. [Scaling Guide](#20-scaling-guide)

---

## 1. System Overview

SocialOS is a **multi-tenant SaaS platform** for social media management. It allows teams (organizations) to connect social accounts (Facebook, Instagram, Twitter/X, LinkedIn), schedule and publish content, reply to messages through a unified inbox, view analytics, and use AI-powered content tools — all from one place.

### What makes this system "production-grade"

| Property | Implementation |
|---|---|
| Multi-tenancy | PostgreSQL Row-Level Security (RLS) + `app.current_org_id` session variable |
| Authentication | JWT (HS256 dev / RS256 prod) with org + role claims embedded in the token |
| Authorization | RBAC: `owner > admin > editor > viewer` enforced at the permission-class level |
| Rate limiting | Per-organization, plan-aware throttling backed by Redis |
| Async work | 7 named Celery queues, independently scalable workers |
| Real-time | Django Channels WebSockets with JWT auth, Redis channel layer |
| Data security | AES-256-GCM encryption of OAuth tokens at rest |
| Error uniformity | Every API error returns an identical `{data, meta, errors}` envelope |
| Observability | Sentry (errors + performance), structured logging, Kubernetes health probes |
| Infrastructure | Multi-stage Docker build → Gunicorn + Uvicorn (ASGI) |

---

## 2. Architecture — High Level

```
┌────────────────────────────────────────────────────────────────┐
│                        Clients                                 │
│     Next.js SPA          Mobile App        Third-party API     │
└────────────────┬───────────────────────────────────────────────┘
                 │ HTTPS  (REST + WebSocket)
                 ▼
┌────────────────────────────────┐
│         Load Balancer          │  (nginx / AWS ALB / Cloudflare)
│   - TLS termination            │
│   - WS upgrade forwarding      │
└───────────────┬────────────────┘
                │
     ┌──────────┴──────────┐
     │    Gunicorn + 4x    │   ◄─ HTTP
     │  UvicornWorker      │   ◄─ WebSocket (Channels)
     │  (ASGI process)     │
     └──────────┬──────────┘
                │
    ┌───────────┼────────────────────────────┐
    │           │                            │
    ▼           ▼                            ▼
PostgreSQL   Redis (3 DBs)           AWS S3 / CloudFront
(Primary DB)  DB0 = Celery broker     (Media files)
              DB1 = Django cache
              DB2 = Channels layer
    │
    ▼
Celery Workers (per-queue)
  publish / scheduler / ai / analytics /
  notifications / reports / audit / default

    │
    ▼
Celery Beat (single instance)
  Periodic task scheduler
  (DB-backed schedules — editable via admin)
```

**Key principle:** Every component is stateless except PostgreSQL. This means any API process can handle any request, and workers can be scaled horizontally by adding more containers.

---

## 3. Architecture — Low Level & Request Flow

### 3.1 HTTP Request Flow

```
Client → Load Balancer → Gunicorn Process → Django Middleware Stack → DRF View → Response
```

Step by step:

**Step 1 — Network**
The client sends `POST /api/v1/content/posts/` with `Authorization: Bearer <jwt>`.

**Step 2 — Gunicorn + Uvicorn**
Gunicorn receives the TCP connection and hands it to one of its `UvicornWorker` processes. Uvicorn speaks ASGI, which means it handles both HTTP and WebSocket over the same process.

**Step 3 — Django Middleware Stack** (executed in order):

```python
MIDDLEWARE = [
    "SecurityMiddleware",           # Sets security headers (HSTS, XSS, etc.)
    "WhiteNoiseMiddleware",         # Serves /static/ files without hitting Django
    "CorsMiddleware",               # Adds CORS headers (must be BEFORE SessionMiddleware)
    "SessionMiddleware",            # Enables session cookie reading
    "CommonMiddleware",             # URL normalization (trailing slashes)
    "CsrfViewMiddleware",           # CSRF token validation
    "AuthenticationMiddleware",     # Sets request.user (session-based, not JWT)
    "AxesMiddleware",               # Brute-force protection (runs after Auth)
    "MessageMiddleware",            # Flash messages
    "XFrameOptionsMiddleware",      # Clickjacking protection
    "TenantIsolationMiddleware",    # Sets PostgreSQL session variable (runs last)
    "AuditMiddleware",              # Logs every mutating request
]
```

**Why this order matters:**
- `CorsMiddleware` must be before `SessionMiddleware` because CORS preflight requests (OPTIONS) must return CORS headers even before a session is loaded.
- `AxesMiddleware` must be after `AuthenticationMiddleware` because it needs `request.user` to track failed login attempts by username.
- `TenantIsolationMiddleware` must be last because it reads `request.org`, which is only populated after DRF's JWT authentication runs (inside the view, not in middleware).

**Step 4 — DRF Authentication**
DRF calls `JWTAuthentication.authenticate()` which:
1. Reads the `Authorization: Bearer <token>` header
2. Decodes and verifies the JWT (signature + expiry)
3. Extracts `user_id` from the payload
4. Returns `(user, token)` — sets `request.user` and `request.auth`
5. The custom serializer also embedded `org` and `role` claims, so we extract those and attach `request.org` and `request.membership`

**Step 5 — TenantIsolationMiddleware.process_view()**
Called just before the view function executes. At this point `request.org` is set. The middleware runs:
```sql
SET LOCAL app.current_org_id = '<org_uuid>';
```
This is a PostgreSQL session-level variable scoped to the current transaction. All subsequent queries in this request that have RLS policies will automatically filter by `org_id`.

**Step 6 — Permission Check**
DRF checks the view's `permission_classes`. For example, `IsEditor` checks that `request.membership.role` is in `["owner", "admin", "editor"]`.

**Step 7 — Throttle Check**
`OrgPlanThrottle.allow_request()` reads `request.org.plan`, looks up the rate limit, and checks a Redis key for remaining quota.

**Step 8 — View Logic → Serializer → DB Query**
The ViewSet runs business logic, serializes data, queries the DB (all queries are RLS-filtered because `app.current_org_id` is set), and returns a `Response`.

**Step 9 — Pagination**
`StandardResultsPagination.get_paginated_response()` wraps the data in the `{data, meta, errors}` envelope.

**Step 10 — Response**
The response travels back through the middleware chain (allowing any middleware to modify the response), and Uvicorn sends it to the client.

### 3.2 WebSocket Connection Flow

```
Client → ws://host/ws/events/?token=<jwt>
       → AllowedHostsOriginValidator  (rejects foreign-origin WS)
       → JWTAuthMiddleware            (validates token, sets scope["user"])
       → AuthMiddlewareStack          (Channels default session auth)
       → URLRouter                    (matches to EventConsumer)
       → EventConsumer                (ASGI consumer)
```

### 3.3 Async Task Flow (Celery)

```
View → task.delay(org_id, post_id)
     → Redis DB0 (broker queue "publish")
     → Celery Worker (subscribed to "publish" queue)
     → Execute task (calls external social API)
     → Store result in Django DB (django-celery-results)
     → Emit WebSocket event via Channel layer
     → Client receives real-time update
```

---

## 4. Technology Stack — Decisions & Trade-offs

### 4.1 Django 5.x

**What it is:** A high-level Python web framework following the MVT pattern.

**Why chosen over FastAPI / Flask:**

| Criterion | Django | FastAPI | Flask |
|---|---|---|---|
| ORM | Built-in, mature, PostgreSQL-native | SQLAlchemy (separate) | SQLAlchemy (separate) |
| Admin panel | Built-in | None | None |
| Auth system | Built-in (extendable) | Build from scratch | Build from scratch |
| Migrations | Built-in (`makemigrations`) | Alembic (separate) | Alembic (separate) |
| Multi-tenancy | RLS + middleware | Complex to add | Complex to add |
| Ecosystem | 10+ years of battle-tested packages | Growing | Mature but smaller |

**Trade-off:** Django's synchronous ORM is the biggest limitation. For high-concurrency scenarios (10k+ concurrent connections), a pure async framework like FastAPI is faster. However, Django + ASGI (Channels) handles WebSockets, and Django 5.x has async views. For a SaaS platform where business logic complexity matters more than raw throughput, Django's ecosystem wins decisively.

**Why not FastAPI?** FastAPI is excellent for pure API services with simple schemas. SocialOS needs: admin panel (for ops team), complex multi-tenant ORM queries, Celery integration, Django Channels WebSockets, social-auth, and django-axes. Replicating all of this in FastAPI would take months and introduce more surface area for bugs.

---

### 4.2 PostgreSQL 16

**What it is:** A production-grade relational database with strong ACID guarantees.

**Why chosen over MySQL / MongoDB / DynamoDB:**

| Criterion | PostgreSQL | MySQL | MongoDB | DynamoDB |
|---|---|---|---|---|
| Row-Level Security | Native RLS policies | No | No (collection-level) | No |
| JSON support | `JSONB` (binary, indexable) | JSON (text-based) | Native document | Native |
| Array types | Native `ArrayField` | No | Native | Lists (limited) |
| Full-text search | Native `tsvector` | Limited | Atlas Search (paid) | No |
| Multi-tenancy | RLS + `SET LOCAL` | Schema-per-tenant | DB-per-tenant | Table-per-tenant |
| Concurrent reads | MVCC (no read locks) | MVCC (similar) | MVCC | Eventually consistent |

**The decisive factor: Row-Level Security (RLS)**

PostgreSQL RLS lets you define a policy at the database level that restricts which rows a user/connection can see. In SocialOS, this is implemented as:

```sql
-- Applied to every tenant table:
CREATE POLICY tenant_isolation ON posts
  USING (org_id = current_setting('app.current_org_id')::uuid);
```

When `TenantIsolationMiddleware` sets `SET LOCAL app.current_org_id = 'some-uuid'`, every `SELECT`, `UPDATE`, `DELETE` on that table automatically adds `WHERE org_id = 'some-uuid'` — even if the ORM query forgets to filter. This is a **defense-in-depth** security measure: a bug in application code cannot leak another tenant's data.

**Why not schema-per-tenant?**
Schema-per-tenant (each org gets its own PostgreSQL schema) provides stronger isolation but has crippling operational costs:
- 1,000 organizations = 1,000 schemas × N tables = potentially millions of tables
- `VACUUM`, `ANALYZE`, `pg_dump` become prohibitively expensive
- Connection pooling (PgBouncer) becomes complex because the schema must be set per connection
- Django's migration system doesn't support per-schema migrations well

The shared-table + RLS approach scales to tens of thousands of tenants.

---

### 4.3 Redis 7

**What it is:** An in-memory data structure store used as a cache, message broker, and pub/sub channel layer.

**Why it serves three roles (three separate logical databases):**

```
DB 0 → Celery broker     (task queues stored as Redis lists)
DB 1 → Django cache      (API response cache, session data)
DB 2 → Channels layer    (WebSocket group message routing)
```

Separating logical databases means a cache flush (DB 1) doesn't disturb Celery queues (DB 0), and a Channels message storm doesn't pollute the cache.

**Redis vs. alternatives for each role:**

**As a cache (DB 1):**
- Redis vs. Memcached: Redis wins because it supports data structures (sorted sets, hashes) that enable advanced caching patterns (like partial invalidation). Memcached only stores strings.

**As Celery broker (DB 0):**
- Redis vs. RabbitMQ: RabbitMQ offers more sophisticated routing, dead-letter queues, and message TTLs at the broker level. Redis is simpler to operate (one less service). For SocialOS's queue topology (named queues, no complex routing), Redis is sufficient. RabbitMQ would be the right choice if you needed complex exchange routing or per-message TTLs.

**As Channels layer (DB 2):**
- Redis is the standard backend for Django Channels. It implements a pub/sub model where `channel_layer.group_send("org_123", {...})` delivers the message to all WebSocket consumers subscribed to that group — even across multiple API server instances.

---

### 4.4 Celery 5.x

**What it is:** A distributed task queue for Python that executes background jobs asynchronously.

**Why Celery:**

SocialOS has inherently asynchronous workloads:
- Publishing a post to Twitter can take 2-10 seconds (network I/O to external API). The HTTP request from the user should not wait 10 seconds.
- AI caption generation can take 5-30 seconds (LLM inference).
- Analytics aggregation processes millions of rows — clearly not synchronous.
- Sending notifications to 10,000 org members cannot happen inline.

**Celery vs. alternatives:**

| Feature | Celery | Dramatiq | RQ (Redis Queue) | Huey |
|---|---|---|---|---|
| Queue routing | Sophisticated | Simple | Simple | Simple |
| Periodic tasks (Beat) | django-celery-beat | `apscheduler` | `rq-scheduler` | Built-in |
| Result backend | django-db, Redis, S3 | Redis, RabbitMQ | Redis | Redis, SQLite |
| Concurrency models | prefork, gevent, eventlet | threads | workers | threads, greenlets |
| Django integration | django-celery-beat + results | Manual | Manual | Manual |
| Monitoring | Flower | None | `rq-dashboard` | None |

Celery with `django-celery-beat` provides the most complete solution for a Django SaaS: periodic tasks stored in the database (editable by ops through admin), result persistence, Flower monitoring, and fine-grained queue routing.

**The 7-queue design:**

```python
CELERY_TASK_ROUTES = {
    "apps.publisher.tasks.publish_post":                 {"queue": "publish"},      # Priority 10
    "apps.scheduler.tasks.process_recurring_schedules":  {"queue": "scheduler"},    # Priority 8
    "apps.analytics.tasks.*":                            {"queue": "analytics"},    # Priority 5
    "apps.ai_engine.tasks.*":                            {"queue": "ai"},           # Priority 6
    "apps.notifications.tasks.*":                        {"queue": "notifications"},# Priority 4
    "apps.audit.tasks.*":                                {"queue": "audit"},        # Priority 1
    "apps.content.tasks.generate_report":                {"queue": "reports"},      # Priority 2
}
```

**Why separate queues?** This allows **independent scaling** of workers:
- Post publishing is time-critical (users waiting for confirmation) → many `publish` workers with high concurrency.
- Analytics aggregation is batch/nightly → few `analytics` workers.
- AI generation is GPU-bound → workers on GPU instances.
- Audit logging is low-priority fire-and-forget → few `audit` workers.

If all tasks shared one queue, a burst of analytics jobs would delay post publishing.

**Reliability settings:**
```python
CELERY_TASK_ACKS_LATE = True             # Acknowledge task AFTER completion, not on receipt
CELERY_TASK_REJECT_ON_WORKER_LOST = True # Re-queue task if worker dies mid-execution
CELERY_WORKER_PREFETCH_MULTIPLIER = 1    # Fetch one task at a time (fair distribution)
CELERY_WORKER_MAX_TASKS_PER_CHILD = 500  # Recycle worker process after 500 tasks (prevents memory leaks)
```

`ACKS_LATE = True` is critical for reliability: with the default `ACKS_EARLY`, if a worker crashes after receiving a task but before completing it, the task is lost. With `ACKS_LATE`, the message stays in the queue until the task finishes successfully.

`PREFETCH_MULTIPLIER = 1` prevents a fast worker from greedily reserving tasks that should go to other workers. Without this, one worker could hold 10 tasks while other workers sit idle.

---

### 4.5 Django Channels + Daphne

**What it is:** Django Channels extends Django to handle WebSocket connections, background tasks, and other async protocols through ASGI.

**Why WebSockets:**
SocialOS needs real-time updates:
- Post published → show "Published ✓" without user refreshing
- New inbox message → badge counter updates instantly
- Approval workflow → notify reviewer in real time

**Polling vs. WebSocket vs. SSE:**

| Approach | Latency | Server load | Complexity |
|---|---|---|---|
| HTTP polling (every 5s) | 0-5s | High (N clients × requests/s) | Low |
| Long polling | Near-real-time | Medium | Medium |
| Server-Sent Events (SSE) | Real-time | Low | Low (one-way only) |
| WebSocket | Real-time | Low | Medium |

WebSocket is chosen because SocialOS needs **bidirectional** communication (user can send messages, not just receive events). SSE would work for notifications only.

**Why Daphne before staticfiles:**
Daphne is the ASGI server that Django Channels uses internally. It must appear before `django.contrib.staticfiles` in `INSTALLED_APPS` because it overrides the `runserver` management command to run the ASGI server instead of the WSGI server. If `staticfiles` loads first, it claims the `runserver` command first.

---

### 4.6 JWT Authentication (HS256 → RS256)

**What it is:** JSON Web Tokens — a signed, self-contained authentication token.

**Two algorithms, two environments:**

| Environment | Algorithm | Key | Why |
|---|---|---|---|
| Development | HS256 (symmetric) | `SECRET_KEY` | No key pair to generate; instant setup |
| Production | RS256 (asymmetric) | Private + Public PEM | Tokens verifiable without private key |

**Why RS256 in production?**
With RS256, the private key signs tokens and the public key verifies them. This means:
- Edge proxies (Nginx, CDN, API Gateway) can verify JWTs without ever having the private key
- Microservices only need the public key to validate tokens from the auth service
- Even if a downstream service is compromised, the attacker cannot forge new tokens

With HS256, every service that needs to verify tokens must have the same secret key — compromising any service compromises all authentication.

**Custom token payload:**
```json
{
  "user_id":    "uuid",
  "exp":        1234567890,
  "jti":        "unique-id",
  "org":        "org-uuid",
  "role":       "editor",
  "name":       "John Smith",
  "email":      "john@example.com",
  "mfa_enabled": false
}
```

Embedding `org` and `role` in the JWT means **every authenticated request knows the tenant and role without a DB query.** This is the key to making RBAC fast: no `JOIN` to `organization_members` per request.

**Trade-off:** If a user's role changes (promoted from editor to admin), their existing access tokens still carry the old role until they expire (15 minutes). This is an acceptable trade-off for the performance gain. For security-critical role changes (removal from org), you would add the token's `jti` to a Redis blocklist.

---

### 4.7 drf-spectacular (OpenAPI)

**What it is:** Automatic OpenAPI 3.0 schema generation from DRF views.

```
GET /api/schema/   → raw OpenAPI YAML/JSON
GET /api/docs/     → Swagger UI (interactive)
GET /api/redoc/    → ReDoc (readable)
```

**Why not drf-yasg?** `drf-spectacular` is the maintained successor. `drf-yasg` is in maintenance mode and doesn't support OpenAPI 3.0.

**Configuration decision — `SERVE_INCLUDE_SCHEMA: False`:**
In production, the schema endpoint itself is excluded from the schema (prevents schema recursion) and the docs UI is disabled for security (don't expose API surface to anonymous internet).

---

### 4.8 python-decouple

**What it is:** Reads configuration from `.env` files and environment variables with type casting.

**Why not `os.environ` directly?**
```python
# Bad: no type casting, no default, KeyError if missing
DB_PORT = os.environ["DB_PORT"]  # Always a string

# Good: type-safe, default provided, reads .env in dev / env vars in prod
DB_PORT = config("DB_PORT", default="5432", cast=int)
```

**Why not `django-environ`?** `python-decouple` is simpler and does one thing well. `django-environ` has more features but a larger footprint.

**Critical rule:** `.env` values must not contain inline comments. python-decouple reads the raw string to the end of the line:
```ini
# WRONG — DB_CONN_MAX_AGE will be "60  # comment" and cast to int will crash
DB_CONN_MAX_AGE=60  # Persistent connection lifetime

# CORRECT
DB_CONN_MAX_AGE=60
```

---

### 4.9 django-axes (Brute Force Protection)

**What it is:** Rate-limits login attempts and locks accounts after repeated failures.

```python
AXES_FAILURE_LIMIT = 5                        # 5 failures → account locked
AXES_COOLOFF_TIME = timedelta(hours=1)        # Locked for 1 hour
AXES_RESET_ON_SUCCESS = True                  # Successful login clears failure counter
AXES_LOCKOUT_PARAMETERS = ["ip_address", "username"]  # Lock by both
```

**Why both IP and username?** Locking only by IP is bypassed by rotating IPs (botnets). Locking only by username enables a DoS attack (an attacker can lock any account by attempting 5 logins). Locking by both requires the same IP + same username to be locked — reducing false positives while maintaining protection.

**Middleware placement:**
`AxesMiddleware` must come after `AuthenticationMiddleware`. Without this, Axes cannot read `request.user` to check lock status.

`AxesStandaloneBackend` must be first in `AUTHENTICATION_BACKENDS`:
```python
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",            # Checks lock FIRST
    "django.contrib.auth.backends.ModelBackend",      # Then checks password
]
```
If ModelBackend runs first, it would verify the password before Axes can block the attempt.

---

### 4.10 WhiteNoise

**What it is:** Serves static files directly from the Django/Gunicorn process without needing Nginx.

**Why:**
- Nginx is not present in the Docker setup (the load balancer handles routing)
- WhiteNoise compresses files with Brotli/gzip and sets long-lived `Cache-Control` headers
- `CompressedManifestStaticFilesStorage` appends a content hash to filenames (`app.abc123.js`) enabling indefinite browser caching

**In production:** Static files are served by WhiteNoise from the `staticfiles/` directory (built during `collectstatic` in the Dockerfile). Media files (user uploads) go to S3 — WhiteNoise does not handle media.

---

## 5. Django Settings Architecture

### 5.1 Three-Layer Settings

```
socialos/settings/
├── __init__.py
├── base.py          ← All shared configuration
├── development.py   ← from .base import *; overrides for local dev
└── production.py    ← from .base import *; overrides for prod
```

**Why this pattern?**

The alternative (one `settings.py` with `if DEBUG:` branches everywhere) makes it impossible to guarantee that a production setting hasn't been accidentally overridden by a debug block. With separate files, `production.py` is the only truth for production — no conditional logic.

### 5.2 base.py — Key Decisions

```python
BASE_DIR = Path(__file__).resolve().parent.parent.parent
```
`__file__` is `socialos/settings/base.py`. `.parent` → `socialos/settings/`. `.parent` → `socialos/`. `.parent` → project root. `.resolve()` converts to an absolute path, handling symlinks.

```python
SECRET_KEY: str = config("DJANGO_SECRET_KEY")
```
No default — if `DJANGO_SECRET_KEY` is missing, the app fails immediately at startup. This is intentional: a missing secret key must be a hard failure, not a silent fallback to an insecure value.

```python
"CONN_MAX_AGE": 60,
"CONN_HEALTH_CHECKS": True,
"options": "-c statement_timeout=30000",  # 30 seconds
```
`CONN_MAX_AGE=60` means each Django worker maintains a persistent PostgreSQL connection for 60 seconds. This avoids the 3-way TCP handshake + PostgreSQL authentication overhead on every request. `CONN_HEALTH_CHECKS=True` pings the connection before reuse to detect stale connections. `statement_timeout=30000` kills any query running longer than 30 seconds — preventing runaway queries from holding connections or locking tables.

```python
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 500
CELERY_TASK_TIME_LIMIT = 30 * 60        # 30 min hard kill
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60   # 25 min → raises exception
```
The soft limit fires 5 minutes before the hard kill, giving the task a chance to clean up (close file handles, send partial results, log the failure). The hard limit forcibly terminates the process.

### 5.3 development.py — Key Decisions

```python
SIMPLE_JWT = {
    **SIMPLE_JWT,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "VERIFYING_KEY": None,
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),  # 1 hour vs 15 min in prod
}
```
Longer token lifetime in development avoids constant re-login during debugging.

```python
MIDDLEWARE = [
    "silk.middleware.SilkyMiddleware",  # Prepended FIRST
    *MIDDLEWARE,
]
```
Silk must be the outermost middleware to capture the complete request timing (including all other middleware overhead).

```python
DATABASES["default"]["CONN_MAX_AGE"] = 0
```
Persistent connections in development cause issues with Django's test runner (which wraps each test in a transaction). Setting to 0 means a new connection per request — safe for dev.

### 5.4 production.py — Key Decisions

```python
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31_536_000    # 1 year
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
```

`SECURE_PROXY_SSL_HEADER` is critical in containerized deployments: the load balancer terminates TLS and forwards HTTP to Django, so Django's `request.is_secure()` would return `False` without this setting. This header tells Django to trust the `X-Forwarded-Proto: https` header added by the load balancer.

> **Warning:** Only set `SECURE_PROXY_SSL_HEADER` if your load balancer is the only thing that can set this header. If clients can spoof it, they could bypass `SECURE_SSL_REDIRECT`.

```python
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
```
`default` storage (media files → `ImageField`, `FileField`) goes to S3. `staticfiles` storage (CSS, JS → `collectstatic`) stays on WhiteNoise/local. This is the Django 4.2+ `STORAGES` dict API.

```python
sentry_sdk.init(
    traces_sample_rate=0.1,   # 10% of transactions
    send_default_pii=False,   # GDPR compliance
)
```
`traces_sample_rate=0.1` captures 10% of all requests for performance profiling. Capturing 100% would double your Sentry bill. `send_default_pii=False` prevents Sentry from including user IPs, emails, or request bodies in error reports.

---

## 6. Database Design

### 6.1 Schema Overview

```
users                    (auth_core.User)
  id UUID PK
  email UNIQUE
  full_name, avatar_url
  is_active, is_staff, is_email_verified
  mfa_enabled, mfa_secret
  date_joined, last_login_at
  timezone, locale

organizations            (organizations.Organization)
  id UUID PK
  name, slug UNIQUE
  plan (free/pro/business/enterprise)
  plan_limits JSONB       ← Denormalized snapshot
  billing_customer_id    ← Stripe customer
  subscription_id        ← Stripe subscription
  is_active
  settings JSONB
  created_at, updated_at

organization_members     (organizations.OrganizationMember)
  id UUID PK
  organization_id FK → organizations
  user_id FK → users
  role (owner/admin/editor/viewer)
  is_active
  invited_by FK → users (nullable)
  joined_at
  notification_settings JSONB
  UNIQUE(organization, user)
```

### 6.2 UUID Primary Keys

**Why UUID instead of auto-increment integers?**

1. **No information leakage:** With integer PKs, a user can guess `GET /posts/1`, `GET /posts/2`, ... and enumerate all posts. With UUIDs, there's nothing to guess.
2. **No cross-tenant collision:** If post 42 exists in org A and post 42 exists in org B, and a bug causes a query without `org_id` filtering, you'd get the wrong record. With UUIDs, `a1b2c3d4-...` is globally unique.
3. **Distributed generation:** UUIDs can be generated client-side or in any service without a DB round-trip to get the next ID.

**Trade-off:** UUID primary keys use more storage (16 bytes vs 4 for int32) and UUIDs are random, causing index fragmentation over time. For SocialOS's scale, this is not a concern.

### 6.3 JSONB Fields

**`plan_limits JSONB` on Organization:**

This stores a snapshot of the plan limits at the time of plan selection:
```json
{
  "social_accounts": 10,
  "scheduled_posts_per_month": 500,
  "team_members": 3,
  "ai_credits_per_month": 200
}
```

**Why denormalize this?**
The alternative is to look up `settings.PLAN_LIMITS[org.plan]` at runtime for every limit check. If `PLAN_LIMITS` changes (plan upgrade), existing orgs automatically get new limits — which could be unexpected. Snapshotting `plan_limits` at purchase time means:
- An org that bought "Pro" with 500 posts/month keeps that limit even if you raise it to 1000 for new customers (grandfathering)
- Limit checks are a single `org.plan_limits["social_accounts"]` dict lookup — no settings import, no extra query

**`settings JSONB` on Organization:**
Org-level configuration that varies per organization (white-label branding, notification preferences, timezone, etc.) is stored in a JSONB column rather than individual columns. This avoids schema migrations every time a new setting is added.

### 6.4 Indexing Strategy

```python
indexes = [
    models.Index(fields=["email"]),                     # Login lookup
    models.Index(fields=["is_active", "is_staff"]),     # Admin queries
]
```

Composite index on `(is_active, is_staff)` serves queries like "get all active staff users" — the planner can use this index for either column or both.

```python
unique_together = [("organization", "user")]
```

A user can only be a member of an organization once. This constraint is enforced at the database level (not just application level) so concurrent requests cannot create duplicate memberships.

---

## 7. Multi-Tenant Architecture

### 7.1 The Tenancy Model

SocialOS is a **shared-database, shared-schema, row-level-security** multi-tenant application.

Three common patterns exist:

| Pattern | Isolation | Operational Cost | Scale Limit |
|---|---|---|---|
| DB per tenant | Highest | Very High (N databases) | ~1,000 tenants |
| Schema per tenant | High | High (N schemas) | ~10,000 tenants |
| Shared schema + RLS | Medium | Low | Unlimited |

SocialOS uses shared schema + RLS because it's a SaaS product targeting thousands of organizations. DB-per-tenant would require managing thousands of databases, connection pools, and migration processes.

### 7.2 How RLS Works in Practice

**The PostgreSQL policy (applied to every tenant table):**
```sql
-- Enable RLS on the table
ALTER TABLE posts ENABLE ROW LEVEL SECURITY;

-- Create the isolation policy
CREATE POLICY tenant_isolation ON posts
  USING (org_id = current_setting('app.current_org_id', true)::uuid);
```

**The session variable (`TenantIsolationMiddleware`):**
```python
def process_view(self, request, view_func, view_args, view_kwargs):
    org = getattr(request, "org", None)
    if org is not None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SET LOCAL app.current_org_id = %s",
                [str(org.id)],
            )
    return None
```

`SET LOCAL` is transaction-scoped — it resets when the transaction ends (end of request). This means:
- Request 1 (org A): sets `current_org_id = org_a_uuid` → all queries filtered to org A → transaction ends → variable resets
- Request 2 (org B): different connection, different `current_org_id`

**Why `process_view` instead of `__call__`?**
Django's middleware `__call__` runs before the view. But DRF's JWT authentication (which sets `request.org`) runs inside `perform_authentication()`, which is called lazily when the view first accesses `request.user`. By the time `__call__` runs, `request.org` doesn't exist yet.

`process_view` is a middleware hook that runs just before the view function is called, after DRF has had a chance to authenticate the request. This is the correct hook.

### 7.3 Tenant Context in JWT

```python
class CustomTokenObtainSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user) -> Token:
        token = super().get_token(user)
        membership = user.active_membership
        if membership:
            token["org"] = str(membership.organization_id)
            token["role"] = membership.role
        token["name"] = user.display_name
        return token
```

`user.active_membership` queries `OrganizationMember` for the most recent active membership. This runs once at login and the result is embedded in the token. All subsequent requests read `org` and `role` directly from the JWT — zero DB queries.

**`active_membership` property:**
```python
@property
def active_membership(self):
    return (
        self.organization_members
        .filter(is_active=True)
        .select_related("organization")  # JOIN to avoid N+1
        .order_by("-joined_at")          # Most recently joined first
        .first()
    )
```

`select_related("organization")` fetches the `Organization` row in the same query using a SQL JOIN. Without it, accessing `membership.organization` would trigger a second query (N+1 problem).

---

## 8. Authentication & Security

### 8.1 Complete Authentication Flow

```
1. User POST /api/v1/auth/token/ with {email, password}
2. AxesMiddleware checks: is this IP+email locked? → 403 if locked
3. DRF calls CustomTokenObtainSerializer.validate()
4. Serializer authenticates user (password check via ModelBackend)
5. On success: AxesMiddleware resets failure counter
6. get_token() called → embeds org, role, name, email, mfa_enabled
7. Returns {access: "...", refresh: "..."}

8. Client stores access token (memory) and refresh token (httpOnly cookie)
9. Every request: Authorization: Bearer <access_token>
10. 15 minutes later: access token expires
11. Client sends refresh token to POST /api/v1/auth/token/refresh/
12. New access + refresh pair issued (ROTATE_REFRESH_TOKENS=True)
13. Old refresh token is blacklisted (BLACKLIST_AFTER_ROTATION=True)
```

**Token rotation:** Every time a refresh token is used, it's replaced with a new one and the old one is added to the `token_blacklist` table. This means a stolen refresh token can only be used once — if the attacker uses it, the legitimate user's next refresh attempt will fail (their token is now blacklisted), alerting them to a compromise.

### 8.2 RBAC — Permission Classes

```python
class HasOrgRole(BasePermission):
    required_role: str = "viewer"
    ROLE_HIERARCHY = ["owner", "admin", "editor", "viewer"]

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        membership = getattr(request, "membership", None)
        if not membership:
            return False
        return membership.role in self._get_allowed_roles()

    def _get_allowed_roles(self) -> list[str]:
        try:
            idx = self.ROLE_HIERARCHY.index(self.required_role)
        except ValueError:
            return []
        return self.ROLE_HIERARCHY[: idx + 1]
```

`_get_allowed_roles()` for `required_role = "editor"`:
- `idx = ROLE_HIERARCHY.index("editor")` → `idx = 2`
- `ROLE_HIERARCHY[:3]` → `["owner", "admin", "editor"]`

So "is at least editor" means the role must be "owner", "admin", or "editor" — not "viewer". The hierarchy is enforced by index position, not by string comparison.

**Usage in a ViewSet:**
```python
class PostViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsEditor]   # editors+ can CRUD

    def destroy(self, request, *args, **kwargs):
        self.permission_classes = [IsAuthenticated, IsAdmin]  # only admins+ can delete
        self.check_permissions(request)
        return super().destroy(request, *args, **kwargs)
```

### 8.3 Plan-Based Rate Limiting

```python
class OrgPlanThrottle(SimpleRateThrottle):
    PLAN_RATES = {
        "free":       "100/day",
        "pro":        "10000/day",
        "business":   "50000/day",
        "enterprise": None,        # Unlimited
    }

    def get_cache_key(self, request, view) -> str | None:
        org = getattr(request, "org", None)
        if not org:
            return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
        return f"throttle_org_{org.id}"
```

**Why throttle by org, not by user?**
In a SaaS with team plans, all team members share the organization's API quota. If user A makes 8,000 API calls and user B makes 2,000, the org has used 10,000 of its 10,000 Pro quota — not 8,000 per user. Keying by `org.id` implements this correctly.

**Redis counter mechanism:**
DRF uses a Redis sorted set for each throttle key. Every request adds a timestamp to the set and removes timestamps older than the window. The number of remaining items in the set is the request count in the window.

---

## 9. REST API Layer

### 9.1 Uniform Response Envelope

Every response — success or error — uses the same structure:

```json
{
  "data":   { } ,
  "meta":   { "pagination": { } },
  "errors": []
}
```

**Why this matters for frontend teams:**
Without a uniform envelope, the frontend must handle: DRF's default `{"detail": "..."}` for auth errors, `{"field_name": ["error msg"]}` for validation errors, `{"error": "..."}` for custom errors, and `[{...}]` for list responses. Each format requires different parsing code.

With a uniform envelope, the frontend always does:
```javascript
const { data, errors } = await api.post("/content/posts/", payload);
if (errors.length) showErrors(errors);
else displayPost(data);
```

### 9.2 Custom Exception Handler

```python
def _flatten_errors(detail: Any, field: str = "non_field_errors") -> list[dict]:
```
DRF's `exc.detail` can be:
- A string: `"Not found."` → `[{"field": "non_field_errors", "message": "Not found."}]`
- A list: `["error1", "error2"]` → two items
- A dict: `{"email": ["invalid"], "password": ["too short"]}` → recursed with field names
- Nested: `{"user": {"email": ["invalid"]}}` → recursed twice

```python
if isinstance(exc, ValidationError):
    errors = _flatten_errors(exc.detail)
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
```
`422 Unprocessable Entity` is semantically more correct than `400 Bad Request` for validation failures. `400` means "malformed request" (e.g., invalid JSON). `422` means "well-formed but semantically invalid" (e.g., email already exists).

### 9.3 Pagination

```python
class StandardResultsPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"   # ?page_size=50 override
    max_page_size = 100
    page_query_param = "page"             # ?page=2
```

Response format:
```json
{
  "data": [ ],
  "meta": {
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total_count": 148,
      "total_pages": 8
    }
  },
  "errors": []
}
```

`self.page.paginator.count` runs a `SELECT COUNT(*) FROM ...` query. For very large tables, this can be expensive. For extreme scale (100M+ rows), you'd cache the count or use approximate counts (`pg_class.reltuples`).

---

## 10. Real-Time Layer — Django Channels & WebSockets

### 10.1 ASGI Application

```python
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        JWTAuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
```

`ProtocolTypeRouter` inspects `scope["type"]`:
- `"http"` → standard Django view handling
- `"websocket"` → Channels WebSocket consumer

**Security layers (inside-out):**

1. `AllowedHostsOriginValidator` — Rejects WebSocket connections from origins not in `ALLOWED_HOSTS`. Without this, a malicious website could open a WebSocket to your API from a user's browser (CSRF via WebSocket).

2. `JWTAuthMiddlewareStack` — Validates the JWT and sets `scope["user"]`.

3. `URLRouter(websocket_urlpatterns)` — Routes to the correct Consumer.

### 10.2 JWT WebSocket Authentication

```python
@database_sync_to_async
def _get_user_from_token(token_str: str) -> Any:
    try:
        token = AccessToken(token_str)       # Validates signature + expiry
        user_id = token["user_id"]
        return User.objects.get(id=user_id, is_active=True)
    except (InvalidToken, TokenError, User.DoesNotExist, KeyError):
        return AnonymousUser()
```

`@database_sync_to_async` wraps a synchronous Django ORM call in a thread pool executor, making it awaitable. Django's ORM is synchronous (blocking I/O). In an async ASGI context, you cannot call blocking operations directly — they would block the event loop.

WebSocket auth via query string (`?token=xxx`) rather than headers because:
- Browser WebSocket API (`new WebSocket(url)`) does not support custom headers
- The token is passed once at connection time; all subsequent messages are on the same authenticated connection

### 10.3 Redis Channel Layer

```python
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": ["redis://localhost:6379/2"],
            "capacity": 1500,    # Max messages per channel group before discarding
            "expiry": 10,        # Messages older than 10s are discarded
        },
    }
}
```

**How messages are delivered:**

```
Celery task (background):
  channel_layer.group_send("org_<org_id>", {"type": "post.published", "post_id": "..."})

EventConsumer (for each connected client in that org):
  async def post_published(self, event):
      await self.send_json({"type": "post.published", "data": event})
```

All EventConsumer instances subscribed to `"org_<org_id>"` receive the message via Redis pub/sub — regardless of which API server process they're running on. This is the key to horizontal scaling: add more API servers and WebSocket connections automatically distribute across them.

`capacity=1500` — If a consumer is processing messages too slowly, the channel group's backlog will fill up. At 1500 messages, new ones are discarded (back-pressure). This prevents Redis memory exhaustion.

`expiry=10` — Messages older than 10 seconds are discarded. A post-published notification that arrives 10 seconds late is no longer useful.

---

## 11. Async Task System — Celery

### 11.1 Celery Application

```python
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "socialos.settings.development")
app = Celery("socialos")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

- `setdefault` — In production containers, `DJANGO_SETTINGS_MODULE` is set in the container environment to `socialos.settings.production`, which overrides this default.
- `namespace="CELERY"` — Tells Celery to read all configuration from Django settings, but only settings prefixed with `CELERY_`. So `CELERY_BROKER_URL` in settings becomes `broker_url` in Celery config.
- `autodiscover_tasks()` — Scans every app in `INSTALLED_APPS` for a `tasks.py` module and automatically imports it.

### 11.2 Queue Topology

**Development (docker-compose):** One worker processes all 8 queues.

**Production (Kubernetes):** Dedicated worker Deployments per queue with independent replica counts:

```
publish worker:       replicas: 8   (time-critical)
scheduler worker:     replicas: 2
ai worker:            replicas: 4   (on GPU nodes via nodeSelector)
analytics worker:     replicas: 2   (nightly batch)
notifications worker: replicas: 3
reports worker:       replicas: 1
audit worker:         replicas: 1
```

### 11.3 Celery Beat (Periodic Tasks)

Beat reads schedules from the `django_celery_beat` database tables. Examples for SocialOS:
- Every minute: check for scheduled posts whose `scheduled_for <= now()` → queue publish
- Every hour: sync analytics from social platform APIs
- Every night at 2am: aggregate daily analytics, clean up old audit logs
- Every 5 minutes: process recurring content schedules

Storing schedules in the DB (vs. hardcoded in `celery.py`) means the ops team can adjust schedules without redeploying.

> **Critical:** Only one Beat instance should ever run. If two Beat instances run simultaneously, every periodic task fires twice. In Kubernetes, enforce this with `replicas: 1`.

---

## 12. Event Bus — Redis Streams vs Kafka

### 12.1 The Toggle

```python
USE_KAFKA: bool = config("USE_KAFKA", default=False, cast=bool)
```

SocialOS starts with `USE_KAFKA=False`, using Redis Streams as the event bus for inter-service communication.

### 12.2 Why Redis Streams First

| Feature | Redis Streams | Kafka |
|---|---|---|
| Persistence | Configurable (AOF + RDB) | Built-in (disk log) |
| Consumer groups | Yes | Yes |
| Message replay | Limited (memory) | Yes (configurable retention) |
| Throughput | ~100k msg/s | ~1M+ msg/s |
| Operations | Zero (already running Redis) | Kafka + ZooKeeper/KRaft cluster |
| At-exactly-once | No (at-least-once) | Yes (transactional producers) |

In early development, introducing Kafka requires a 3-broker cluster, ZooKeeper or KRaft for coordination, and Schema Registry for Avro/Protobuf schemas. This operational overhead is not justified until the platform handles millions of events per day.

### 12.3 Kafka at Scale

When `USE_KAFKA=True`, the system switches to Apache Kafka.

**Topics:**
```
socialos.posts.published          → Analytics consumer, notification consumer
socialos.posts.scheduled          → Scheduler consumer
socialos.analytics.collected      → Analytics aggregator
socialos.inbox.messages           → Inbox consumer, notification consumer
socialos.oauth.token_refreshed    → Audit consumer
```

**Partitioning by `org_id`:** All events from one organization land on the same partition, ensuring ordering. Events from different organizations go to different partitions and are processed in parallel.

**Consumer groups:**
- Group `analytics`: consumes `socialos.posts.published`, updates metrics
- Group `notifications`: consumes `socialos.posts.published`, sends in-app notifications
- Each group maintains its own offset — the same event is independently consumed by both groups

**When to switch:** When Redis Streams becomes a bottleneck (typically >500k events/day) or when you need guaranteed exactly-once delivery.

---

## 13. Caching Strategy

### 13.1 Redis Cache (DB 1)

```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://localhost:6379/1",
        "KEY_PREFIX": "socialos",   # Prevents key collisions if multiple apps share Redis
        "TIMEOUT": 300,             # 5-minute default TTL
    }
}
```

### 13.2 django-cachalot

`django-cachalot` automatically caches ORM query results and invalidates the cache when the underlying table changes.

```python
# First call hits DB; subsequent calls hit Redis until the table changes:
Organization.objects.get(id=org_id)
```

When any row in `organizations` is updated, cachalot automatically invalidates all cached queries on that table. Transparent to application code.

### 13.3 Throttle Rate Limit Counter

Redis stores a sorted set per `throttle_org_{uuid}`. Each request adds the current timestamp and removes timestamps outside the window. The cardinality of the set is the request count in the window. DRF's `SimpleRateThrottle` manages this automatically.

---

## 14. Token Encryption — AES-256-GCM

### 14.1 Why Encrypt OAuth Tokens

When a user connects their Twitter account, SocialOS stores an OAuth access token and refresh token in the database. These tokens grant SocialOS the ability to post on the user's behalf.

- **Without encryption:** A database breach gives attackers all OAuth tokens → they can post to every connected account.
- **With encryption:** A database breach gives attackers ciphertext → they cannot post without the encryption key (stored separately in environment variables / AWS Secrets Manager).

### 14.2 AES-256-GCM vs AES-256-CBC

| Property | CBC | GCM |
|---|---|---|
| Authentication | No (malleable) | Yes (AEAD) |
| Padding required | Yes (PKCS7) | No |
| Padding oracle attacks | Vulnerable | Immune |
| Parallelizable encryption | No | Yes |

GCM is **Authenticated Encryption with Associated Data (AEAD)**. The 16-byte GCM authentication tag ensures that if the ciphertext is tampered with, decryption raises `InvalidTag` immediately. CBC without a MAC is vulnerable to padding oracle attacks.

### 14.3 Implementation

**Output format (after base64 decode):** `[12 bytes nonce][N bytes ciphertext][16 bytes GCM tag]`

```python
def encrypt_token(plaintext: str) -> str:
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(_NONCE_BYTES)          # Cryptographically random 12 bytes
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()
```

`os.urandom()` reads from the OS's cryptographically secure RNG (`/dev/urandom` on Linux). Nonce reuse with the same key catastrophically breaks GCM security — never use `random.random()` for nonces.

```python
def decrypt_token(encrypted: str) -> str:
    key = _get_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(encrypted)
    nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
```

`aesgcm.decrypt()` raises `cryptography.exceptions.InvalidTag` if the ciphertext was tampered with, the nonce doesn't match, or the key is wrong. Callers must treat this exception as a security event.

---

## 15. Application Modules

### 15.1 Module Map

```
apps/
├── auth_core/       User model, JWT, RBAC, throttling, WebSocket auth
├── organizations/   Organization + Member, middleware, tenant management
├── social_accounts/ Facebook/Instagram/Twitter/LinkedIn OAuth connections
├── content/         Posts, media, approval workflows
├── scheduler/       Recurring post schedules
├── publisher/       Actual publishing to social platforms
├── analytics/       Metrics collection + aggregation
├── inbox/           Unified inbox (DMs, comments, mentions)
├── ai_engine/       AI caption/hashtag generation
├── notifications/   In-app notifications, WebSocket push
├── automation/      Rule-based automation (if X then Y)
└── audit/           Request audit log, compliance
```

### 15.2 `auth_core` — Custom User Model

```python
class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
```

- `AbstractBaseUser` provides: `password` (hashed), `last_login`, `set_password()`, `check_password()`. No `username` field.
- `PermissionsMixin` provides: `is_superuser`, `groups`, `user_permissions`.
- `USERNAME_FIELD = "email"` tells Django to use email for authentication.
- `REQUIRED_FIELDS = []` means `createsuperuser` only prompts for email and password.
- `db_table = "users"` — explicit table name. Without this, Django would use `auth_core_user`, which doesn't match Django's internal admin FK reference.

### 15.3 `organizations` — Tenant Root

`Organization.save()` auto-populates `plan_limits` from `settings.PLAN_LIMITS` whenever the plan changes:

```python
def save(self, *args, **kwargs) -> None:
    if not self.plan_limits or self._plan_changed():
        from django.conf import settings as django_settings
        self.plan_limits = django_settings.PLAN_LIMITS.get(self.plan, {})
    super().save(*args, **kwargs)
```

This deferred import (`from django.conf import settings`) inside the method avoids circular imports during app initialization.

---

## 16. Utilities — Deep Dive

### 16.1 Health Checks

**Liveness probe (`GET /health/`)** — deliberately simple. Kubernetes calls this every few seconds. Checking the database here would be wrong: a temporary DB outage would restart perfectly healthy web processes unnecessarily.

**Readiness probe (`GET /ready/`)** — Kubernetes stops sending traffic to the pod if this returns non-200. During a deployment rollout, new pods start in `NotReady` state until their readiness probe passes.

```python
checks = {
    "db":     self._check_db(),
    "redis":  self._check_redis(),
    "celery": self._check_celery(),   # Non-critical — warns but doesn't fail
}
```

Celery being down doesn't block web traffic — the pod stays ready but logs a warning. If Celery workers are temporarily restarting during a deployment, the web tier should continue serving.

---

## 17. Docker & Container Architecture

### 17.1 Multi-Stage Build

```dockerfile
FROM python:3.12-slim AS base
```

`python:3.12-slim` vs. `python:3.12-alpine`:
- `slim` is Debian-based and compatible with `psycopg2-binary` (requires `libpq`) and `cryptography` (requires `gcc`).
- `alpine` is smaller but building `cryptography` on Alpine is notoriously difficult.

**Environment variables:**
```dockerfile
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1
```

- `PYTHONDONTWRITEBYTECODE=1` — No `.pyc` files in containers (never reused between runs).
- `PYTHONUNBUFFERED=1` — Log output goes directly to stdout without buffering. Critical for container logging.
- `PYTHONFAULTHANDLER=1` — On crash (segfault), Python dumps a traceback even without a debugger.

**Layer caching:**
```dockerfile
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .   # Source code copied AFTER dependencies
```

If source code changes but `requirements.txt` doesn't, Docker reuses the cached pip install layer. Without this separation, every code change triggers a full `pip install`.

**Static files at build time:**
```dockerfile
RUN DJANGO_SETTINGS_MODULE=socialos.settings.production \
    DJANGO_SECRET_KEY=build-time-placeholder \
    python manage.py collectstatic --noinput 2>/dev/null || true
```

`collectstatic` runs at build time so the image contains pre-built static files. Placeholder secrets are used because real secrets aren't available at build time.

**Non-root user:**
```dockerfile
RUN addgroup --system socialos && adduser --system --ingroup socialos socialos
USER socialos
```

Running as non-root is a security best practice. Kubernetes enforces `runAsNonRoot: true` in pod security contexts.

### 17.2 API Stage

```dockerfile
CMD ["gunicorn", "socialos.asgi:application",
     "--worker-class", "uvicorn.workers.UvicornWorker",
     "--workers", "4",
     "--max-requests", "1000",
     "--max-requests-jitter", "100"]
```

- `UvicornWorker` — Gunicorn manages worker lifecycle; Uvicorn provides the ASGI event loop.
- `--workers 4` — Rule of thumb: `2 × CPU_cores + 1`.
- `--max-requests 1000 --max-requests-jitter 100` — Workers restart after 1000 requests (±100 random). Prevents memory leaks. Jitter prevents all workers restarting simultaneously (thundering herd).

### 17.3 Worker Stage

```dockerfile
ARG QUEUE=publish
ENV QUEUE=${QUEUE}
CMD ["sh", "-c", "celery -A socialos worker -Q ${QUEUE} --concurrency=8 --pool=gevent"]
```

`--pool=gevent` — gevent-based concurrency using greenlets. For I/O-bound tasks (HTTP calls to social APIs), gevent allows a single worker process to handle many tasks concurrently by switching between them while waiting for I/O. For CPU-bound tasks (analytics), use `--pool=prefork`.

### 17.4 Docker Compose (Development)

```yaml
api:
  command: >
    sh -c "python manage.py migrate --noinput &&
           uvicorn socialos.asgi:application --host 0.0.0.0 --port 8000
             --reload --reload-dir /app/apps --reload-dir /app/socialos"
  volumes:
    - ..:/app    # Mount source tree for hot-reload
```

**Hot reload:** The source tree is mounted into the container. `--reload` watches for file changes and restarts the server automatically — same developer experience as `runserver`.

**Service dependencies:**
```yaml
depends_on:
  db:
    condition: service_healthy
  redis:
    condition: service_healthy
```

`condition: service_healthy` waits for the PostgreSQL healthcheck (`pg_isready`) to pass before starting the API. Without health conditions, the API would start before Postgres finishes initializing.

### 17.5 Entrypoint Script

```bash
set -euo pipefail
```
- `-e`: Exit immediately if any command fails
- `-u`: Treat unset variables as errors
- `-o pipefail`: If any command in a pipe fails, the whole pipe fails

```bash
if [[ "${RUN_MIGRATIONS:-true}" == "true" ]]; then
    python manage.py migrate --noinput
fi
```

Workers (`celery worker` and `celery beat`) should not run migrations. Set `RUN_MIGRATIONS=false` in their pod specs. Only the API pod runs migrations.

---

## 18. Health & Observability

### 18.1 Sentry Integration

```python
sentry_sdk.init(
    integrations=[
        DjangoIntegration(transaction_style="url"),    # Groups errors by URL pattern
        CeleryIntegration(monitor_beat_tasks=True),    # Monitors Beat task failures
        RedisIntegration(),                            # Redis errors
    ],
    traces_sample_rate=0.1,    # 10% of transactions for performance monitoring
    send_default_pii=False,    # GDPR compliance
)
```

`transaction_style="url"` groups performance transactions by URL pattern (`/api/v1/content/posts/{id}/`) rather than the specific URL (`/api/v1/content/posts/abc123/`). Without this, each unique post ID would create a separate Sentry transaction — making trends impossible to read.

`monitor_beat_tasks=True` sends heartbeats from Celery Beat to Sentry Crons. If Beat fails to fire a task on schedule, Sentry alerts you.

### 18.2 Structured Logging

Production log format (JSON, ingested by Datadog / CloudWatch):
```json
{
  "time": "2026-03-30 12:00:00",
  "level": "ERROR",
  "logger": "apps.publisher",
  "line": 142,
  "message": "Failed to publish post to Twitter"
}
```

**Log levels per environment:**
- Development: `DEBUG` for DB queries and app logs
- Production: `WARNING` for root, `INFO` for app logs, `WARNING` for DB backends

---

## 19. Development Workflow

### 19.1 Common Commands

```bash
make install-dev      # Install all dependencies
make run              # Start Django dev server
make run-asgi         # Start Uvicorn ASGI server (for WebSocket testing)
make migrate          # Apply migrations
make test             # Run pytest
make test-cov         # Tests with coverage (must hit 80%)
make lint             # ruff linter + autofix
make type-check       # mypy
make security-check   # bandit + safety
make docker-up        # Start all services via docker-compose
make celery-worker    # Start Celery worker locally
make generate-jwt-keys # Generate RSA-2048 key pair for production JWT
```

### 19.2 Test Architecture

```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "socialos.settings.development"
asyncio_mode = "auto"           # All async tests run without @pytest.mark.asyncio
addopts = ["--strict-markers", "--tb=short", "-v"]
markers = [
    "slow: marks tests as slow",
    "integration: requires live services",
    "unit: pure unit tests (no DB, no network)",
]
```

**Test markers usage:**
```bash
pytest -m unit              # Run only unit tests (fast, no DB)
pytest -m "not slow"        # Skip slow tests
pytest -m integration       # Run only integration tests
```

**Factory Boy for test data:**
```python
class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
    email = factory.LazyAttribute(lambda _: faker.email())
    full_name = factory.Faker("name")
```

---

## 20. Scaling Guide

### 20.1 Identifying Bottlenecks

| Symptom | Diagnosis Tool | Solution |
|---|---|---|
| Slow API responses | Django Silk (dev), Sentry performance | N+1 queries → `select_related`, add indexes |
| High Celery queue depth | Flower monitoring | Increase worker `--concurrency` or add replicas |
| Redis memory growing | `redis-cli INFO memory` | Add TTLs, increase `maxmemory`, use LRU eviction |
| DB connection exhaustion | PostgreSQL `pg_stat_activity` | Add PgBouncer connection pooler |

### 20.2 Horizontal Scaling

**API layer:** Stateless — add more API containers behind the load balancer. All state is in PostgreSQL and Redis.

**WebSockets:** All API containers share the same Redis channel layer (DB 2). A WebSocket connection to API container 1 can receive a message sent from API container 2, because both send/receive via Redis pub/sub.

**Celery workers:** Each queue has independently scaled worker Deployments:
```
publish workers:    scale up during peak publishing hours
analytics workers:  scale up nightly for batch jobs, scale to 0 overnight
ai workers:         scale based on AI credit usage metrics
```

**Database:** Add PostgreSQL read replicas for analytics queries. Configure `DATABASES["analytics"]` routing to send read-heavy analytics queries to the replica.

### 20.3 Kafka Migration Path

When `USE_KAFKA=True`:
1. Social platform API responses are published to Kafka topics instead of directly triggering Celery tasks
2. Consumer groups independently consume topics and fan-out to analytics, notifications, audit
3. Event replay becomes possible: replay missed events during a consumer downtime
4. Topics can be consumed by future microservices without modifying the publisher

**Migration threshold:** Switch when Redis Streams becomes a bottleneck (typically >500k events/day) or when you need guaranteed exactly-once delivery.

### 20.4 Multi-Region Deployment

```
us-east-1:   PostgreSQL primary + Redis primary + API cluster
eu-west-1:   PostgreSQL read replica + Redis cluster + API cluster
ap-southeast-1: PostgreSQL read replica + Redis cluster + API cluster
```

- Cloudflare / AWS Route 53 routes users to the nearest region
- Write operations (POST/PUT/DELETE) go to primary region's DB
- Read operations serve from local replica
- Celery publish tasks are regional (social API calls go to local edge)
- Analytics aggregation runs nightly against the primary DB

---

## Appendix A — Environment Variables Reference

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | Yes | — | Django signing key |
| `DJANGO_ENV` | Yes | `development` | Settings module selector |
| `DEBUG` | No | `False` | Debug mode (never True in prod) |
| `DB_NAME` | Yes | `socialos` | PostgreSQL database name |
| `DB_USER` | Yes | `socialos` | PostgreSQL user |
| `DB_PASSWORD` | Yes | — | PostgreSQL password |
| `DB_HOST` | Yes | `localhost` | PostgreSQL host |
| `DB_PORT` | No | `5432` | PostgreSQL port |
| `DB_CONN_MAX_AGE` | No | `60` | Persistent connection lifetime (seconds) |
| `REDIS_URL` | Yes | `redis://localhost:6379/0` | Celery broker |
| `REDIS_CACHE_URL` | Yes | `redis://localhost:6379/1` | Django cache |
| `REDIS_CHANNEL_URL` | Yes | `redis://localhost:6379/2` | Channels layer |
| `JWT_PRIVATE_KEY` | Prod only | — | RS256 signing key |
| `JWT_PUBLIC_KEY` | Prod only | — | RS256 verification key |
| `TOKEN_ENCRYPTION_KEY` | Yes | — | AES-256-GCM key (64 hex chars) |
| `AWS_ACCESS_KEY_ID` | Prod only | — | S3 access |
| `AWS_SECRET_ACCESS_KEY` | Prod only | — | S3 secret |
| `AWS_STORAGE_BUCKET_NAME` | Prod only | `socialos-media` | S3 bucket |
| `AWS_CLOUDFRONT_DOMAIN` | No | — | CDN domain for media |
| `SENTRY_DSN` | Prod only | — | Error tracking |
| `STRIPE_SECRET_KEY` | Yes | — | Billing |
| `STRIPE_WEBHOOK_SECRET` | Yes | — | Stripe webhook validation |
| `OPENAI_API_KEY` | No | — | AI caption generation |
| `ANTHROPIC_API_KEY` | No | — | AI caption generation |
| `USE_KAFKA` | No | `False` | Redis Streams vs Kafka |
| `KAFKA_BOOTSTRAP_SERVERS` | If Kafka | `localhost:9092` | Kafka brokers |
| `CELERY_TASK_ALWAYS_EAGER` | No | `False` | Run tasks synchronously (tests) |

---

## Appendix B — Architectural Decision Record (ADR)

| Decision | Choice | Rejected Alternatives | Reason |
|---|---|---|---|
| Framework | Django 5 | FastAPI, Flask | Ecosystem (admin, auth, migrations, ORM) |
| ORM | Django ORM | SQLAlchemy | Native Django integration, RLS support |
| Database | PostgreSQL 16 | MySQL, MongoDB | Native RLS, JSONB, Arrays, MVCC |
| Multi-tenancy | Shared schema + RLS | Schema-per-tenant, DB-per-tenant | Operational scale |
| Auth tokens | JWT (RS256 prod) | Session + Cookie, OAuth-only | Stateless, embeddable claims, microservice-ready |
| Refresh token storage | HttpOnly cookie | localStorage | XSS resistance |
| Task queue | Celery + Redis | RQ, Dramatiq, Huey | Beat scheduler, Django integration, Flower |
| Queue routing | 7 named queues | Single queue | Independent worker scaling |
| Real-time | Django Channels | Polling, SSE, Socket.io | Bidirectional, scalable, Django-native |
| Channel layer | Redis pub/sub | In-memory, RabbitMQ | Multi-instance distribution |
| Token encryption | AES-256-GCM | AES-256-CBC, Fernet | Authenticated encryption, no padding oracle |
| Event bus (early) | Redis Streams | Kafka | Zero operational overhead |
| Event bus (scale) | Kafka | Redis | Replay, partitioning, throughput, exactly-once |
| Container base | `python:3.12-slim` | `python:3.12-alpine` | C extension compatibility (cryptography, psycopg2) |
| Container build | Multi-stage Dockerfile | Single stage | Image size, security (non-root), separation of concerns |
| Config management | python-decouple | django-environ, os.environ | Type-safe, dev/prod parity, clean `.env` format |
| Error format | Uniform `{data, meta, errors}` | Default DRF format | Frontend simplicity, consistent parsing |
| Static files | WhiteNoise | Nginx sidecar | Simpler ops (no extra container), Brotli compression |
| Media files | AWS S3 + CloudFront | Local disk | Scalability, CDN edge delivery |

---

*This document covers Sections 1 and 2 of the SocialOS build: Project Initialization and Docker Setup. Each subsequent section (social accounts, content, scheduling, publishing, analytics, inbox, AI, notifications, automation, audit) follows the same architectural patterns established here.*
