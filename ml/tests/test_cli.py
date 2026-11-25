"""End-to-end CLI runs against a fake archive in a temp directory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from resume_ml import cli
from resume_ml.data import kaggle

from .conftest import build_archive, synthetic_rows


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    rows = synthetic_rows({"ARTS": 120, "HR": 120})
    rows.append(("99999", "HR", rows[0][2].upper()))  # duplicate of the first row
    archive = build_archive(tmp_path / "archive.zip", rows)
    monkeypatch.setattr(kaggle, "ARCHIVE_SHA256", kaggle.sha256_file(archive))
    return tmp_path


def _args(ws: Path, *command: str) -> list[str]:
    return ["--archive", str(ws / "archive.zip"), "--splits", str(ws / "splits.json"), *command]


def _data(ws: Path) -> list[str]:
    return [
        *_args(ws, "data"),
        "--out",
        str(ws / "interim"),
        "--profile",
        str(ws / "profile.md"),
    ]


def test_splits_then_data_end_to_end(workspace: Path) -> None:
    assert cli.main(_args(workspace, "splits")) == 0
    splits = json.loads((workspace / "splits.json").read_text())
    assert len(splits["gold_validation"]) == 30
    assert len(splits["gold_test"]) == 120

    assert cli.main(_data(workspace)) == 0
    lines = (workspace / "interim" / "records.jsonl").read_text().splitlines()
    assert len(lines) == 240  # 241 rows minus 1 duplicate
    assert (workspace / "interim" / "pdf" / "ARTS").is_dir()
    assert "99999\t1000" in (workspace / "interim" / "duplicates.tsv").read_text()
    assert (
        "Gold validation / test / train | 30 / 120 / 90" in (workspace / "profile.md").read_text()
    )


def test_splits_refuses_to_overwrite(workspace: Path) -> None:
    assert cli.main(_args(workspace, "splits")) == 0
    before = (workspace / "splits.json").read_text()
    assert cli.main(_args(workspace, "splits")) == 1
    assert (workspace / "splits.json").read_text() == before


def test_data_fails_when_frozen_splits_drift(workspace: Path) -> None:
    assert cli.main(_args(workspace, "splits")) == 0
    path = workspace / "splits.json"
    data = json.loads(path.read_text())
    data["train"].append("123456789")
    path.write_text(json.dumps(data))
    assert cli.main(_data(workspace)) == 1


def test_bad_checksum_exits_2(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kaggle, "ARCHIVE_SHA256", "0" * 64)
    assert cli.main(_data(workspace)) == 2
