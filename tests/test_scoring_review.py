"""Manual review and manual-filter preservation for fictional jobs."""

import json
import sqlite3

from bosshunter.scoring_review import (
    get_manual_company_review,
    is_manually_filtered,
    preserve_manual_review_reason,
    score_reason_body,
)


def _database() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE jobs (id TEXT PRIMARY KEY, status TEXT);
        CREATE TABLE history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT
        );
        INSERT INTO jobs (id, status) VALUES ('job-a', 'filtered'), ('job-b', 'pending');
        """
    )
    return conn


def _history(conn: sqlite3.Connection, job_id: str, action: str, detail: str | None) -> None:
    conn.execute(
        "INSERT INTO history (job_id, action, detail) VALUES (?, ?, ?)",
        (job_id, action, detail),
    )


def test_latest_valid_company_review_skips_other_and_malformed_history() -> None:
    conn = _database()
    try:
        _history(
            conn,
            "job-a",
            "manual_intake",
            json.dumps({"type": "manual_company_review", "recommendation": "low_priority", "review": "旧复核"}),
        )
        _history(
            conn,
            "job-a",
            "manual_intake",
            json.dumps(
                {
                    "type": "manual_company_review",
                    "recommendation": "low_priority",
                    "review": "新复核：主体关系待核，薪资只覆盖目标下沿。",
                    "internal_evidence": "不应进入评分输入",
                }
            ),
        )
        for detail in (
            "{broken",
            None,
            "[]",
            json.dumps({"type": "manual_company_review", "review": "  "}),
            json.dumps({"type": "other_note", "review": "无关备注"}),
        ):
            _history(conn, "job-a", "manual_intake", detail)
        _history(conn, "job-a", "status_changed", "用户手动将状态从 ready 修改为 filtered")
        assert get_manual_company_review(conn, "job-a") == {
            "type": "manual_company_review",
            "recommendation": "low_priority",
            "review": "新复核：主体关系待核，薪资只覆盖目标下沿。",
        }
        assert get_manual_company_review(conn, "job-b") is None
    finally:
        conn.close()


def test_non_string_recommendation_is_omitted_without_losing_review() -> None:
    conn = _database()
    try:
        _history(
            conn,
            "job-a",
            "manual_intake",
            json.dumps({"type": "manual_company_review", "recommendation": ["low_priority"], "review": "待核"}),
        )
        assert get_manual_company_review(conn, "job-a") == {
            "type": "manual_company_review",
            "recommendation": "",
            "review": "待核",
        }
    finally:
        conn.close()


def test_review_prefix_is_preserved_once() -> None:
    conn = _database()
    try:
        _history(
            conn,
            "job-a",
            "manual_intake",
            json.dumps({"type": "manual_company_review", "recommendation": "low_priority", "review": "人工复核：待核实用工主体"}),
        )
        reason = preserve_manual_review_reason(conn, "job-a", "技术匹配良好")
        assert reason == "人工复核：待核实用工主体\n\n【本次评分理由】\n技术匹配良好"
        assert preserve_manual_review_reason(conn, "job-a", reason) == reason
        assert preserve_manual_review_reason(conn, "job-b", "无人工复核") == "无人工复核"
    finally:
        conn.close()


def test_score_reason_body_unwraps_latest_scoring_section() -> None:
    assert score_reason_body(None) == ""
    assert score_reason_body("  AI评分失败: 超时  ") == "AI评分失败: 超时"
    assert score_reason_body("人工复核\n\n【本次评分理由】\n 预筛不通过: 必备条件不符 ") == "预筛不通过: 必备条件不符"
    assert score_reason_body("人工复核\n\n【本次评分理由】\n \n") == ""
    assert score_reason_body("旧段\n\n【本次评分理由】\n过渡段\n\n【本次评分理由】\n最终段") == "最终段"


def test_manual_filter_requires_current_status_and_latest_manual_choice() -> None:
    conn = _database()
    try:
        assert is_manually_filtered(conn, "missing") is False
        assert is_manually_filtered(conn, "job-a") is False
        _history(conn, "job-a", "status_changed", "用户手动将状态从 ready 修改为 filtered")
        _history(conn, "job-a", "auto_scored", "自动流程记录")
        assert is_manually_filtered(conn, "job-a") is True

        _history(conn, "job-a", "status_changed", "用户手动将状态从 filtered 修改为 pending")
        assert is_manually_filtered(conn, "job-a") is False
        _history(conn, "job-a", "status_changed", "用户手动将状态从 pending 修改为 filtered")
        assert is_manually_filtered(conn, "job-a") is True

        conn.execute("UPDATE jobs SET status = 'ready' WHERE id = 'job-a'")
        assert is_manually_filtered(conn, "job-a") is False
        _history(conn, "job-b", "status_changed", "用户手动将状态从 ready 修改为 filtered")
        assert is_manually_filtered(conn, "job-b") is False
    finally:
        conn.close()


def test_uncontrolled_status_details_do_not_count_as_manual_filter() -> None:
    details = (
        None,
        "",
        "自动筛选为 filtered",
        "用户手动将状态从 ready 修改为 ready",
        "用户手动将状态从  修改为 filtered",
        "用户手动将状态从 ready 修改为 filtered 后又恢复",
    )
    for detail in details:
        conn = _database()
        try:
            _history(conn, "job-a", "status_changed", detail)
            assert is_manually_filtered(conn, "job-a") is False
        finally:
            conn.close()
