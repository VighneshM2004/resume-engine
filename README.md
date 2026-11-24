# resume-engine

Turns resumes (PDF, DOCX, scanned images) into structured, confidence-scored
candidate profiles, with a Flutter app for recruiters to upload, review,
correct, search and export.

> **Status:** M0 (foundations). See `docs/DECISIONS.md` for design decisions.

## Authorship

The code in this repository is written by Claude (Anthropic) and reviewed line
by line by Vighnesh M before merge. AI-written commits carry a
`Co-Authored-By: Claude` trailer.

## Quick start

Requirements: Docker with Compose v2, [uv](https://docs.astral.sh/uv/), GNU Make.

```bash
cp .env.example .env
make up          # starts api, postgres, redis, object storage; waits until healthy
curl localhost:8000/health
curl localhost:8000/ready
make test        # unit tests
make test-integration   # needs `make up` first
make down
```

## Repository layout

| Path | What lives there |
|---|---|
| `engine/` | `resume_engine`: the extraction pipeline as a plain Python package (no web or queue code) |
| `ml/` | Data preparation, training, evaluation and generated reports |
| `backend/` | FastAPI service, Celery workers, database migrations |
| `app/` | Flutter recruiter app (Android + web) |
| `taxonomy/` | ESCO skills (downloaded) and the reviewed alias file |
| `infra/` | Service configuration (object storage, monitoring, reverse proxy) |
| `docs/` | Decisions, security, runbook, labeling guide |

## Licence

MIT. See `LICENSE`.
