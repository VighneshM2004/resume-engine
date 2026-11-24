# Architecture Decision Records

Each record: **Context** (the forces), **Decision**, **Alternatives** (and why
not), **Consequences** (what we accept). Status is `Proposed` until approved by
the project owner, then `Accepted`. A changed decision gets a new record that
supersedes the old one; old records are never edited away.

| # | Decision | Status |
|---|---|---|
| 001 | Data: public labeled sets + 150-resume hand-labeled gold set | Proposed |
| 002 | Field-specific metric definitions | Proposed |
| 003 | Hybrid extraction pipeline; no external LLM APIs | Proposed |
| 004 | Taxonomy: ESCO skills pillar + maintained alias file | Proposed |
| 005 | Performance targets measured on 4 vCPU / 8 GB, no GPU | Proposed |
| 006 | Flutter targets: Android + web; iOS out of scope | Proposed |
| 007 | Public repo uses only public and synthetic resumes | Proposed |
| 008 | Calibrated per-field confidence with flag thresholds | Proposed |
| 009 | Per-skill experience = union of mentioning jobs' date ranges | Proposed |
| 010 | Object storage: SeaweedFS (S3 API) instead of MinIO | Proposed |
| 011 | Python 3.12 | Proposed |
| 012 | uv for dependency management | Proposed |
| 013 | One uv workspace and one lock file for all Python packages | Proposed |
| 014 | Flutter state management: Riverpod | Proposed |
| 015 | Dev environment: WSL2 + Docker Desktop; Flutter on Windows | Proposed |
| 016 | Licence: MIT | Proposed |
| 017 | Authorship: AI-written code, human-reviewed, disclosed | Proposed |
| 018 | Separate liveness (/health) and readiness (/ready) probes | Proposed |

---

## ADR-001: Data strategy

**Context.** No single public dataset labels every field the schema needs
(name, contacts, skills, jobs, education, certifications), and accuracy claims
need a held-out set nobody trained on.
**Decision.** Train on public labeled sets (skills/NER spans) plus a synthetic
format-robustness set; evaluate on a 150-resume hand-labeled gold set
(stratified by format), split 30 validation / 120 frozen test.
**Alternatives.** Public data only: doesn't cover all fields, and its label
quality is unknown. Label everything by hand: too slow for the timeline.
**Consequences.** Labeling is the largest early cost (risk table, PRD §11);
inter-annotator agreement must be reported before the gold set is trusted.

## ADR-002: Metric definitions

**Context.** "F1" is undefined for structured fields until the unit of
comparison and match rule are fixed; without that, the targets are untestable.
**Decision.** Per-field rules in `ml/evaluation/metrics.py` (PRD §3): skills
as a set of canonical IDs per resume, micro-averaged; exact match for
normalized email/phone; fuzzy (rapidfuzz token-set) for education and jobs;
95% bootstrap CIs, overall and per format.
**Alternatives.** Token-level NER F1: measures the model, not what a recruiter
sees. Exact string match everywhere: punishes harmless formatting differences.
**Consequences.** Metrics are code and get unit tests; changing a rule means a
new ADR and re-running all reported numbers.

## ADR-003: Hybrid extraction; no external LLM APIs

**Context.** Resumes are personal data; per-resume latency and cost must be
predictable; every extracted value must trace to a source span.
**Decision.** Rules for formatted fields (contacts, dates), layout-aware
section detection, a fine-tuned small transformer for entities, deterministic
normalization with ML fallback. Everything runs inside our own containers.
**Alternatives.** Hosted LLM extraction: sends PII to a third party, cost and
latency scale per resume, outputs are hard to calibrate and audit. Pure rules:
brittle across layouts and phrasing.
**Consequences.** We own model training and evaluation; accuracy depends on
our data more than on a vendor's model.

## ADR-004: Skill taxonomy

**Context.** Normalization needs canonical IDs ("JS", "js" → JavaScript).
**Decision.** ESCO skills pillar as the base, plus `taxonomy/aliases.yaml`
(reviewed, committed) for tech names and abbreviations ESCO lacks.
**Alternatives.** A home-grown list: no structure, no multilingual labels.
Proprietary taxonomies (e.g. Lightcast): licensing.
**Consequences.** Unmatched skills are kept with `canonical_id: null` and
logged weekly for alias review.

## ADR-005: Hardware for performance targets

**Context.** "p95 < 5 s" means nothing without the machine it's measured on.
**Decision.** All latency/throughput targets are measured on the staging VM
(4 vCPU, 8 GB RAM, no GPU). Targets split by format: ≤ 5 s text PDF/DOCX,
≤ 12 s scanned images (OCR alone takes seconds on CPU).
**Alternatives.** GPU instance: cost outside budget. One target for all
formats: unachievable for scans on CPU without dropping quality.
**Consequences.** Model size is capped by CPU inference cost (DistilBERT-class).

## ADR-006: Flutter targets

**Context.** iOS builds need macOS and an Apple developer account.
**Decision.** Ship an Android APK and a Flutter web build.
**Alternatives.** iOS via cloud macOS CI: added cost and setup for no new
evidence of skill.
**Consequences.** Layouts and tests target phone, tablet and ≥ 1280 px web.

## ADR-007: Data in the public repository

**Context.** The repo is public (portfolio); resumes are personal data.
**Decision.** Only public-licence or synthetic (Faker-generated) resumes appear
in fixtures, tests, screenshots and demos. `data/` is git-ignored and filled by
scripts with checksums.
**Alternatives.** Private repo: defeats the portfolio purpose.
**Consequences.** gitleaks plus a PII regex check run in CI.

## ADR-008: Confidence and flags

**Context.** A wrong value shown as fact is worse than a value marked
"check this".
**Decision.** Each field's confidence combines model probability,
normalization score and rule checks, calibrated on the validation split; fields
below a per-field threshold are flagged.
**Alternatives.** Raw softmax scores: badly calibrated. No confidence: hides
errors.
**Consequences.** Target (G3): flagged fields contain ≥ 50% of all errors
while flagging ≤ 20% of fields.

## ADR-009: Per-skill experience

**Context.** Resumes rarely state years per skill.
**Decision.** Skill months = length of the union of date ranges of jobs whose
title or description mentions the skill. Skills listed only in a skills section
get `experience_months: null`, not 0.
**Alternatives.** Total experience for every skill: overstates. Self-reported
numbers only: rarely present.
**Consequences.** Search must define how `null` behaves in a "min years"
filter (decide in M4).

## ADR-010: Object storage

**Context.** Uploaded files need S3-compatible storage locally and in staging.
MinIO stopped publishing community Docker images and binaries (October 2025),
and its repository was archived (2026).
**Decision.** SeaweedFS (Apache-2.0), single-container `weed server -s3` for
local and CI, image pinned (`chrislusf/seaweedfs:4.28`). Application code uses
only the S3 API via boto3 with path-style addressing.
**Alternatives.** Garage: needs layout and key setup commands before first
use. RustFS: younger project. Building MinIO from source: maintaining an
unpatched, archived codebase.
**Consequences.** Swapping to any S3-compatible service (cloud or self-hosted)
is a config change. The dev identity in `infra/seaweedfs/s3.dev.json` is for
local use only and is allowlisted in `.gitleaks.toml`.

## ADR-011: Python version

**Context.** Needs wheels for PyTorch, transformers, spaCy, PyMuPDF and
Tesseract bindings on Linux.
**Decision.** Python 3.12 (`requires-python = ">=3.12,<3.13"`).
**Alternatives.** 3.13: newer, but the ML stack's wheel coverage is less
complete. 3.11: older than needed.
**Consequences.** Upper bound is deliberate; bump in a dedicated PR after
checking the ML wheels.

## ADR-012: Dependency manager

**Context.** Builds must be reproducible: CI, Docker and laptops must install
identical versions.
**Decision.** uv, with `uv.lock` committed and `--locked`/`--frozen` in CI and
Docker.
**Alternatives.** Poetry: slower resolver, no built-in Python version
management. pip + requirements.txt: no lock of transitive dependencies without
extra tooling.
**Consequences.** One tool for Python versions, venvs, locking and running.

## ADR-013: Workspace layout

**Context.** `engine/` (pipeline) and `backend/` (API) are separate packages;
the backend depends on the engine; evaluation must run the same engine code.
**Decision.** A uv workspace at the repo root with one `uv.lock`.
**Alternatives.** Separate lock per package: versions can drift between the
engine the API runs and the engine evaluation measures.
**Consequences.** Docker builds use the repo root as context.

## ADR-014: Flutter state management

**Context.** The app needs async data, auth state, dependency injection for
tests.
**Decision.** Riverpod.
**Alternatives.** Bloc: more boilerplate per feature for the same testability.
Provider: superseded by Riverpod. setState: doesn't scale past one screen.
**Consequences.** Repositories are injected via providers and overridden with
fakes in widget tests.

## ADR-015: Development environment

**Context.** Development machine runs Windows; the stack runs on Linux
containers.
**Decision.** Code lives in WSL2 (Ubuntu); Docker Desktop with the WSL2
backend; Flutter and the Android emulator run on Windows.
**Alternatives.** Repo on the Windows filesystem: slow bind mounts, broken file
watching. A VirtualBox VM: fixed RAM allocation, port-forwarding to reach the
API from Windows.
**Consequences.** `.gitattributes` forces LF line endings; the Flutter app is
edited from Windows via `\\wsl$` or a Windows-side clone.

## ADR-016: Licence

**Context.** Public portfolio repository.
**Decision.** MIT.
**Alternatives.** Apache-2.0: adds an explicit patent grant, unnecessary here.
No licence: legally "all rights reserved", which discourages reading the code.
**Consequences.** Anyone may reuse the code with attribution.

## ADR-017: Authorship

**Context.** This is a portfolio project. The code is written by Claude
(Anthropic); the owner directs the design, reviews every line, and runs every
test and deployment.
**Decision.** Disclose it: the README says so, and AI-written commits carry a
`Co-Authored-By: Claude` trailer. Nothing merges without the owner's review and
a passing CI run on their machine/GitHub.
**Alternatives.** Not disclosing: misrepresents the work to readers.
**Consequences.** The owner must be able to explain any line and decision in a
walkthrough; review comments and ADR approvals are the record of that.

## ADR-018: Liveness vs readiness probes

**Context.** Orchestrators use one probe to restart a process and another to
route traffic to it.
**Decision.** `/health` never touches dependencies (restart signal);
`/ready` checks Postgres, Redis and object storage concurrently with a bounded
timeout each and returns 503 if any fail (traffic signal). Responses carry
dependency names and fixed error codes only; details go to server logs.
**Alternatives.** One `/health` that checks everything: a database blip would
make the orchestrator restart every healthy API instance at once.
**Consequences.** The Docker HEALTHCHECK uses `/health`; deploy smoke tests and
load balancers use `/ready`.
