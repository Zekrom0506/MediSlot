# MediSlot

A clinic appointment booking platform built to stay correct when many patients book at the same moment.

When a popular doctor opens up slots, dozens of patients may tap the same time within the same second, and a flaky mobile connection may send the same request twice. MediSlot guarantees that a slot is **never double-booked** and a booking is **never lost or duplicated**, while staying fast under load. Each booking locks the slot row in PostgreSQL (`SELECT ... FOR UPDATE`) inside a transaction, a partial unique index acts as a second safety net, idempotency keys make retries safe, a database exclusion constraint makes overlapping slots impossible, and anything slow (confirmation, cancellation and reminder emails) is pushed to a Celery queue so the booking request returns immediately. Patients search and book, doctors manage their week, and admins manage clinics and see statistics.

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
    A->>DB: BEGIN; lock patient row, doctor row (KEY SHARE), SELECT slot FOR UPDATE
    Note over A,DB: other requests for this slot wait here
    A->>DB: slot available? patient within limits?<br/>insert booking, mark slot booked,<br/>save idempotency key + response
    A->>DB: COMMIT
    A->>Q: enqueue confirmation email
    A-->>P: 201 Created (or 409 "slot was just booked")
```

## Key design decisions

**Why row locking (pessimistic) for booking.** A slot is a single hot row that many requests fight over. `SELECT ... FOR UPDATE` makes the second request wait until the first commits, then it sees the slot as booked and gets a clean `409`. The alternative, optimistic locking with a version column, never blocks but makes every loser retry or fail after doing the work; it is the better choice when conflicts are rare (for example editing a doctor's profile). As a second line of defence, a partial unique index (`UNIQUE (slot_id) WHERE status = 'confirmed'`) means the database itself refuses a second confirmed booking even if some future code path forgets to lock.

**Why every change locks rows in one fixed order.** Reschedule touches two slots in one transaction. If two patients swap slots A and B at the same time and each locks "its own" slot first, they wait for each other forever (a deadlock). So every transaction locks rows in the same order, skipping the ones it does not need: the patient's user row, then the doctor row, then bookings, then slots, each in increasing id order. One transaction simply waits for the other. The load test produces no deadlocks.

**Why the patient's own row is locked.** Each patient can have one upcoming appointment per doctor, no two appointments at overlapping times, and at most 5 upcoming appointments, so one account cannot fill a doctor's week. Checking these rules is a read, and five parallel requests would all read "no booking yet" before any of them commits. Locking the patient's row first makes one patient's bookings go one at a time; different patients still book in parallel. `test_parallel_requests_from_one_patient_cannot_beat_the_limits` fires five requests at once: without the lock 4 or 5 of them succeeded, with it exactly one does.

**Why the database refuses overlapping slots.** Slots are generated from the weekly schedule and the doctor's visit length. If an admin changes the length from 20 to 30 minutes, new 30 minute slots could overlap old 20 minute ones that are already booked, and the same doctor would be booked twice at once. An exclusion constraint (`EXCLUDE USING gist (doctor_id WITH =, tstzrange(start_time, end_time) WITH &&)`, with the `btree_gist` extension) makes PostgreSQL itself refuse two overlapping live slots for one doctor. The nightly generator inserts with `ON CONFLICT DO NOTHING`, so it skips anything that would overlap, and is still safe to run any number of times. Slots that are taken out of use but have booking history are marked `retired` and leave the constraint.

**What happens when the clinic cancels.** A doctor can cancel an upcoming appointment (for example when ill); the slot is blocked, not freed, and the patient is emailed. Deactivating a doctor or a clinic cancels their upcoming appointments the same way. Bookings hold a shared `FOR KEY SHARE` lock on the doctor row and deactivation takes `FOR UPDATE`, so a booking can never slip in while a doctor's appointments are being cancelled, and ordinary profile edits still never wait for bookings. The patient sees "Cancelled by the clinic", and a reschedule is stored as `rescheduled`, not `cancelled`, so the admin statistics count a moved appointment once.

**Why idempotency keys.** If a phone loses signal after sending "book", the app cannot know whether it worked, so it retries. The app sends the same `Idempotency-Key` for every retry of one attempt; the server stores the response under that key *in the same transaction as the booking*, so a retry, even one arriving in parallel, gets the original response instead of a second booking. Keys are deleted after 24 hours by a scheduled job.

**Why a queue for notifications.** Sending an email can take seconds or fail. The booking request only writes notification rows and pushes their ids to Celery, then returns. The worker sends them, retries up to 3 times with exponential backoff (30s, 60s, 120s) and records every attempt. A unique constraint on (booking, type) stops a reminder job that runs twice from sending twice.

**Why cache-aside for free slots.** Viewing free slots is far more common than booking. The list for one doctor and day is cached in Redis for 60 seconds and deleted whenever a slot on that day changes (book, cancel, reschedule, block). Booking never trusts the cache: it always locks and checks the real row, so the worst a stale cache can do is show a slot that then returns `409`. If Redis is down, reads fall back to PostgreSQL.

**Why a hand-written fixed-window rate limiter.** 5 booking attempts per minute per patient and 10 logins per minute per IP, using one Redis `INCR` + `EXPIRE` per request. A fixed window can let up to twice the limit through around a window boundary; a sliding window (sorted set of timestamps) would fix that at the cost of more memory. A retry that is answered from a saved idempotency response does not count, so a flaky connection cannot lock a patient out.

**Why the per-IP limit trusts only our own proxies.** Behind Nginx the visitor's IP comes from the `X-Forwarded-For` header, which anyone can fake. With `--forwarded-allow-ips '*'` uvicorn takes the *left-most* address, which is exactly the part a visitor controls, so a new fake IP per request would bypass the login limit. Now uvicorn only trusts proxies inside the Docker network (`FORWARDED_ALLOW_IPS=172.16.0.0/12`) and takes the right-most address that is not one of them, and the host Nginx overwrites the header instead of appending to it.

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

Latest run: **138 tests passed, 98% line coverage.**

| Test | What it proves | Result |
|---|---|---|
| `test_100_simultaneous_bookings_for_one_slot` | 100 threads book the same slot at the same instant through a live uvicorn server | exactly 1 × `201`, 99 × `409`, 1 confirmed booking in the database |
| `test_same_key_sent_in_parallel_creates_one_booking` | 5 parallel requests with one `Idempotency-Key` | all 5 get the same `201` response, 1 booking |
| `test_same_key_five_times_creates_one_booking` | 5 sequential retries | 1 booking, replays marked `Idempotent-Replayed: true` |
| `test_patient_always_has_exactly_one_booking_across_many_reschedules` | repeated reschedules, and a failed one | patient always has exactly 1 confirmed booking |
| `test_parallel_requests_from_one_patient_cannot_beat_the_limits` | 5 parallel requests from one patient for 5 slots of one doctor | exactly 1 × `201`, 4 × `409` |
| `test_changing_visit_length_never_creates_overlapping_slots` | visit length changed while a slot is booked | booked slot kept, new slots fitted around it, none overlap |
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

After the per-patient locks and the doctor row lock were added, a 90 second run with 100 users straight against one uvicorn process (no Docker or Nginx, so not comparable with the table above) gave 4,505 requests, 0 errors, booking p50 13 ms / p95 140 ms, and no deadlocks in the PostgreSQL log.

## Scaling out

The question: if one API server is not enough, can we just add more? Only if nothing that matters lives inside one process. In MediSlot the slot locks, the per-patient limits and the idempotency keys all live in PostgreSQL, and the rate limiter counters and slot cache live in Redis, so any copy of the API can serve any request.

`./scripts/scale_test.sh` checks this with one command (only Docker is needed, about 12 minutes; give Docker Desktop at least 8 CPUs under Settings > Resources). It runs the same load test three times on a fresh database, with every API copy limited to **1 CPU**, as if each had its own small server:

1. **1 copy**, straight to PostgreSQL.
2. **3 copies** behind Nginx (round robin), straight to PostgreSQL.
3. **3 copies** behind Nginx, through **PgBouncer**.

Before each load test it runs the race test through Nginx: 100 patients book the same slot at the same instant, and the `X-Served-By` response header shows which copy answered each one. The load test itself (`load_tests/locustfile_scale.py`) uses login tokens created beforehand, so bcrypt password hashing does not drown out the numbers, and it measures only the time after every simulated user has started.

Results on an Apple M4 Mac mini (Docker with 10 CPUs), 2,500 simulated patients, 180 seconds per run, measured after all users had started (`USERS=2500 DURATION=180 bash scripts/scale_test.sh`):

| Setup | Requests/s | Median | p95 | Failed requests | Peak PostgreSQL connections | Race test (100 at once) |
|---|---|---|---|---|---|---|
| 1 copy | 414 | 4,200 ms | 4,400 ms | 203 of 54,147 (0.37%, Nginx 502s) | 41 of 100 | 1 booked, 99 "just taken" |
| 3 copies | 1,003 | 550 ms | 1,000 ms | 6,282 of 131,275 (4.8%, HTTP 500s) | **100 of 100**, 6,865 refused | 1 booked, 99 "just taken" |
| 3 copies + PgBouncer | **1,011** | 700 ms | 960 ms | **0 of 132,328** | 41 of 100 | 1 booked, 99 "just taken" |

What the runs showed:

1. **One copy tops out at about 414 requests/s.** A lighter run (1,000 users) gave the same ceiling (428 requests/s). Past it, requests queue: the median wait was 4.2 seconds, and Nginx gave up on some with `502 Bad Gateway`.
2. **Three copies handled 2.4 times the traffic** (1,011 requests/s) with a sixth of the waiting time. It is not a full 3 times, because the copies share one PostgreSQL, one Nginx and one machine with the load generator, which may itself have been close to its limit at this point.
3. **Adding app servers moved the bottleneck to the database, as predicted.** Without pooling, the three copies reached PostgreSQL's limit of 100 connections; it refused 6,865 connection attempts, and 4.8% of requests failed with a 500.
4. **PgBouncer removed every one of those failures** while the app needed only 41 real PostgreSQL connections, at the same throughput.
5. **No double booking in any run.** With the 100 simultaneous requests spread over three processes (for example 38 / 34 / 28), exactly one booking was made every time.

At 1,000 users (a lighter load) the difference showed up mostly in waiting time: one copy answered in 460 ms (median) and three copies in 3 ms, with p95 falling from 640 ms to 10 ms and no failed requests.

What to look for, and why:

- **Correctness across copies.** The race test must give exactly 1 booking and 99 "just taken" answers even when the requests are spread over 3 processes. A lock held in Python memory would fail this; a PostgreSQL row lock cannot.
- **Throughput.** Copies are limited to 1 CPU each, so going from 1 to 3 copies triples the CPU the API has. The `API CPU` column shows whether the copies were really the bottleneck (near 100%).
- **Database connections.** Each copy keeps a pool of up to 40 connections (`database_pool_size` 20 + `database_max_overflow` 20), so 3 copies may ask for 120, while PostgreSQL allows 100 by default. The `Peak Postgres connections` and `Connections refused by Postgres` columns show how close a run came. The race test is the sharpest probe: it runs right after the copies start, with empty pools, so all three open connections at the same moment. When PostgreSQL refuses one (`sorry, too many clients already`), that request gets a 500. Correctness still holds (never two bookings for one slot), but adding app servers has moved the bottleneck onto the database.
- **PgBouncer.** In transaction mode it lends a real PostgreSQL connection to a client only for the length of one transaction, so 120 app connections share 40 real ones. That works here because the app needs nothing from a connection beyond one transaction: row locks are released at commit, and the session time zone is UTC on the server anyway. PgBouncer 1.21+ keeps psycopg's prepared statements working in this mode (`MAX_PREPARED_STATEMENTS`).

What should not be copied: **Celery Beat** must run exactly once, or every reminder would be sent once per copy. Celery workers can be added freely, because the unique constraint on (booking, type) stops a notification from being created twice.

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
| Doctor | `GET /api/doctor/me`, `GET\|PUT /api/doctor/schedule`, `GET /api/doctor/slots?date=`, `POST /api/doctor/slots/{id}/block\|unblock`, `POST /api/doctor/block-day`, `GET /api/doctor/appointments?scope=today\|upcoming`, `PATCH /api/doctor/appointments/{id}`, `POST /api/doctor/appointments/{id}/cancel` |
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
- Online payment of the consultation fee, with a short hold on the slot during checkout.
- Refresh token rotation with a server-side revocation list, and refresh tokens in httpOnly cookies.
- Video consultations and digital prescriptions.
- Frontend tests (Vitest + React Testing Library) and end-to-end tests (Playwright).
