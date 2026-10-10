import json
from unittest.mock import patch

import pytest

from bosshunter.ai import scorer
from bosshunter.db import (
    add_history, get_db, get_funnel_stats, get_score_trace, insert_job, persist_job_score_and_trace,
    reset_ai_filtered_jobs, update_job_score, update_job_status, update_jobs_manual_status,
)


def _job(job_id):
    return {
        "id": job_id, "title": "后端工程师", "company": "示例软件公司", "salary": "18-25K",
        "city": "示例城市", "experience": "3-5年", "jd": "负责后端服务开发",
        "hr_name": "HR", "hr_title": "招聘", "hr_active": "active",
        "company_size": "20-99", "company_industry": "软件", "url": f"https://example.com/{job_id}",
    }


def _review(db, job_id, recommendation="low_priority"):
    add_history(db, job_id, "manual_intake", json.dumps({
        "type": "manual_company_review", "recommendation": recommendation,
        "review": "人工复核：用工主体关系待核，不能作为稳定性背书。",
    }, ensure_ascii=False))


def _response():
    return json.dumps({
        **{key: {"score": value, "evidence": "有相关项目证据"} for key, value in zip(
            scorer.COMPONENT_LIMITS, (34, 23, 12, 8, 10),
        )},
        "reason": "后端交付经验相关", "caps": [], "hard_gaps": [], "missing": "",
    }, ensure_ascii=False)


@pytest.mark.parametrize("recommendation,expected_score", [("low_priority", 65), ("needs_review", 83)])
def test_forced_rescore_keeps_manual_exclusion_notes_and_unrelated_job(
    tmp_path, recommendation, expected_score,
):
    path = tmp_path / "review.db"
    db = get_db(path)
    insert_job(db, _job("reviewed"))
    insert_job(db, _job("untouched"))
    update_job_score(db, "reviewed", 87, "历史技术匹配")
    update_job_status(db, "reviewed", "ready")
    update_jobs_manual_status(db, ["reviewed"], "filtered")
    _review(db, "reviewed", recommendation)
    before = dict(db.execute("SELECT * FROM jobs WHERE id='untouched'").fetchone())
    db.close()
    config = {"profile": {"salary_min": 24, "salary_max": 30}, "scoring": {"threshold": 71}}
    with (
        patch.object(scorer, "get_db", side_effect=lambda: get_db(path)),
        patch.object(scorer, "_load_resume", return_value="虚构候选人有后端交付经历"),
        patch.object(scorer, "quick_score", return_value=(80, "通过")),
        patch.object(scorer, "_call_claude", return_value=_response()) as call_ai,
    ):
        counts = scorer.score_jobs(config, scope="selected", job_ids=["reviewed"], force_rescore=True)
    db = get_db(path)
    try:
        row = dict(db.execute("SELECT * FROM jobs WHERE id='reviewed'").fetchone())
        assert counts == (0, 1)
        assert row["status"] == "filtered"
        assert row["score"] == expected_score
        assert row["score_reason"].startswith("人工复核：用工主体关系待核")
        assert row["score_reason"].count("人工复核：") == 1
        assert "用工主体关系待核" in call_ai.call_args.args[0]
        assert get_score_trace(db, "reviewed")[1]["final_score"] == expected_score
        assert dict(db.execute("SELECT * FROM jobs WHERE id='untouched'").fetchone()) == before
    finally:
        db.close()


def test_reset_ai_filtered_jobs_skips_manual_filter_and_keeps_review(tmp_path):
    db = get_db(tmp_path / "reset.db")
    try:
        for job_id in ("manual", "automatic"):
            insert_job(db, _job(job_id))
            _review(db, job_id)
            update_job_score(db, job_id, 65, "历史匹配")
        update_jobs_manual_status(db, ["manual"], "filtered")
        update_job_status(db, "automatic", "filtered")
        before = dict(db.execute("SELECT * FROM jobs WHERE id='manual'").fetchone())
        assert reset_ai_filtered_jobs(db) == 1
        assert dict(db.execute("SELECT * FROM jobs WHERE id='manual'").fetchone()) == before
        row = db.execute("SELECT status, score, score_reason FROM jobs WHERE id='automatic'").fetchone()
        assert row["status"] == "pending" and row["score"] == 0
        assert row["score_reason"].startswith("人工复核：")
    finally:
        db.close()


def test_review_wrapped_failures_are_not_reset_or_counted_as_ai_scores(tmp_path):
    db = get_db(tmp_path / "wrapped-reasons.db")
    try:
        reasons = {
            "wrapped-prefilter": "预筛不通过: 必备条件不符",
            "wrapped-ai-failure": "AI评分失败: 暂时不可用",
            "wrapped-ai-spaced": "AI 评分失败: 暂时不可用",
            "wrapped-old-failure": "评分失败: 暂时不可用",
            "wrapped-empty": "",
            "plain-prefilter": "预筛不通过: 必备条件不符",
            "plain-ai-failure": "AI评分失败: 暂时不可用",
            "plain-ai-spaced": "AI 评分失败: 暂时不可用",
            "plain-old-failure": "评分失败: 暂时不可用",
            "plain-empty": "",
            "wrapped-low-score": "职责30/40；实际匹配待提升",
            "plain-low-score": "职责30/40；实际匹配待提升",
            "deleted-low-score": "职责30/40；实际匹配待提升",
        }
        for job_id, reason in reasons.items():
            insert_job(db, _job(job_id))
            if job_id.startswith("wrapped-"):
                _review(db, job_id, recommendation="needs_review")
            update_job_score(db, job_id, 68 if "low-score" in job_id else 0, reason)
            update_job_status(db, job_id, "filtered")
        insert_job(db, _job("ready"))
        update_job_score(db, "ready", 80, "匹配")
        update_job_status(db, "ready", "ready")
        db.execute("UPDATE jobs SET created_at = datetime('now', '-1 day') WHERE id = 'wrapped-low-score'")
        db.execute("UPDATE jobs SET deleted_at = CURRENT_TIMESTAMP WHERE id = 'deleted-low-score'")
        db.commit()

        before_failures = {
            job_id: dict(db.execute("SELECT status, score, score_reason FROM jobs WHERE id = ?", (job_id,)).fetchone())
            for job_id in reasons if "low-score" not in job_id
        }
        assert get_funnel_stats(db)["AI评分"] == 3  # two low scores and one ready job
        assert get_funnel_stats(db, today=True)["AI评分"] == 2  # old wrapped score is outside today's scope
        assert reset_ai_filtered_jobs(db) == 2
        assert all(
            dict(db.execute("SELECT status, score, score_reason FROM jobs WHERE id = ?", (job_id,)).fetchone()) == previous
            for job_id, previous in before_failures.items()
        )
        for job_id in ("wrapped-low-score", "plain-low-score"):
            row = db.execute("SELECT status, score FROM jobs WHERE id = ?", (job_id,)).fetchone()
            assert (row["status"], row["score"]) == ("pending", 0)
    finally:
        db.close()


def test_failure_and_prefilter_preserve_manual_review_and_prior_trace(tmp_path):
    db = get_db(tmp_path / "failure.db")
    try:
        insert_job(db, _job("reviewed"))
        _review(db, "reviewed")
        result = scorer.validate_structured_score_payload(json.loads(_response()))
        trace = scorer.build_score_trace(result)
        persist_job_score_and_trace(db, "reviewed", result.score, result.reason, trace)
        for reason in ("AI评分失败: 服务暂时不可用", "预筛不通过: 当前条件不合"):
            update_job_score(db, "reviewed", 0, reason)
            stored = db.execute("SELECT score_reason FROM jobs WHERE id='reviewed'").fetchone()[0]
            assert stored.startswith("人工复核：") and reason in stored
            assert get_score_trace(db, "reviewed")[1] == trace
    finally:
        db.close()
