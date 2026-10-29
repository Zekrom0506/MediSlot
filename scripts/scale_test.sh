#!/usr/bin/env bash
# Scale-out experiment, one command:   ./scripts/scale_test.sh
#
# Runs the same load test three times, each on a fresh database:
#   1. one API copy (1 CPU), straight to PostgreSQL
#   2. three API copies (1 CPU each) behind Nginx, straight to PostgreSQL
#   3. three API copies behind Nginx, through PgBouncer
# Before each load test it runs the 100-patients-one-slot race test through Nginx.
# Results: load_tests/results/scale-report.md
#
# Only needs Docker. Uses its own Compose project (medislot-scale), so your normal
# stack and its data are not touched. Takes about 12 minutes.
#
# Optional settings, e.g.  USERS=800 ./scripts/scale_test.sh
#   USERS (1000) simulated patients     DURATION (150)  seconds per run
#   REPLICAS (3) copies in runs 2 and 3 LOCUST_CPUS (4)  CPUs for the load generator

set -euo pipefail
cd "$(dirname "$0")/.."

USERS=${USERS:-1000}
DURATION=${DURATION:-150}
RAMP=${RAMP:-50}
REPLICAS=${REPLICAS:-3}
export LOCUST_CPUS=${LOCUST_CPUS:-4}
RESULTS=load_tests/results
LOG=$RESULTS/docker.log
COMPOSE=(docker compose -p medislot-scale -f docker-compose.yml -f docker-compose.scale.yml)

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop and run this again." >&2
  exit 1
fi
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example."
fi

env_value() { grep -E "^$1=" .env | tail -1 | cut -d= -f2-; }
PG_USER=$(env_value POSTGRES_USER)
PG_PASSWORD=$(env_value POSTGRES_PASSWORD)
PG_DB=$(env_value POSTGRES_DB)

DOCKER_CPUS=$(docker info --format '{{.NCPU}}')
NEEDED_CPUS=$((REPLICAS + LOCUST_CPUS + 1))
if [ "$DOCKER_CPUS" -lt "$NEEDED_CPUS" ]; then
  echo "Warning: Docker has $DOCKER_CPUS CPUs, this test wants about $NEEDED_CPUS" >&2
  echo "($REPLICAS API copies + $LOCUST_CPUS for the load generator + 1 for PostgreSQL)." >&2
  echo "Raise it in Docker Desktop > Settings > Resources, or the copies share CPUs and the" >&2
  echo "comparison is unfair. Continuing in 5 seconds." >&2
  sleep 5
fi
HOST_INFO="$(uname -s) $(uname -m), Docker with $DOCKER_CPUS CPUs"
if [ "$(uname -s)" = "Darwin" ]; then
  HOST_INFO="$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo Mac), Docker with $DOCKER_CPUS CPUs"
fi

mkdir -p "$RESULTS"
rm -f "$RESULTS"/*.csv "$RESULTS"/*.json "$LOG"
echo "Docker progress messages go to $LOG"

cleanup() { "${COMPOSE[@]}" --profile pgbouncer --profile loadtest down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "Building images (first time takes a few minutes)..."
"${COMPOSE[@]}" build --quiet migrate api frontend 2>>"$LOG"
"${COMPOSE[@]}" --profile loadtest pull --quiet locust 2>>"$LOG"

postgres_sql() { "${COMPOSE[@]}" exec -T postgres psql -U "$PG_USER" -d "$PG_DB" -tAc "$1"; }

watch_connections() {
  # Highest number of client connections PostgreSQL saw, sampled every second.
  local peak=0 count
  while [ -f "$1.running" ]; do
    count=$(postgres_sql "SELECT count(*) FROM pg_stat_activity WHERE backend_type = 'client backend'" 2>/dev/null || echo 0)
    if [ "${count:-0}" -gt "$peak" ]; then peak=$count; fi
    echo "$peak" > "$1.peak"
    sleep 1
  done
}

watch_cpu() {
  # Average CPU use per API copy, sampled every few seconds during the run.
  while [ -f "$1.running" ]; do
    docker stats --no-stream --format '{{.Name}} {{.CPUPerc}}' | grep -- '-api-' | sed 's/%//' | awk '{print $2}' >> "$1.cpu"
  done
}

run_experiment() {
  local name=$1 replicas=$2 use_pgbouncer=$3
  local prefix="$RESULTS/$name"
  echo
  echo "=== $name: $replicas API copies$([ "$use_pgbouncer" = yes ] && echo ', through PgBouncer') ==="
  cleanup

  # (Arrays are expanded with ${x[@]+...} below: macOS ships bash 3.2, which
  # treats an empty array as unset under "set -u".)
  local services=(postgres redis api frontend)
  local profiles=()
  if [ "$use_pgbouncer" = yes ]; then
    export SCALE_DATABASE_URL="postgresql+psycopg://$PG_USER:$PG_PASSWORD@pgbouncer:5432/$PG_DB"
    services+=(pgbouncer)
    profiles=(--profile pgbouncer)
  else
    unset SCALE_DATABASE_URL
  fi

  "${COMPOSE[@]}" ${profiles[@]+"${profiles[@]}"} up -d --scale "api=$replicas" "${services[@]}" >>"$LOG" 2>&1
  echo "Seeding demo data..."
  "${COMPOSE[@]}" run --rm -T migrate python -m app.seed >>"$LOG" 2>&1
  local max_connections
  max_connections=$(postgres_sql "SHOW max_connections")

  echo "Race test: 100 patients book one slot at the same instant, through Nginx..."
  "${COMPOSE[@]}" run --rm -T migrate python -m scripts.race_check http://frontend \
    > "$prefix.race.json" 2>>"$LOG" || echo "  DOUBLE BOOKING: more than one winner, see $prefix.race.json"
  cat "$prefix.race.json"
  "${COMPOSE[@]}" run --rm -T migrate python -m scripts.make_tokens > "$RESULTS/tokens.json" 2>>"$LOG"

  echo "Load test: $USERS patients for $DURATION seconds..."
  touch "$prefix.running"
  watch_connections "$prefix" &
  local watcher=$!
  watch_cpu "$prefix" &
  local cpu_watcher=$!
  "${COMPOSE[@]}" --profile loadtest run --rm -T locust \
    -f locustfile_scale.py ScalePatient --headless --only-summary \
    -u "$USERS" -r "$RAMP" -t "${DURATION}s" --host http://frontend --reset-stats \
    --processes "$LOCUST_CPUS" --csv "results/$name" >>"$LOG" 2>&1 || true
  rm -f "$prefix.running"
  wait "$watcher" "$cpu_watcher" 2>/dev/null || true

  local peak cpu refused
  peak=$(cat "$prefix.peak" 2>/dev/null || echo "?")
  # Each run starts a fresh PostgreSQL container, so its log only covers this run.
  refused=$("${COMPOSE[@]}" logs postgres 2>/dev/null | grep -c "too many clients" || true)
  cpu=$(awk '{ total += $1; count++ } END { if (count) printf "%.0f%%", total / count; else print "?" }' "$prefix.cpu" 2>/dev/null)
  printf '{"replicas": %s, "peak_connections": "%s", "max_connections": "%s", "refused_connections": %s, "api_cpu": "%s", "users": %s, "duration_seconds": %s, "host": "%s"}\n' \
    "$replicas" "$peak" "$max_connections" "${refused:-0}" "$cpu" "$USERS" "$DURATION" "$HOST_INFO" > "$prefix.extra.json"
  rm -f "$prefix.peak" "$prefix.cpu"

  "${COMPOSE[@]}" --profile loadtest run --rm -T --entrypoint python locust \
    scale_report.py summarize "results/$name" 2>>"$LOG"
}

run_experiment 1-copy 1 no
run_experiment 3-copies "$REPLICAS" no
run_experiment 3-copies-pgbouncer "$REPLICAS" yes

echo
echo "=== Results (also saved to $RESULTS/scale-report.md) ==="
"${COMPOSE[@]}" --profile loadtest run --rm -T --entrypoint python locust scale_report.py report results 2>>"$LOG"
