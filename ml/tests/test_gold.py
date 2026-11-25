"""Label Studio export → gold records, including every rule the guide sets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from resume_ml import cli
from resume_ml.data import kaggle
from resume_ml.labeling import gold

TEXT = (
    "Skills Excel, QuickBooks and GAAP. "
    "Experience Staff Accountant Company Name 2015 to Current prepared reports. "
    "Education Bachelor of Science : Accounting State University 2014 "
    "Certifications CPA"
)


def span(label: str, phrase: str, nth: int = 0) -> dict[str, Any]:
    start = -1
    for _ in range(nth + 1):
        start = TEXT.index(phrase, start + 1)
    return {
        "type": "labels",
        "from_name": "label",
        "value": {"start": start, "end": start + len(phrase), "text": phrase, "labels": [label]},
    }


def block(label: str, first: str, last: str) -> dict[str, Any]:
    start = TEXT.index(first)
    end = TEXT.index(last) + len(last)
    return {
        "type": "labels",
        "from_name": "label",
        "value": {"start": start, "end": end, "text": TEXT[start:end], "labels": [label]},
    }


QUALITY_OK = {"type": "choices", "from_name": "quality", "value": {"choices": ["usable"]}}

GOOD_RESULT: list[dict[str, Any]] = [
    span("SKILL", "Excel"),
    span("SKILL", "QuickBooks"),
    span("SKILL", "GAAP"),
    block("JOB_ENTRY", "Staff Accountant", "prepared reports"),
    span("JOB_TITLE", "Staff Accountant"),
    span("COMPANY", "Company Name"),
    span("JOB_DATES", "2015 to Current"),
    block("EDU_ENTRY", "Bachelor of Science", "2014"),
    span("DEGREE", "Bachelor of Science : Accounting"),
    span("INSTITUTION", "State University"),
    span("EDU_DATES", "2014"),
    span("CERTIFICATION", "CPA"),
    QUALITY_OK,
]


def task(
    result: list[dict[str, Any]],
    rid: str = "11",
    *,
    cancelled: bool = False,
    updated: str = "2026-11-26T10:00:00Z",
) -> dict[str, Any]:
    return {
        "data": {"id": rid, "category": "ACCOUNTANT", "split": "gold_test", "text": TEXT},
        "annotations": [{"result": result, "was_cancelled": cancelled, "updated_at": updated}],
    }


def test_converts_a_correct_annotation() -> None:
    records, report = gold.convert_export([task(GOOD_RESULT)])
    r = records[0]
    assert r.usable
    assert r.skills == ["Excel", "QuickBooks", "GAAP"]
    assert r.jobs == [
        {"title": "Staff Accountant", "company": "Company Name", "dates": "2015 to Current"}
    ]
    assert r.education == [
        {
            "degree": "Bachelor of Science : Accounting",
            "institution": "State University",
            "dates": "2014",
        }
    ]
    assert r.certifications == ["CPA"]
    assert report.jobs == 1
    assert report.label_counts["SKILL"] == 3


def test_repeated_skill_mentions_count_once() -> None:
    result = [*GOOD_RESULT, span("SKILL", "Excel")]
    records, _ = gold.convert_export([task(result)])
    assert records[0].skills.count("Excel") == 1


def test_uses_the_latest_submitted_annotation() -> None:
    t = task(GOOD_RESULT, updated="2026-11-26T10:00:00Z")
    newer = [span("SKILL", "Excel"), QUALITY_OK]
    t["annotations"].append({"result": newer, "was_cancelled": False, "updated_at": "2026-11-27"})
    t["annotations"].append({"result": [], "was_cancelled": True, "updated_at": "2026-11-28"})
    records, _ = gold.convert_export([t])
    assert records[0].skills == ["Excel"]


def _problems(result: list[dict[str, Any]]) -> str:
    with pytest.raises(gold.GoldError) as info:
        gold.convert_export([task(result)])
    return str(info.value)


def test_rejects_field_outside_its_entry() -> None:
    result = [r for r in GOOD_RESULT if r["value"].get("labels") != ["JOB_ENTRY"]]
    assert "inside no JOB_ENTRY" in _problems(result)


def test_rejects_two_titles_in_one_job() -> None:
    result = [*GOOD_RESULT, span("JOB_TITLE", "prepared reports")]
    assert "two JOB_TITLE" in _problems(result)


def test_rejects_empty_entry() -> None:
    result = [*GOOD_RESULT, block("JOB_ENTRY", "Skills", "Excel")]
    assert "no labeled fields" in _problems(result)


def test_rejects_missing_quality_choice() -> None:
    result = [r for r in GOOD_RESULT if r is not QUALITY_OK]
    assert "usable/unusable" in _problems(result)


def test_rejects_unknown_label_and_out_of_range_span() -> None:
    bad = span("SKILL", "Excel")
    bad["value"] = {**bad["value"], "labels": ["SKILLS"]}
    oob = span("SKILL", "CPA")
    oob["value"] = {**oob["value"], "end": len(TEXT) + 5}
    problems = _problems([*GOOD_RESULT, bad, oob])
    assert "unknown label" in problems
    assert "outside the text" in problems


def test_rejects_two_locations() -> None:
    result = [*GOOD_RESULT, span("LOCATION", "Excel"), span("LOCATION", "GAAP")]
    assert "more than one LOCATION" in _problems(result)


def test_rejects_unannotated_and_cancelled_tasks() -> None:
    with pytest.raises(gold.GoldError, match="no submitted annotation"):
        gold.convert_export([task(GOOD_RESULT, cancelled=True)])


def test_reports_unlabeled_gold_ids_unless_partial() -> None:
    with pytest.raises(gold.GoldError, match="not labeled yet"):
        gold.convert_export([task(GOOD_RESULT, rid="11")], expected_ids=["11", "12"])
    records, _ = gold.convert_export([task(GOOD_RESULT, rid="11")], expected_ids=None)
    assert len(records) == 1


def test_rejects_duplicate_resume() -> None:
    with pytest.raises(gold.GoldError, match="more than once"):
        gold.convert_export([task(GOOD_RESULT), task(GOOD_RESULT)])


def test_build_tasks_puts_validation_first() -> None:
    records = [{"id": str(i), "category": "ARTS", "text": f"t{i}"} for i in range(1, 6)]
    tasks = gold.build_tasks(records, gold_validation=["5"], gold_test=["2", "3"])
    assert [t["data"]["id"] for t in tasks] == ["5", "2", "3"]
    assert tasks[0]["data"]["split"] == "gold_validation"


def test_build_tasks_fails_on_unknown_id() -> None:
    with pytest.raises(gold.GoldError, match="not found"):
        gold.build_tasks([], gold_validation=["1"], gold_test=[])


# ------------------------------------------------------------------ CLI


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    splits = kaggle.Splits(
        version=1, seed=1, archive_sha256="x", gold_validation=["11"], gold_test=["12"], train=[]
    )
    (tmp_path / "splits.json").write_text(splits.to_json())
    records = [
        {"id": "11", "category": "ACCOUNTANT", "text": TEXT},
        {"id": "12", "category": "ACCOUNTANT", "text": TEXT},
    ]
    (tmp_path / "records.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    return tmp_path


def test_cli_label_tasks(ws: Path) -> None:
    out = ws / "tasks.json"
    argv = ["--splits", str(ws / "splits.json"), "label-tasks"]
    assert cli.main([*argv, "--records", str(ws / "records.jsonl"), "--tasks", str(out)]) == 0
    assert [t["data"]["id"] for t in json.loads(out.read_text())] == ["11", "12"]


def test_cli_label_import_partial_then_complete(ws: Path) -> None:
    export = ws / "export.json"
    out = ws / "gold.jsonl"
    base = ["--splits", str(ws / "splits.json"), "label-import", str(export), "--out", str(out)]

    export.write_text(json.dumps([task(GOOD_RESULT, rid="11")]))
    assert cli.main(base) == 1  # resume 12 not labeled yet
    assert cli.main([*base, "--partial"]) == 0

    export.write_text(json.dumps([task(GOOD_RESULT, rid="11"), task(GOOD_RESULT, rid="12")]))
    assert cli.main(base) == 0
    assert len(out.read_text().splitlines()) == 2


def test_cli_label_import_rejects_rule_breaks(ws: Path) -> None:
    export = ws / "export.json"
    bad = [r for r in GOOD_RESULT if r is not QUALITY_OK]
    export.write_text(json.dumps([task(bad, rid="11")]))
    argv = ["--splits", str(ws / "splits.json"), "label-import", str(export), "--partial"]
    assert cli.main([*argv, "--out", str(ws / "g.jsonl")]) == 1
    assert not (ws / "g.jsonl").exists()
