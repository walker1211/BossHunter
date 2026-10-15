"""Evidence threshold and review behavior for the technical_required cap.

All job and resume text here is fictional. No model or job database is used.
"""

import json
from unittest.mock import patch

import pytest

from bosshunter.ai import scorer
from bosshunter.ai.credentials import AIRequestError


REQUIREMENT = "必须独立完成 Linux 私有化部署"
EVIDENCE = "我只在 Windows 上开发，无法独立完成 Linux 私有化部署"
JOB = {
    "id": "fictional-job", "company": "虚构公司", "title": "后端工程师",
    "salary": "25-35K", "experience": "3-5年", "jd": REQUIREMENT,
}
RESUME = f"八年后端开发。{EVIDENCE}。"


def _assessment(**changes):
    result = {
        "requirement": REQUIREMENT,
        "is_core_required": True,
        "evidence_status": "not_met",
        "candidate_evidence": EVIDENCE,
        "blocks_core_work": True,
        "blocking_reason": "岗位核心交付要求独立部署，当前无法承担",
    }
    result.update(changes)
    return result


def _payload(*, hard=12, caps=None, assessment=None):
    result = {
        "role_summary": "虚构后端岗位",
        "core_duties": {"score": 36, "evidence": "有后端交付经验"},
        "transferable_evidence": {"score": 22, "evidence": "有相邻经验"},
        "hard_requirements": {"score": hard, "evidence": "Linux 要求待核"},
        "tools_industry": {"score": 8, "evidence": "常用工具符合"},
        "practical_fit": {"score": 9, "evidence": "地点和薪资匹配"},
        "caps": ["technical_required"] if caps is None else caps,
        "hard_gaps": ["Linux 私有化部署需核实"],
        "reason": "后端经验匹配，专项部署能力需核实",
        "missing": "Linux 私有化部署",
    }
    if assessment is not None:
        result["technical_required_assessment"] = assessment
    return result


def _validated(payload, *, job=JOB, resume=RESUME):
    result = scorer.validate_structured_score_payload(payload, job=job, resume=resume)
    assert result is not None
    return result


def test_explicit_core_blocker_with_verbatim_sources_can_cap_at_55():
    result = _validated(_payload(assessment=_assessment()))

    assert result.raw_score == 87
    assert result.score == 55
    assert result.caps == ("technical_required",)
    assert result.technical_cap_requested is True
    assert result.technical_cap_rejected is False
    assert result.technical_assessment is not None


@pytest.mark.parametrize(
    "assessment,hard",
    [
        (None, 12),
        (_assessment(evidence_status="unverified"), 12),
        (_assessment(evidence_status="adjacent"), 12),
        (_assessment(evidence_status="met"), 12),
        (_assessment(is_core_required=False), 12),
        (_assessment(is_core_required=1), 12),
        (_assessment(blocks_core_work=False), 12),
        (_assessment(blocks_core_work=1), 12),
        (_assessment(blocking_reason=""), 12),
        (_assessment(candidate_evidence=""), 12),
        (_assessment(candidate_evidence="简历未体现 Linux 部署经历"), 12),
        (_assessment(candidate_evidence="待确认是否掌握 Linux 部署"), 12),
        (_assessment(candidate_evidence="not mentioned in resume"), 12),
        (_assessment(requirement=""), 12),
        (_assessment(candidate_evidence="熟悉 MySQL 与 Linux 部署"), 12),
        ([{"evidence_status": "not_met"}], 12),
        (_assessment(evidence_status={"value": "not_met"}), 12),
        (_assessment(), 15),
    ],
)
def test_unknown_or_nonblocking_evidence_never_caps(assessment, hard):
    result = _validated(_payload(hard=hard, assessment=assessment))

    assert result.score == result.raw_score
    assert result.caps == ()
    assert result.technical_cap_requested is True
    assert result.technical_cap_rejected is True
    assert result.component_evidence["hard_requirements"] == "Linux 要求待核"
    assert result.hard_gaps == ("待核：Linux 私有化部署需核实",)


@pytest.mark.parametrize(
    "job,resume,assessment",
    [
        ({**JOB, "jd": "熟悉常规后端开发"}, RESUME, _assessment()),
        (JOB, "有 Linux 部署项目经验", _assessment()),
        (JOB, RESUME, _assessment(requirement="必须掌握 Go")),
        (JOB, RESUME, _assessment(candidate_evidence="明确不会使用 Kubernetes")),
    ],
)
def test_claimed_source_quotes_must_match_actual_jd_and_resume(job, resume, assessment):
    result = _validated(_payload(assessment=assessment), job=job, resume=resume)
    assert result.score == result.raw_score
    assert result.caps == ()
    assert result.technical_cap_rejected is True


def test_parser_without_sources_still_checks_structured_evidence():
    valid = scorer.validate_structured_score_payload(_payload(assessment=_assessment()))
    unknown = scorer.validate_structured_score_payload(
        _payload(assessment=_assessment(candidate_evidence="简历没有写 Linux"))
    )
    assert valid is not None and valid.score == 55
    assert unknown is not None and unknown.score == unknown.raw_score


def test_json_parser_checks_sources_and_keeps_unknown_as_review_question():
    payload = _payload(assessment=_assessment(candidate_evidence="简历未体现 Linux 部署经历"))
    result = scorer._validated_score_result(json.dumps(payload, ensure_ascii=False), job=JOB, resume=RESUME)
    assert result is not None
    assert result.score == 87
    assert result.hard_gaps == ("待核：Linux 私有化部署需核实",)


def test_high_raw_technical_cap_is_reviewed_and_can_be_revoked():
    first = _validated(_payload(assessment=_assessment()))
    review = _payload(caps=[], assessment=None)
    review["hard_gaps"] = ["值班安排待核"]
    review["reason"] = "补核后技术要求仍需沟通"
    with (
        patch("bosshunter.ai.scorer._request_score", return_value=scorer.ScoreOutcome(result=first)),
        patch("bosshunter.ai.scorer._call_claude", return_value=json.dumps(review, ensure_ascii=False)) as call_ai,
    ):
        outcome = scorer._score_job_with_ai(JOB, RESUME, {"ai": {"scoring_second_review": True}}, 1)

    assert call_ai.call_count == 1
    assert outcome.result is not None
    assert outcome.result.reviewed is True
    assert outcome.result.score == 87
    assert outcome.result.caps == ()
    assert outcome.result.hard_gaps == ("值班安排待核",)


def test_rejected_high_raw_cap_still_receives_review():
    first = _validated(_payload(assessment=_assessment(evidence_status="unverified")))
    with (
        patch("bosshunter.ai.scorer._request_score", return_value=scorer.ScoreOutcome(result=first)),
        patch("bosshunter.ai.scorer._call_claude", return_value=json.dumps(_payload(caps=[]), ensure_ascii=False)) as call_ai,
    ):
        outcome = scorer._score_job_with_ai(JOB, RESUME, {"ai": {"scoring_second_review": True}}, 1)

    assert call_ai.call_count == 1
    assert outcome.result is not None and outcome.result.reviewed is True
    assert outcome.result.score == 87


def test_review_can_confirm_technical_blocker_and_preserves_other_caps():
    first = _validated(_payload(caps=["weak_core_transfer"], assessment=None))
    review = _payload(assessment=_assessment())
    with (
        patch("bosshunter.ai.scorer._request_score", return_value=scorer.ScoreOutcome(result=first)),
        patch("bosshunter.ai.scorer._call_claude", return_value=json.dumps(review, ensure_ascii=False)) as call_ai,
    ):
        outcome = scorer._score_job_with_ai(JOB, RESUME, {"ai": {"scoring_second_review": True}}, 1)

    assert call_ai.call_count == 1
    assert outcome.result is not None and outcome.result.reviewed is True
    assert outcome.result.score == 55
    assert outcome.result.caps == ("weak_core_transfer", "technical_required")


def test_review_does_not_accept_technical_blocker_with_unmatched_resume_quote():
    first = _validated(_payload(caps=["weak_core_transfer"], assessment=None))
    review = _payload(assessment=_assessment(candidate_evidence="我不会使用 Kubernetes"))
    with (
        patch("bosshunter.ai.scorer._request_score", return_value=scorer.ScoreOutcome(result=first)),
        patch("bosshunter.ai.scorer._call_claude", return_value=json.dumps(review, ensure_ascii=False)),
    ):
        outcome = scorer._score_job_with_ai(JOB, RESUME, {"ai": {"scoring_second_review": True}}, 1)

    assert outcome.result is not None and outcome.result.reviewed is True
    assert outcome.result.score == 70
    assert outcome.result.caps == ("weak_core_transfer",)


@pytest.mark.parametrize("response", [None, "", "not json", '{"score": 87}'])
def test_empty_or_invalid_review_preserves_first_score(response):
    first = _validated(_payload(assessment=_assessment()))
    with (
        patch("bosshunter.ai.scorer._request_score", return_value=scorer.ScoreOutcome(result=first)),
        patch("bosshunter.ai.scorer._call_claude", return_value=response),
        patch("bosshunter.ai.scorer._notify"),
    ):
        outcome = scorer._score_job_with_ai(JOB, RESUME, {"ai": {"scoring_second_review": True}}, 1)
    assert outcome.result == first


def test_service_level_review_failure_keeps_first_and_pauses():
    first = _validated(_payload(assessment=_assessment()))
    with (
        patch("bosshunter.ai.scorer._request_score", return_value=scorer.ScoreOutcome(result=first)),
        patch("bosshunter.ai.scorer._call_claude", side_effect=AIRequestError("rate_limit", "请求限流")),
    ):
        outcome = scorer._score_job_with_ai(JOB, RESUME, {"ai": {"scoring_second_review": True}}, 1)
    assert outcome.result == first
    assert outcome.pause_reason


def test_review_disabled_keeps_technical_cap_without_second_call():
    first = _validated(_payload(assessment=_assessment()))
    with (
        patch("bosshunter.ai.scorer._request_score", return_value=scorer.ScoreOutcome(result=first)),
        patch("bosshunter.ai.scorer._call_claude") as call_ai,
    ):
        outcome = scorer._score_job_with_ai(JOB, RESUME, {"ai": {"scoring_second_review": False}}, 1)
    call_ai.assert_not_called()
    assert outcome.result is not None and outcome.result.score == 55
