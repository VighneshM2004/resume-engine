"""Command line for data preparation. Called by `make data` / `make splits`.

resume-ml data      verify archive, extract PDFs, write records + profile
resume-ml splits    create the frozen split file (refuses to overwrite)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from resume_ml.data import kaggle
from resume_ml.labeling import gold

DEFAULT_ARCHIVE = Path("data/raw/kaggle-resume-dataset.zip")
DEFAULT_OUT = Path("data/interim/kaggle")
DEFAULT_SPLITS = Path("ml/splits/kaggle_v1.json")
DEFAULT_PROFILE = Path("ml/reports/kaggle_profile.md")
DEFAULT_RECORDS = DEFAULT_OUT / "records.jsonl"
DEFAULT_TASKS = Path("data/labeling/gold_tasks.json")
DEFAULT_GOLD = Path("data/gold/kaggle_gold_v1.jsonl")


def _load(archive: Path) -> tuple[list[kaggle.ResumeRecord], list[kaggle.Duplicate]]:
    print(f"verifying {archive} ...")
    kaggle.verify_archive(archive)
    records = kaggle.read_records(archive)
    unique, duplicates = kaggle.deduplicate(records)
    print(f"{len(records)} rows, {len(duplicates)} exact duplicates, {len(unique)} unique")
    return unique, duplicates


def cmd_data(args: argparse.Namespace) -> int:
    records, duplicates = _load(args.archive)

    splits = None
    if args.splits.exists():
        splits = kaggle.Splits.from_json(args.splits.read_text(encoding="utf-8"))
        problems = kaggle.check_splits(splits, records)
        if problems:
            print("frozen splits don't match the dataset:", *problems, sep="\n  ")
            return 1
        print(f"frozen splits OK ({args.splits})")
    else:
        print(f"no frozen splits yet: run `make splits` to create {args.splits}")

    n = kaggle.extract_pdfs(args.archive, records, args.out / "pdf")
    kaggle.write_records_jsonl(records, args.out / "records.jsonl")
    dup_lines = [f"{d.dropped_id}\t{d.kept_id}" for d in duplicates]
    (args.out / "duplicates.tsv").write_text(
        "dropped_id\tkept_id\n" + "".join(f"{line}\n" for line in dup_lines), encoding="utf-8"
    )
    args.profile.parent.mkdir(parents=True, exist_ok=True)
    args.profile.write_text(
        kaggle.render_profile(kaggle.profile(records, duplicates), splits), encoding="utf-8"
    )
    print(f"extracted {n} PDFs to {args.out / 'pdf'}")
    print(f"wrote {args.out / 'records.jsonl'}, {args.out / 'duplicates.tsv'}, {args.profile}")
    return 0


def cmd_splits(args: argparse.Namespace) -> int:
    if args.splits.exists():
        print(
            f"{args.splits} already exists and is frozen. Delete it only if you "
            "accept that every metric reported so far becomes invalid."
        )
        return 1
    records, _ = _load(args.archive)
    splits = kaggle.make_splits(records)
    args.splits.parent.mkdir(parents=True, exist_ok=True)
    args.splits.write_text(splits.to_json(), encoding="utf-8")
    print(
        f"wrote {args.splits}: {len(splits.gold_validation)} validation, "
        f"{len(splits.gold_test)} test, {len(splits.train)} train"
    )
    return 0


def _read_splits(path: Path) -> kaggle.Splits:
    if not path.exists():
        raise kaggle.DatasetError(f"{path} not found: run `make splits` first")
    return kaggle.Splits.from_json(path.read_text(encoding="utf-8"))


def cmd_label_tasks(args: argparse.Namespace) -> int:
    splits = _read_splits(args.splits)
    if not args.records.exists():
        raise kaggle.DatasetError(f"{args.records} not found: run `make data` first")
    with args.records.open(encoding="utf-8") as f:
        records = [json.loads(line) for line in f]
    tasks = gold.build_tasks(records, splits.gold_validation, splits.gold_test)
    args.tasks.parent.mkdir(parents=True, exist_ok=True)
    args.tasks.write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(tasks)} tasks to {args.tasks} (validation first)")
    return 0


def cmd_label_import(args: argparse.Namespace) -> int:
    splits = _read_splits(args.splits)
    tasks = json.loads(args.export.read_text(encoding="utf-8"))
    expected = None if args.partial else [*splits.gold_validation, *splits.gold_test]
    try:
        records, report = gold.convert_export(tasks, expected)
    except gold.GoldError as e:
        print("export breaks the labeling rules; fix these in Label Studio:", file=sys.stderr)
        print("  " + str(e).replace("\n", "\n  "), file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(r.to_json() + "\n" for r in records), encoding="utf-8")
    print(f"wrote {report.records} gold records ({report.usable} usable) to {args.out}")
    print(f"jobs: {report.jobs}, education entries: {report.education}")
    for label, n in report.label_counts.items():
        print(f"  {label:<14} {n}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="resume-ml")
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    sub = parser.add_subparsers(dest="command", required=True)

    data = sub.add_parser("data", help="verify, extract and profile the Kaggle dataset")
    data.add_argument("--out", type=Path, default=DEFAULT_OUT)
    data.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    data.set_defaults(func=cmd_data)

    splits = sub.add_parser("splits", help="create the frozen gold/train split file")
    splits.set_defaults(func=cmd_splits)

    tasks = sub.add_parser("label-tasks", help="write the Label Studio import file")
    tasks.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    tasks.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    tasks.set_defaults(func=cmd_label_tasks)

    imp = sub.add_parser("label-import", help="validate a Label Studio export")
    imp.add_argument("export", type=Path, help="JSON export from Label Studio")
    imp.add_argument("--out", type=Path, default=DEFAULT_GOLD)
    imp.add_argument(
        "--partial", action="store_true", help="allow unlabeled gold resumes (mid-way checks)"
    )
    imp.set_defaults(func=cmd_label_import)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code: int = args.func(args)
    except kaggle.DatasetError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return code


if __name__ == "__main__":
    raise SystemExit(main())
