"""Gold set: Label Studio tasks out, Label Studio export in.

`build_tasks` turns the frozen gold IDs into a Label Studio import file.
`convert_export` turns a Label Studio JSON export into one structured gold
record per resume, and refuses exports that break the labeling guide's
rules (docs/LABELING_GUIDE.md), so a sloppy label can't silently become
"ground truth".

Gold files contain resume text and stay in git-ignored data/ (ADR-007).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from itertools import chain
from typing import Any, Literal

Split = Literal["gold_validation", "gold_test"]

ENTRY_CHILDREN: dict[str, tuple[str, ...]] = {
    "JOB_ENTRY": ("JOB_TITLE", "COMPANY", "JOB_DATES"),
    "EDU_ENTRY": ("DEGREE", "INSTITUTION", "EDU_DATES"),
}
STANDALONE = ("SKILL", "CERTIFICATION", "LOCATION")
ALL_LABELS = frozenset(chain(ENTRY_CHILDREN, STANDALONE, *ENTRY_CHILDREN.values()))
_PARENT_OF = {child: parent for parent, kids in ENTRY_CHILDREN.items() for child in kids}


class GoldError(Exception):
    """The export breaks the labeling rules. The message lists every problem."""


# ------------------------------------------------------------------ tasks


def build_tasks(
    records: Iterable[Mapping[str, Any]],
    gold_validation: Iterable[str],
    gold_test: Iterable[str],
) -> list[dict[str, Any]]:
    """Label Studio import format, validation resumes first (label those first)."""
    split_of: dict[str, Split] = {rid: "gold_test" for rid in gold_test}
    split_of.update({rid: "gold_validation" for rid in gold_validation})
    by_id = {str(r["id"]): r for r in records}

    missing = sorted(set(split_of) - set(by_id), key=int)
    if missing:
        raise GoldError(f"gold IDs not found in records: {missing[:10]}")

    order = sorted(split_of, key=lambda rid: (split_of[rid] != "gold_validation", int(rid)))
    return [
        {
            "data": {
                "id": rid,
                "category": by_id[rid]["category"],
                "split": split_of[rid],
                "text": by_id[rid]["text"],
            }
        }
        for rid in order
    ]


# ------------------------------------------------------------------ convert


@dataclass(frozen=True, slots=True)
class Span:
    start: int
    end: int
    label: str
    text: str

    def inside(self, other: Span) -> bool:
        return other.start <= self.start and self.end <= other.end


@dataclass
class Entry:
    fields: dict[str, str | None]
    start: int
    end: int


@dataclass
class GoldRecord:
    id: str
    category: str
    split: str
    usable: bool
    skills: list[str] = field(default_factory=list)
    jobs: list[dict[str, str | None]] = field(default_factory=list)
    education: list[dict[str, str | None]] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    location: str | None = None
    notes: str = ""
    spans: list[Span] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass(frozen=True)
class ConversionReport:
    records: int
    usable: int
    label_counts: dict[str, int]
    jobs: int
    education: int


def convert_export(
    tasks: list[Mapping[str, Any]], expected_ids: Iterable[str] | None = None
) -> tuple[list[GoldRecord], ConversionReport]:
    problems: list[str] = []
    gold: list[GoldRecord] = []

    for task in tasks:
        data = task.get("data", {})
        rid = str(data.get("id", "?"))
        try:
            gold.append(_convert_task(task))
        except GoldError as e:
            problems.extend(f"resume {rid}: {p}" for p in str(e).splitlines())

    ids = [g.id for g in gold]
    dupes = sorted(rid for rid, n in Counter(ids).items() if n > 1)
    if dupes:
        problems.append(f"resumes labeled more than once: {dupes}")
    if expected_ids is not None:
        missing = sorted(set(expected_ids) - set(ids), key=int)
        if missing:
            problems.append(f"{len(missing)} gold resumes not labeled yet, e.g. {missing[:10]}")

    if problems:
        raise GoldError("\n".join(problems))

    counts = Counter(s.label for g in gold for s in g.spans)
    report = ConversionReport(
        records=len(gold),
        usable=sum(g.usable for g in gold),
        label_counts=dict(sorted(counts.items())),
        jobs=sum(len(g.jobs) for g in gold),
        education=sum(len(g.education) for g in gold),
    )
    return sorted(gold, key=lambda g: int(g.id)), report


def _latest_annotation(task: Mapping[str, Any]) -> Mapping[str, Any]:
    annotations = [a for a in task.get("annotations", []) if not a.get("was_cancelled")]
    if not annotations:
        raise GoldError("no submitted annotation")
    return max(annotations, key=lambda a: str(a.get("updated_at", "")))


def _convert_task(task: Mapping[str, Any]) -> GoldRecord:
    data = task["data"]
    text: str = data["text"]
    annotation = _latest_annotation(task)

    spans: list[Span] = []
    quality: str | None = None
    notes = ""
    problems: list[str] = []

    for item in annotation.get("result", []):
        kind, value = item.get("type"), item.get("value", {})
        if kind == "labels":
            for label in value.get("labels", []):
                start, end = int(value["start"]), int(value["end"])
                if label not in ALL_LABELS:
                    problems.append(f"unknown label {label!r}")
                elif not 0 <= start < end <= len(text):
                    problems.append(f"{label} span {start}-{end} outside the text")
                else:
                    spans.append(Span(start, end, label, text[start:end].strip()))
        elif kind == "choices" and item.get("from_name") == "quality":
            quality = (value.get("choices") or [None])[0]
        elif kind == "textarea" and item.get("from_name") == "notes":
            notes = " ".join(value.get("text", []))

    if quality not in ("usable", "unusable"):
        problems.append("usable/unusable not chosen")

    spans.sort(key=lambda s: (s.start, -s.end))
    entries: dict[str, list[tuple[Span, Entry]]] = {p: [] for p in ENTRY_CHILDREN}
    for s in spans:
        if s.label in ENTRY_CHILDREN:
            entries[s.label].append(
                (s, Entry(dict.fromkeys(ENTRY_CHILDREN[s.label]), s.start, s.end))
            )

    for s in spans:
        parent = _PARENT_OF.get(s.label)
        if parent is None:
            continue
        holders = [e for span, e in entries[parent] if s.inside(span)]
        if len(holders) != 1:
            where = "no" if not holders else "more than one"
            problems.append(f'{s.label} "{s.text[:40]}" is inside {where} {parent}')
            continue
        entry = holders[0]
        if entry.fields[s.label] is not None:
            problems.append(f'{parent} at {entry.start} has two {s.label} spans ("{s.text[:40]}")')
            continue
        entry.fields[s.label] = s.text

    for parent, items in entries.items():
        for span, entry in items:
            if all(v is None for v in entry.fields.values()):
                problems.append(f'{parent} "{span.text[:40]}" has no labeled fields inside it')

    locations = [s.text for s in spans if s.label == "LOCATION"]
    if len(locations) > 1:
        problems.append("more than one LOCATION (label only the candidate's own location)")

    if problems:
        raise GoldError("\n".join(problems))

    def unique(label: str) -> list[str]:
        seen: dict[str, str] = {}
        for s in spans:
            if s.label == label:
                seen.setdefault(" ".join(s.text.lower().split()), s.text)
        return list(seen.values())

    return GoldRecord(
        id=str(data["id"]),
        category=str(data.get("category", "")),
        split=str(data.get("split", "")),
        usable=quality == "usable",
        skills=unique("SKILL"),
        jobs=[
            {
                "title": e.fields["JOB_TITLE"],
                "company": e.fields["COMPANY"],
                "dates": e.fields["JOB_DATES"],
            }
            for _, e in entries["JOB_ENTRY"]
        ],
        education=[
            {
                "degree": e.fields["DEGREE"],
                "institution": e.fields["INSTITUTION"],
                "dates": e.fields["EDU_DATES"],
            }
            for _, e in entries["EDU_ENTRY"]
        ],
        certifications=unique("CERTIFICATION"),
        location=locations[0] if locations else None,
        notes=notes,
        spans=spans,
    )
