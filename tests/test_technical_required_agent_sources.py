"""Source validation at the live scoring and Agent entry points, using mocks only."""

import json
from unittest.mock import patch

import pytest

from bosshunter.agent_api import validate_agent_evaluations
from bosshunter.ai import scorer


def _payload(quote="我无法独立完成 Linux 部署"):
    return {
        **{key: {"score": score, "evidence": "虚构项目证据"} for key, score in zip(
            scorer.COMPONENT_LIMITS, (35, 23, 8, 8, 10),
        )},
        "caps": ["technical_required"],
        "technical_required_assessment": {
            "requirement": "必须独立完成 Linux 部署",
            "is_core_required": True,
            "evidence_status": "not_met",
            "candidate_evidence": quote,
            "blocks_core_work": True,
            "blocking_reason": "核心交付依赖独立部署",
        },
        "hard_gaps": ["明确无法独立部署"],
        "reason": "独立部署能力不足",
        "missing": "独立部署",
    }


JOB = {
    "id": "fictional-source-job", "company": "虚构公司", "title": "后端工程师",
    "salary": "25-35K", "experience": "3-5年", "jd": "必须独立完成 Linux 部署",
}


@pytest.mark.parametrize("resume,expected", [
    ("我无法独立完成 Linux 部署", 55),
    ("后端开发多年，部署经历未写", 84),
])
def test_primary_ai_scoring_binds_the_blocker_to_the_actual_resume(resume, expected):
    with patch.object(scorer, "_call_claude", return_value=json.dumps(_payload())):
        outcome = scorer._score_job_with_ai(JOB, resume, {"ai": {"scoring_second_review": False}}, 1)
    assert outcome.result.score == expected


@pytest.mark.parametrize("resume,expected", [
    ("我无法独立完成 Linux 部署", 55),
    ("后端开发多年，部署经历未写", 84),
])
def test_agent_submission_uses_the_same_resume_source_guard(resume, expected):
    with patch.object(scorer, "_load_resume", return_value=resume):
        rows = validate_agent_evaluations(
            [{"job_id": JOB["id"], "score": _payload()}], 71,
            jobs_by_id={JOB["id"]: JOB}, config={},
        )
    assert rows[0]["score"] == expected
    assert rows[0]["passed"] is (expected >= 71)


def test_positive_verbatim_evidence_cannot_be_relabelled_as_not_met():
    evidence = "我熟悉 Linux 并独立部署过多个服务"
    result = scorer.validate_structured_score_payload(_payload(evidence), job=JOB, resume=evidence)
    assert result.score == result.raw_score == 84
    assert result.technical_cap_rejected


def test_or_requirement_with_a_supported_alternative_remains_uncapped():
    payload = _payload()
    payload["technical_required_assessment"].update({
        "requirement": "熟悉 Go 或 Java", "evidence_status": "met",
        "candidate_evidence": "熟悉 Go，不会 Java",
    })
    result = scorer.validate_structured_score_payload(
        payload, job={"jd": "熟悉 Go 或 Java"}, resume="熟悉 Go，不会 Java",
    )
    assert result.score == result.raw_score


def test_agent_validation_does_not_read_resume_for_ordinary_scores():
    payload = _payload()
    payload["caps"] = []
    with patch.object(scorer, "_load_resume", side_effect=AssertionError("unexpected_resume_read")):
        rows = validate_agent_evaluations([{"job_id": JOB["id"], "score": payload}], 71)
    assert rows[0]["score"] == 84
