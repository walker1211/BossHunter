"""Conservative work-schedule claims from postings and company profiles."""

from __future__ import annotations

import re


_PATTERNS = (
    ("alternate", re.compile(r"大小周|单双休")),
    ("single", re.compile(r"单休|做六休一|每周(?:工作|上班)六天|每周休息[一1]天|周休[一1]天")),
    ("double", re.compile(r"双休|周休(?:两|二|2)天|每周休息(?:两|二|2)天|做五休二")),
)
_NEGATION = re.compile(r"(?:不|非|无|没有|不是|并非|否定|不实行|取消|不保证|无法保证|不能保证|不一定)\s*$")


def _claim(text: str) -> tuple[str, str]:
    """Classify one source, returning its label and a short original excerpt."""
    matches: list[tuple[str, re.Match[str]]] = []
    for schedule, pattern in _PATTERNS:
        matches.extend((schedule, match) for match in pattern.finditer(text))
    alternate_spans = [match.span() for schedule, match in matches if schedule == "alternate"]
    matches = [
        (schedule, match) for schedule, match in matches
        if schedule == "alternate" or not any(start <= match.start() < end for start, end in alternate_spans)
    ]
    if not matches:
        return "unknown", ""
    positive: set[str] = set()
    negative: set[str] = set()
    for schedule, match in matches:
        if _NEGATION.search(text[max(0, match.start() - 8):match.start()]):
            negative.add(schedule)
        else:
            positive.add(schedule)
    first = min(matches, key=lambda item: item[1].start())[1]
    evidence = text[max(0, first.start() - 16):min(len(text), first.end() + 24)]
    if len(positive) > 1 or (not positive and negative) or positive & negative:
        return "unclear", evidence
    if positive:
        return next(iter(positive)), evidence
    return "unknown", ""


def infer_work_schedule(title: str = "", jd: str = "", company_text: str = "") -> tuple[str, str, str]:
    """Return (schedule, source, evidence), preferring any posting claim."""
    posting = " ".join(str(value or "").strip() for value in (title, jd)).strip()
    schedule, evidence = _claim(posting)
    if schedule != "unknown":
        return schedule, "job_posting", evidence
    company = " ".join(str(company_text or "").split())
    schedule, evidence = _claim(company)
    if schedule != "unknown":
        return schedule, "company_profile", evidence
    return "unknown", "", ""
