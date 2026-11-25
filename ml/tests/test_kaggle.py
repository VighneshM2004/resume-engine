from __future__ import annotations

from pathlib import Path

import pytest

from resume_ml.data import kaggle

from .conftest import MakeArchive, synthetic_rows

# ------------------------------------------------------------------ verify


def test_verify_accepts_matching_checksum(make_archive: MakeArchive) -> None:
    archive = make_archive([("1", "ARTS", "text")])
    kaggle.verify_archive(archive, kaggle.sha256_file(archive))


def test_verify_rejects_wrong_checksum(make_archive: MakeArchive) -> None:
    archive = make_archive([("1", "ARTS", "text")])
    with pytest.raises(kaggle.DatasetError, match="SHA-256"):
        kaggle.verify_archive(archive, "0" * 64)


def test_verify_explains_missing_file(tmp_path: Path) -> None:
    with pytest.raises(kaggle.DatasetError, match="not found"):
        kaggle.verify_archive(tmp_path / "nope.zip")


# ------------------------------------------------------------------ read


def test_read_pairs_rows_with_pdfs_sorted_by_id(make_archive: MakeArchive) -> None:
    archive = make_archive([("20", "ARTS", "b"), ("3", "HR", "a")])
    records = kaggle.read_records(archive)
    assert [r.id for r in records] == ["3", "20"]
    assert records[0].pdf_member == "data/data/HR/3.pdf"


def test_read_handles_fields_larger_than_csv_default_limit(make_archive: MakeArchive) -> None:
    big = "x" * 200_000  # csv's default limit is 131072
    records = kaggle.read_records(make_archive([("1", "ARTS", big)]))
    assert len(records[0].text) == 200_000


def test_read_fails_on_missing_pdf(make_archive: MakeArchive) -> None:
    archive = make_archive([("1", "ARTS", "a"), ("2", "ARTS", "b")], skip_pdfs=["2"])
    with pytest.raises(kaggle.DatasetError, match="no PDF"):
        kaggle.read_records(archive)


def test_read_fails_on_orphan_pdf(make_archive: MakeArchive) -> None:
    archive = make_archive([("1", "ARTS", "a")], extra_pdfs=["data/data/ARTS/99.pdf"])
    with pytest.raises(kaggle.DatasetError, match="without CSV row"):
        kaggle.read_records(archive)


def test_read_fails_on_unexpected_columns(make_archive: MakeArchive) -> None:
    archive = make_archive([("1", "ARTS", "a")], columns=["ID", "Text", "Html", "Category"])
    with pytest.raises(kaggle.DatasetError, match="columns"):
        kaggle.read_records(archive)


@pytest.mark.parametrize(
    ("rid", "category"),
    [("../../etc", "ARTS"), ("1", "../../tmp"), ("1", "arts lower"), ("12a", "ARTS")],
)
def test_read_rejects_ids_and_categories_unsafe_as_paths(
    make_archive: MakeArchive, rid: str, category: str
) -> None:
    with pytest.raises(kaggle.DatasetError, match="invalid"):
        kaggle.read_records(make_archive([(rid, category, "a")]))


# ------------------------------------------------------------------ dedupe


def test_dedupe_ignores_case_and_whitespace_and_keeps_lowest_id(
    make_archive: MakeArchive,
) -> None:
    rows = [
        ("30", "ARTS", "Senior  Accountant\n"),
        ("7", "HR", "senior accountant"),
        ("9", "HR", "x"),
    ]
    unique, dropped = kaggle.deduplicate(kaggle.read_records(make_archive(rows)))
    assert [r.id for r in unique] == ["7", "9"]
    assert dropped == [kaggle.Duplicate(dropped_id="30", kept_id="7")]


# ------------------------------------------------------------------ split


def _records(per_category: dict[str, int]) -> list[kaggle.ResumeRecord]:
    return [
        kaggle.ResumeRecord(rid, cat, text, f"data/data/{cat}/{rid}.pdf")
        for rid, cat, text in synthetic_rows(per_category)
    ]


def test_splits_are_disjoint_and_cover_every_record() -> None:
    records = _records({"ARTS": 40, "HR": 40, "BPO": 10})
    s = kaggle.make_splits(records, gold_size=30, validation_size=6)
    ids = s.all_ids()
    assert len(ids) == len(set(ids)) == len(records)
    assert (len(s.gold_validation), len(s.gold_test)) == (6, 24)


def test_gold_is_spread_evenly_across_categories() -> None:
    records = _records({"ARTS": 100, "HR": 100, "BPO": 4})
    s = kaggle.make_splits(records, gold_size=30, validation_size=6)
    category = {r.id: r.category for r in records}
    counts = {c: 0 for c in ("ARTS", "HR", "BPO")}
    for rid in [*s.gold_validation, *s.gold_test]:
        counts[category[rid]] += 1
    # BPO only has 4 resumes; the other 26 split evenly.
    assert counts == {"ARTS": 13, "HR": 13, "BPO": 4}


def test_validation_includes_every_category() -> None:
    records = _records({c: 20 for c in ("A1", "B2", "C3", "D4", "E5")})
    s = kaggle.make_splits(records, gold_size=25, validation_size=5)
    category = {r.id: r.category for r in records}
    assert {category[rid] for rid in s.gold_validation} == {"A1", "B2", "C3", "D4", "E5"}


def test_splits_are_deterministic_for_a_seed() -> None:
    records = _records({"ARTS": 30, "HR": 30})
    a = kaggle.make_splits(records, gold_size=10, validation_size=2, seed=1)
    b = kaggle.make_splits(list(reversed(records)), gold_size=10, validation_size=2, seed=1)
    c = kaggle.make_splits(records, gold_size=10, validation_size=2, seed=2)
    assert a == b
    assert a.gold_test != c.gold_test


def test_splits_round_trip_through_json() -> None:
    s = kaggle.make_splits(_records({"ARTS": 20}), gold_size=5, validation_size=1)
    assert kaggle.Splits.from_json(s.to_json()) == s


def test_check_splits_detects_drift() -> None:
    records = _records({"ARTS": 20})
    s = kaggle.make_splits(records, gold_size=5, validation_size=1)
    assert kaggle.check_splits(s, records) == []
    extra = kaggle.ResumeRecord("999999", "ARTS", "new", "data/data/ARTS/999999.pdf")
    problems = kaggle.check_splits(s, [*records[1:], extra])
    assert any("not in the dataset" in p for p in problems)
    assert any("in no split" in p for p in problems)


def test_make_splits_rejects_impossible_sizes() -> None:
    with pytest.raises(ValueError):
        kaggle.make_splits(_records({"ARTS": 5}), gold_size=10, validation_size=2)


# ------------------------------------------------------------------ extract


def test_extract_writes_category_folders(make_archive: MakeArchive, tmp_path: Path) -> None:
    archive = make_archive([("1", "ARTS", "a"), ("2", "HR", "b")])
    out = tmp_path / "pdf"
    n = kaggle.extract_pdfs(archive, kaggle.read_records(archive), out)
    assert n == 2
    assert (out / "HR" / "2.pdf").read_bytes() == b"%PDF-fake 2"


def test_extract_refuses_paths_outside_out_dir(make_archive: MakeArchive, tmp_path: Path) -> None:
    archive = make_archive([("1", "ARTS", "a")])
    evil = kaggle.ResumeRecord("1", "../escape", "a", "data/data/ARTS/1.pdf")
    with pytest.raises(kaggle.DatasetError, match="outside"):
        kaggle.extract_pdfs(archive, [evil], tmp_path / "pdf")


# ------------------------------------------------------------------ profile


def test_profile_counts_contacts_and_duplicates() -> None:
    records = [
        kaggle.ResumeRecord("1", "ARTS", "mail me: a.b@example.com", "x"),
        kaggle.ResumeRecord("2", "ARTS", "call +91 98450 12345 today", "x"),
        kaggle.ResumeRecord("3", "HR", "   ", "x"),
    ]
    dup = [kaggle.Duplicate("4", "1")]
    p = kaggle.profile(records, dup)
    assert (p.total_rows, p.unique_records, p.duplicates_dropped) == (4, 3, 1)
    assert (p.with_email, p.with_phone, p.empty_texts) == (1, 1, 1)
    assert p.categories == {"ARTS": 2, "HR": 1}


def test_rendered_profile_contains_no_resume_text() -> None:
    secret = "UNIQUE-RESUME-CONTENT-123"
    records = [kaggle.ResumeRecord("1", "ARTS", secret, "x")]
    report = kaggle.render_profile(kaggle.profile(records, []), None)
    assert secret not in report
    assert "| ARTS | 1 |" in report
