# MediSlot

A clinic appointment booking platform built to stay correct when many patients book at the same moment.

When a popular doctor opens up slots, dozens of patients may tap the same time within the same second, and a flaky mobile connection may send the same request twice. MediSlot guarantees that a slot is **never double-booked** and a booking is **never lost or duplicated**, while staying fast under load. Each booking locks the slot row in PostgreSQL (`SELECT ... FOR UPDATE`) inside a transaction, a partial unique index acts as a second safety net, idempotency keys make retries safe, and anything slow (emails, SMS, reminders) is pushed to a Celery queue so the booking request returns immediately. Patients search and book, doctors manage their week, and admins manage clinics and see statistics.

## Architecture

```mermaid
flowchart LR
    Browser["React app<br/>(Vite + Tailwind)"] -->|HTTPS| HostNginx["Nginx on host<br/>TLS, Let's Encrypt"]
    HostNginx --> FrontNginx["Nginx container<br/>static files + /api proxy"]
    FrontNginx -->|/api| API["FastAPI<br/>(uvicorn)"]

    API -->|transactions, row locks| PG[(PostgreSQL 16)]
    API -->|slot cache, rate limits| Redis[(Redis 7)]
    API -->|enqueue notification ids| Redis

    Beat["Celery Beat<br/>nightly slots, reminders,<br/>key cleanup"] --> Redis
    Redis --> Worker["Celery worker"]
    Worker --> PG
    Worker -->|SMTP| Mail["Mailpit (dev) /<br/>SMTP provider (prod)"]
    Worker -->|pluggable| SMS["SMS sender<br/>(logs in dev)"]

    Prometheus["Prometheus"] -->|scrape /metrics| API
    Grafana["Grafana dashboard"] --> Prometheus
```

### How one booking flows

```mermaid
sequenceDiagram
    participant P as Patient app
    participant A as API
    participant DB as PostgreSQL
    participant Q as Redis queue
    P->>A: POST /api/bookings (Idempotency-Key: uuid)
    A->>DB: key seen before? (return saved response if yes)
    A->>DB: BEGIN; SELECT slot FOR UPDATE
    Note over A,DB: other requests for this slot wait here
    A->>DB: slot available? insert booking, mark slot booked,<br/>save idempotency key + response
    A->>DB: COMMIT
    A->>Q: enqueue confirmation email + SMS
    A-->>P: 201 Created (or 409 "slot was just booked")
```

## Key design decisions

**Why row locking (pessimistic) for booking.** A slot is a single hot row that many requests fight over. `SELECT ... FOR UPDATE` makes the second request wait until the first commits, then it sees the slot as booked and gets a clean `409`. The alternative, optimistic locking with a version column, never blocks but makes every loser retry or fail after doing the work; it is the better choice when conflicts are rare (for example editing a doctor's profile). As a second line of defence, a partial unique index (`UNIQUE (slot_id) WHERE status = 'confirmed'`) means the database itself refuses a second confirmed booking even if some future code path forgets to lock.

**Why reschedule locks in a fixed order.** Reschedule touches two slots in one transaction. If two patients swap slots A and B at the same time and each locks "its own" slot first, they wait for each other forever (a deadlock). Every transaction locks the booking first, then slots in increasing id order, so one simply waits for the other.

**Why idempotency keys.** If a phone loses signal after sending "book", the app cannot know whether it worked, so it retries. The app sends the same `Idempotency-Key` for every retry of one attempt; the server stores the response under that key *in the same transaction as the booking*, so a retry, even one arriving in parallel, gets the original response instead of a second booking. Keys are deleted after 24 hours by a scheduled job.

**Why a queue for notifications.** Sending an email can take seconds or fail. The booking request only writes notification rows and pushes their ids to Celery, then returns. The worker sends them, retries up to 3 times with exponential backoff (30s, 60s, 120s) and records every attempt. A unique constraint on (booking, type, channel) stops a reminder job that runs twice from sending twice.

**Why cache-aside for free slots.** Viewing free slots is far more common than booking. The list for one doctor and day is cached in Redis for 60 seconds and deleted whenever a slot on that day changes (book, cancel, reschedule, block). Booking never trusts the cache: it always locks and checks the real row, so the worst a stale cache can do is show a slot that then returns `409`. If Redis is down, reads fall back to PostgreSQL.

**Why a hand-written fixed-window rate limiter.** 5 booking attempts per minute per patient and 10 logins per minute per IP, using one Redis `INCR` + `EXPIRE` per request. A fixed window can let up to twice the limit through around a window boundary; a sliding window (sorted set of timestamps) would fix that at the cost of more memory.

**What load testing taught me.** The first runs through Nginx froze the API completely: PostgreSQL showed 40 connections "idle in transaction" forever. Starlette's `BaseHTTPMiddleware` cancels a request when the client disconnects (Nginx times out after 60s), and a cancelled request could leave its session behind in a worker thread. The request-id middleware was rewritten as a plain ASGI middleware, the login path now returns its database connection before the slow bcrypt check, and a small middleware caps in-flight requests at the size of the database pool so a burst queues cheaply instead of exhausting connections.

**What I would change at 100x the traffic.**
- Move the API to several instances behind a load balancer, with PgBouncer in front of PostgreSQL.
- Use a managed PostgreSQL with read replicas for search and slot listing; keep booking on the primary.
- Switch the rate limiter to a sliding window, and add per-doctor queueing for "flash" slot releases.
- Partition the `slots` and `bookings` tables by month, and archive old rows.
- Replace polling reminders with a scheduled queue (delayed messages) and move to a dedicated broker (RabbitMQ or SQS).
- Distributed tracing (OpenTelemetry) on top of the request ids.

## Tech stack

| Area | Tools |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2.0, Alembic |
| Data | PostgreSQL 16, Redis 7 |
| Background jobs | Celery + Celery Beat (Redis broker), Mailpit for development email |
| Auth | bcrypt password hashing, JWT access (30 min) and refresh (7 day) tokens |
| Observability | JSON logs with request ids, Prometheus metrics, provisioned Grafana dashboard |
| Frontend | React 18, Vite, Tailwind CSS, React Router |
| Testing | pytest, httpx, coverage, Locust |
| Delivery | Docker Compose, GitHub Actions, AWS EC2 + Nginx + Let's Encrypt |

## Running it

Requirements: Docker with Docker Compose.

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec api python -m app.seed
```

| What | Where |
|---|---|
| Web app | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Emails sent by the app (Mailpit) | http://localhost:8025 |
| Grafana dashboard (admin / value in `.env`) | http://localhost:3001 |
| Prometheus | http://localhost:9090 |

### Demo logins

The seed script creates 3 clinics, 10 doctors, 50 patients, 14 days of slots and two weeks of booking history. Every demo account uses the password `Demo@1234`.

| Role | Email |
|---|---|
| Patient | `patient@medislot.dev` |
| Doctor | `doctor@medislot.dev` |
| Admin | `admin@medislot.dev` |

### Running without Docker (for development)

```bash
# Backend (needs PostgreSQL and Redis running locally)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/medislot
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload

# Worker and scheduler, in two more terminals
celery -A app.workers.celery_app worker --loglevel=info
celery -A app.workers.celery_app beat --loglevel=info

# Frontend (proxies /api to localhost:8000)
cd frontend
npm install
npm run dev
```

## Tests

The tests run against a real PostgreSQL and Redis (a separate `medislot_test` database), because the guarantees this project cares about (row locks, the partial unique index, `ON CONFLICT`) only exist in the real database.

```bash
cd backend
createdb medislot_test            # once
pytest                            # all tests
pytest --cov --cov-report=html    # coverage report in backend/htmlcov/index.html
```

Latest run: **124 tests passed, 98% line coverage.**

| Test | What it proves | Result |
|---|---|---|
| `test_100_simultaneous_bookings_for_one_slot` | 100 threads book the same slot at the same instant through a live uvicorn server | exactly 1 × `201`, 99 × `409`, 1 confirmed booking in the database |
| `test_same_key_sent_in_parallel_creates_one_booking` | 5 parallel requests with one `Idempotency-Key` | all 5 get the same `201` response, 1 booking |
| `test_same_key_five_times_creates_one_booking` | 5 sequential retries | 1 booking, replays marked `Idempotent-Replayed: true` |
| `test_patient_always_has_exactly_one_booking_across_many_reschedules` | repeated reschedules, and a failed one | patient always has exactly 1 confirmed booking |
| `test_partial_unique_index_blocks_second_confirmed_booking` | the database safety net on its own | second confirmed booking rejected by PostgreSQL |
| `test_task_retries_three_times_then_marks_failed` | email delivery failing | 4 attempts recorded, then marked `failed` |

## Load test

`load_tests/locustfile.py` simulates patients who log in, search doctors, look at free slots, book (with an idempotency key), check their appointments and sometimes cancel, waiting 1 to 3 seconds between actions.

```bash
pip install -r load_tests/requirements.txt
# Logins are limited to 10/minute per IP; every simulated user logs in from the same machine,
# so raise that limit for the test run: add LOGIN_RATE_LIMIT_PER_MINUTE=1000 to .env and restart the api.
locust -f load_tests/locustfile.py --host http://localhost:3000 --headless -u 100 -r 5 -t 120s
```

Results through the full Docker Compose stack (Nginx → FastAPI with one uvicorn process → PostgreSQL/Redis), with all nine containers **and** Locust sharing a single 2 vCPU, 8 GB machine:

| Simulated patients | Requests/s | p50 | p95 | p99 | Error rate |
|---|---|---|---|---|---|
| 100 (2 min) | 46 | 14 ms | 54 ms | 830 ms | 0% (5,481 requests) |
| 300 (3 min) | 107 | 120 ms | 1.3 s | 14 s | 0% (19,255 requests) |

At 100 users, slot listing has a p95 of 32 ms and booking a p95 of 100 ms. At 300 users the machine is CPU-bound: 300 logins hash passwords with bcrypt in the first 30 seconds, and that burst is what pushes up the p99. `409` (slot just taken) and `429` (rate limited) responses are counted as correct outcomes, not errors.

## Screenshots

> **Screenshot placeholder:** doctor search (`docs/screenshots/search.png`)

> **Screenshot placeholder:** doctor profile with free times (`docs/screenshots/doctor-profile.png`)

> **Screenshot placeholder:** booking confirmed (`docs/screenshots/booking-confirmed.png`)

> **Screenshot placeholder:** doctor dashboard (`docs/screenshots/doctor-dashboard.png`)

> **Screenshot placeholder:** admin dashboard (`docs/screenshots/admin-dashboard.png`)

> **Screenshot placeholder:** Grafana dashboard during the load test (`docs/screenshots/grafana.png`)

## API overview

Full interactive documentation is at `/docs` when the API is running.

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/refresh`, `GET /api/auth/me` |
| Search (public) | `GET /api/doctors?specialty=&city=&date=`, `GET /api/doctors/filters`, `GET /api/doctors/{id}`, `GET /api/doctors/{id}/slots?date=` |
| Patient | `POST /api/bookings`, `GET /api/bookings/me?scope=upcoming\|past`, `GET /api/bookings/{id}`, `POST /api/bookings/{id}/cancel`, `POST /api/bookings/{id}/reschedule` |
| Doctor | `GET /api/doctor/me`, `GET\|PUT /api/doctor/schedule`, `GET /api/doctor/slots?date=`, `POST /api/doctor/slots/{id}/block\|unblock`, `POST /api/doctor/block-day`, `GET /api/doctor/appointments?scope=today\|upcoming`, `PATCH /api/doctor/appointments/{id}` |
| Admin | `GET\|POST /api/admin/clinics`, `PATCH /api/admin/clinics/{id}`, `POST /api/admin/clinics/{id}/deactivate`, the same for `/api/admin/doctors`, `GET /api/admin/stats?days=`, `POST /api/admin/slots/generate` |
| Operations | `GET /health`, `GET /ready`, `GET /metrics` |

Every error has the same shape:

```json
{"error": {"code": "SLOT_ALREADY_BOOKED", "message": "Sorry, this slot was just booked. Please choose another slot."}}
```

## Project layout

```
medislot/
  backend/
    app/
      api/          route files, kept thin: read the request, call a service, return the response
      core/         settings, database, security, errors, logging, rate limiter, middleware
      models/       SQLAlchemy tables
      schemas/      Pydantic request and response shapes
      services/     business rules: booking, scheduling, slots, notifications, stats
      workers/      Celery app and tasks
      main.py
      seed.py       demo data
    alembic/        database migrations
    tests/
  frontend/         React app (served by Nginx in production)
  load_tests/       Locust script
  monitoring/       Prometheus config and the Grafana dashboard
  deploy/           host Nginx config
  docs/             deployment guide
  .github/workflows CI
```

## Deployment

See [docs/deployment.md](docs/deployment.md) for running it on a single AWS EC2 server with Nginx and a free Let's Encrypt certificate. CI (GitHub Actions) runs ruff, the full test suite including the concurrency test against real PostgreSQL and Redis services, the frontend build and the Docker image builds on every push.

## Future improvements

- Waitlist: notify patients when a slot on a full day is freed by a cancellation.
- Real SMS provider (e.g. MSG91 or Twilio) behind the existing `SmsSender` interface.
- Online payment of the consultation fee, with a short hold on the slot during checkout.
- Refresh token rotation with a server-side revocation list, and refresh tokens in httpOnly cookies.
- Video consultations and digital prescriptions.
- Frontend tests (Vitest + React Testing Library) and end-to-end tests (Playwright).
