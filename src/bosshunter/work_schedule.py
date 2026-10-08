"""Conservative work-schedule claims extracted from saved job postings.

These labels describe what a posting says, not an independently verified policy.
"""

from __future__ import annotations

import re


_PATTERNS = (
    ("alternate", re.compile(r"大小周|单双休")),
    ("single", re.compile(r"单休|做六休一|每周(?:工作|上班)六天")),
    ("double", re.compile(r"双休|周休两天")),
)
_NEGATED_DOUBLE = re.compile(r"(?:不|非|无|没有|不保证|无法保证|不能保证|不一定)\s*双休|单双休")


def infer_work_schedule(title: str = "", jd: str = "") -> tuple[str, str, str]:
    """Return (schedule, source, evidence); unknown never implies double rest."""
    text = " ".join(f"{title or ''} {jd or ''}".split())
    if not text:
        return "unknown", "", ""

    matches: list[tuple[str, re.Match[str]]] = []
    for schedule, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            if schedule == "double" and _NEGATED_DOUBLE.search(text[max(0, match.start() - 8):match.end()]):
                continue
            matches.append((schedule, match))
    if not matches:
        return "unknown", "", ""

    schedules = {schedule for schedule, _ in matches}
    first = min(matches, key=lambda item: item[1].start())[1]
    evidence = text[max(0, first.start() - 24):min(len(text), first.end() + 40)]
    if len(schedules) > 1:
        return "unclear", "job_posting", evidence
    return next(iter(schedules)), "job_posting", evidence
