"""Kaggle LiveCareer resume dataset: verify, read, deduplicate, split, profile.

Source: https://www.kaggle.com/datasets/snehaanbhawal/resume-dataset
(ADR-001, ADR-007). The archive is downloaded by hand into data/raw/ and
never committed. Everything here is deterministic: the same archive and seed
always produce the same records, duplicates and splits.

Archive layout:
    Resume/Resume.csv                 columns ID, Resume_str, Resume_html, Category
    data/data/<CATEGORY>/<ID>.pdf     one PDF per CSV row
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import re
import statistics
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

ARCHIVE_SHA256 = "b12c4ab34df707ad2cc64312c016509cad9b6c93b0baed7a6a2c7cbd6b2b7aa4"
CSV_MEMBER = "Resume/Resume.csv"
PDF_PREFIX = "data/data/"
EXPECTED_COLUMNS = ("ID", "Resume_str", "Resume_html", "Category")

# IDs and categories become path components when PDFs are extracted, so they
# are validated strictly: nothing in the archive can write outside out_dir.
_ID_RE = re.compile(r"^\d{1,12}$")
_CATEGORY_RE = re.compile(r"^[A-Z0-9][A-Z0-9_&-]{0,63}$")

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{8,}\d)(?!\d)")

# Resume_str fields can exceed csv's default 128 KiB field limit.
_CSV_FIELD_LIMIT = 2**31 - 1


class DatasetError(Exception):
    """The archive or its contents are not what this module expects."""


@dataclass(frozen=True, slots=True)
class ResumeRecord:
    id: str
    category: str
    text: str
    pdf_member: str

    @property
    def fingerprint(self) -> str:
        return text_fingerprint(self.text)


@dataclass(frozen=True, slots=True)
class Duplicate:
    dropped_id: str
    kept_id: str


# ------------------------------------------------------------------ verify


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive(path: Path, expected_sha256: str | None = None) -> None:
    expected_sha256 = expected_sha256 or ARCHIVE_SHA256
    if not path.is_file():
        raise DatasetError(
            f"{path} not found. Download the dataset zip from Kaggle "
            "(see docs/DATA.md) and save it at that path."
        )
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise DatasetError(
            f"{path} has SHA-256 {actual}, expected {expected_sha256}. "
            "The file is corrupt or a different version of the dataset."
        )


# ------------------------------------------------------------------ read


def read_records(archive: Path) -> list[ResumeRecord]:
    """Read every CSV row and pair it with its PDF. Fails on any mismatch."""
    with zipfile.ZipFile(archive) as zf:
        members = set(zf.namelist())
        if CSV_MEMBER not in members:
            raise DatasetError(f"{CSV_MEMBER} missing from archive")
        pdfs = {m for m in members if m.startswith(PDF_PREFIX) and m.endswith(".pdf")}

        csv.field_size_limit(_CSV_FIELD_LIMIT)
        with zf.open(CSV_MEMBER) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
            if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
                raise DatasetError(
                    f"unexpected CSV columns {reader.fieldnames}, expected {EXPECTED_COLUMNS}"
                )
            rows = list(reader)

    records: list[ResumeRecord] = []
    problems: list[str] = []
    seen_ids: set[str] = set()
    for line, row in enumerate(rows, start=2):  # line 1 is the header
        rid, category = row["ID"].strip(), row["Category"].strip()
        if not _ID_RE.match(rid):
            problems.append(f"line {line}: invalid ID {rid!r}")
            continue
        if not _CATEGORY_RE.match(category):
            problems.append(f"line {line}: invalid category {category!r}")
            continue
        if rid in seen_ids:
            problems.append(f"line {line}: duplicate ID {rid}")
            continue
        member = f"{PDF_PREFIX}{category}/{rid}.pdf"
        if member not in pdfs:
            problems.append(f"line {line}: no PDF at {member}")
            continue
        seen_ids.add(rid)
        records.append(ResumeRecord(rid, category, row["Resume_str"], member))

    orphans = pdfs - {r.pdf_member for r in records}
    problems.extend(f"PDF without CSV row: {m}" for m in sorted(orphans))
    if problems:
        shown = "\n  ".join(problems[:20])
        more = f"\n  ... and {len(problems) - 20} more" if len(problems) > 20 else ""
        raise DatasetError(f"{len(problems)} problem(s) in archive:\n  {shown}{more}")

    return sorted(records, key=lambda r: int(r.id))


# ------------------------------------------------------------------ dedupe


def normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def text_fingerprint(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def deduplicate(records: Iterable[ResumeRecord]) -> tuple[list[ResumeRecord], list[Duplicate]]:
    """Drop exact duplicates (same text after case/whitespace normalization).

    The lowest ID wins, so the result doesn't depend on input order. Without
    this, one resume could land in both train and test and inflate F1.
    """
    kept: dict[str, ResumeRecord] = {}
    dropped: list[Duplicate] = []
    for record in sorted(records, key=lambda r: int(r.id)):
        first = kept.setdefault(record.fingerprint, record)
        if first is not record:
            dropped.append(Duplicate(dropped_id=record.id, kept_id=first.id))
    return sorted(kept.values(), key=lambda r: int(r.id)), dropped


# ------------------------------------------------------------------ split


@dataclass(frozen=True)
class Splits:
    """Frozen assignment of record IDs to splits. Committed to git (IDs only)."""

    version: int
    seed: int
    archive_sha256: str
    gold_validation: list[str]
    gold_test: list[str]
    train: list[str]
    note: str = field(
        default="Gold IDs are hand-labeled in Label Studio (docs/LABELING_GUIDE.md). "
        "Never train on gold_test. Regenerating this file invalidates every "
        "reported metric."
    )

    def all_ids(self) -> list[str]:
        return [*self.gold_validation, *self.gold_test, *self.train]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Splits:
        data = json.loads(text)
        return cls(**data)


def make_splits(
    records: list[ResumeRecord],
    *,
    gold_size: int = 150,
    validation_size: int = 30,
    seed: int = 20261125,
    archive_sha256: str | None = None,
) -> Splits:
    """Stratified gold sample (every category represented), rest is train.

    Gold is spread evenly across categories rather than proportionally, so
    small categories still get enough labeled examples to report per-category
    numbers. Validation is taken round-robin across categories.
    """
    if not 0 < validation_size < gold_size <= len(records):
        raise ValueError("need 0 < validation_size < gold_size <= number of records")

    by_category: dict[str, list[str]] = defaultdict(list)
    for r in records:
        by_category[r.category].append(r.id)
    categories = sorted(by_category)

    quota = _allocate(gold_size, {c: len(by_category[c]) for c in categories})

    # Reproducible sampling, not security: a seeded PRNG is the point.
    rng = random.Random(seed)  # noqa: S311
    picked: dict[str, list[str]] = {}
    for c in categories:
        ids = sorted(by_category[c], key=int)
        picked[c] = rng.sample(ids, quota[c])

    interleaved = [
        picked[c][i] for i in range(max(quota.values())) for c in categories if i < len(picked[c])
    ]
    validation = interleaved[:validation_size]
    test = interleaved[validation_size:]
    gold = set(interleaved)
    train = [r.id for r in records if r.id not in gold]

    return Splits(
        version=1,
        seed=seed,
        archive_sha256=archive_sha256 or ARCHIVE_SHA256,
        gold_validation=sorted(validation, key=int),
        gold_test=sorted(test, key=int),
        train=sorted(train, key=int),
    )


def _allocate(total: int, sizes: dict[str, int]) -> dict[str, int]:
    """Even split of `total` over categories, capped by each category's size."""
    quota = dict.fromkeys(sizes, 0)
    remaining = total
    while remaining:
        open_ = sorted(
            (c for c in sizes if quota[c] < sizes[c]),
            key=lambda c: (quota[c], -sizes[c], c),
        )
        if not open_:
            raise ValueError("not enough records to fill the gold set")
        quota[open_[0]] += 1
        remaining -= 1
    return quota


def check_splits(splits: Splits, records: list[ResumeRecord]) -> list[str]:
    """Problems between a frozen split file and the current records."""
    problems: list[str] = []
    ids = splits.all_ids()
    if len(ids) != len(set(ids)):
        problems.append("an ID appears in more than one split")
    record_ids = {r.id for r in records}
    missing = set(ids) - record_ids
    unassigned = record_ids - set(ids)
    if missing:
        problems.append(f"{len(missing)} split IDs not in the dataset, e.g. {sorted(missing)[:5]}")
    if unassigned:
        problems.append(f"{len(unassigned)} dataset IDs in no split, e.g. {sorted(unassigned)[:5]}")
    return problems


# ------------------------------------------------------------------ extract


def extract_pdfs(archive: Path, records: Iterable[ResumeRecord], out_dir: Path) -> int:
    """Copy each record's PDF to out_dir/<CATEGORY>/<ID>.pdf. Returns count."""
    count = 0
    root = out_dir.resolve()
    with zipfile.ZipFile(archive) as zf:
        for r in records:
            # Paths are built from validated parts, never from the zip entry
            # name; the resolve() check is a second guard against traversal.
            dest = (root / r.category / f"{r.id}.pdf").resolve()
            if root not in dest.parents:
                raise DatasetError(f"refusing to write outside {root}: {dest}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(r.pdf_member))
            count += 1
    return count


def write_records_jsonl(records: Iterable[ResumeRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            row = {
                "id": r.id,
                "category": r.category,
                "pdf": f"{r.category}/{r.id}.pdf",
                "text_sha256": r.fingerprint,
                "text": r.text,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------ profile


@dataclass(frozen=True)
class Profile:
    total_rows: int
    duplicates_dropped: int
    unique_records: int
    categories: dict[str, int]
    median_chars: int
    p95_chars: int
    empty_texts: int
    with_email: int
    with_phone: int


def profile(records: list[ResumeRecord], duplicates: list[Duplicate]) -> Profile:
    lengths = sorted(len(r.text) for r in records)
    p95_index = max(0, round(0.95 * len(lengths)) - 1)
    return Profile(
        total_rows=len(records) + len(duplicates),
        duplicates_dropped=len(duplicates),
        unique_records=len(records),
        categories=dict(sorted(Counter(r.category for r in records).items())),
        median_chars=int(statistics.median(lengths)) if lengths else 0,
        p95_chars=lengths[p95_index] if lengths else 0,
        empty_texts=sum(1 for r in records if not r.text.strip()),
        with_email=sum(1 for r in records if _EMAIL_RE.search(r.text)),
        with_phone=sum(1 for r in records if _PHONE_RE.search(r.text)),
    )


def render_profile(p: Profile, splits: Splits | None) -> str:
    """Aggregate statistics only: safe to commit (no resume content)."""

    def pct(n: int) -> str:
        return f"{100 * n / p.unique_records:.1f}%" if p.unique_records else "n/a"

    lines = [
        "# Kaggle LiveCareer dataset profile",
        "",
        "Generated by `make data`. Aggregate counts only; no resume content.",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Archive SHA-256 | `{ARCHIVE_SHA256[:16]}…` |",
        f"| CSV rows | {p.total_rows} |",
        f"| Exact duplicates dropped | {p.duplicates_dropped} |",
        f"| Unique resumes | {p.unique_records} |",
        f"| Categories | {len(p.categories)} |",
        f"| Median text length (chars) | {p.median_chars} |",
        f"| 95th percentile length (chars) | {p.p95_chars} |",
        f"| Empty texts | {p.empty_texts} |",
        f"| Text contains an email address | {p.with_email} ({pct(p.with_email)}) |",
        f"| Text contains a phone-like number | {p.with_phone} ({pct(p.with_phone)}) |",
    ]
    if splits is not None:
        lines += [
            f"| Gold validation / test / train | {len(splits.gold_validation)} / "
            f"{len(splits.gold_test)} / {len(splits.train)} |",
        ]
    lines += ["", "## Resumes per category", "", "| Category | Resumes |", "|---|---|"]
    lines += [f"| {c} | {n} |" for c, n in p.categories.items()]
    return "\n".join(lines) + "\n"
