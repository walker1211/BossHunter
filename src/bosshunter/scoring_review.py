"""Read manual company reviews and status decisions used by job scoring."""

import json
import sqlite3


_SCORE_REASON_SEPARATOR = "\n\n【本次评分理由】\n"


def score_reason_body(reason: str | None) -> str:
    """Return the actual scoring reason without the displayed company review."""
    return (reason or "").rsplit(_SCORE_REASON_SEPARATOR, 1)[-1].strip()


def get_manual_company_review(conn: sqlite3.Connection, job_id: str) -> dict[str, str] | None:
    """Return the latest valid manual company review for a job."""
    rows = conn.execute(
        """SELECT detail FROM history
           WHERE job_id = ? AND action = 'manual_intake'
           ORDER BY id DESC""",
        (job_id,),
    )
    for (detail,) in rows:
        try:
            record = json.loads(detail)
        except (TypeError, ValueError):
            continue
        if not isinstance(record, dict) or record.get("type") != "manual_company_review":
            continue
        review = record.get("review")
        if not isinstance(review, str) or not review.strip():
            continue
        recommendation = record.get("recommendation")
        return {
            "type": "manual_company_review",
            "recommendation": recommendation if isinstance(recommendation, str) else "",
            "review": review,
        }
    return None


def preserve_manual_review_reason(conn: sqlite3.Connection, job_id: str, reason: str) -> str:
    """Keep the recorded company review visible above a new scoring reason."""
    record = get_manual_company_review(conn, job_id)
    if record is None:
        return reason
    review = record["review"]
    if reason.startswith(review):
        return reason
    return f"{review}{_SCORE_REASON_SEPARATOR}{reason}"


def is_manually_filtered(conn: sqlite3.Connection, job_id: str) -> bool:
    """Whether the current filtered status was the latest manual status choice."""
    row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None or row[0] != "filtered":
        return False
    last_change = conn.execute(
        """SELECT detail FROM history
           WHERE job_id = ? AND action = 'status_changed'
           ORDER BY id DESC LIMIT 1""",
        (job_id,),
    ).fetchone()
    if last_change is None or not isinstance(last_change[0], str):
        return False
    detail = last_change[0]
    prefix = "用户手动将状态从 "
    suffix = " 修改为 filtered"
    return (
        detail.startswith(prefix)
        and detail.endswith(suffix)
        and bool(detail[len(prefix) : -len(suffix)].strip())
    )
