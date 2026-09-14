# MediSlot

A clinic appointment booking platform. Work in progress.

## Running locally

```bash
cp .env.example .env
docker compose up --build
```

The API runs on http://localhost:8000 and the interactive docs on http://localhost:8000/docs.

To fill the database with demo data:

```bash
docker compose exec api python -m app.seed
```
