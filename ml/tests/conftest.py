"""Builds small fake Kaggle archives with the real layout. No real resumes."""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from resume_ml.data import kaggle

Row = tuple[str, str, str]  # (id, category, text)
MakeArchive = Callable[..., Path]


def build_archive(
    path: Path,
    rows: Sequence[Row],
    *,
    extra_pdfs: Sequence[str] = (),
    skip_pdfs: Sequence[str] = (),
    columns: Sequence[str] = kaggle.EXPECTED_COLUMNS,
) -> Path:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for rid, category, text in rows:
        writer.writerow([rid, text, f"<p>{text}</p>", category])
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(kaggle.CSV_MEMBER, buffer.getvalue())
        for rid, category, _ in rows:
            if rid not in skip_pdfs:
                zf.writestr(f"{kaggle.PDF_PREFIX}{category}/{rid}.pdf", f"%PDF-fake {rid}")
        for member in extra_pdfs:
            zf.writestr(member, "%PDF-orphan")
    return path


@pytest.fixture
def make_archive(tmp_path: Path) -> MakeArchive:
    def make(rows: Sequence[Row], **kwargs: object) -> Path:
        return build_archive(tmp_path / "archive.zip", rows, **kwargs)  # type: ignore[arg-type]

    return make


def synthetic_rows(per_category: dict[str, int]) -> list[Row]:
    rows: list[Row] = []
    next_id = 1000
    for category, n in per_category.items():
        for i in range(n):
            rows.append((str(next_id), category, f"{category} resume number {i} id {next_id}"))
            next_id += 1
    return rows
