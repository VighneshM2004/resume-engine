"""Command line for data preparation. Called by `make data` / `make splits`.

resume-ml data      verify archive, extract PDFs, write records + profile
resume-ml splits    create the frozen split file (refuses to overwrite)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from resume_ml.data import kaggle

DEFAULT_ARCHIVE = Path("data/raw/kaggle-resume-dataset.zip")
DEFAULT_OUT = Path("data/interim/kaggle")
DEFAULT_SPLITS = Path("ml/splits/kaggle_v1.json")
DEFAULT_PROFILE = Path("ml/reports/kaggle_profile.md")


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
