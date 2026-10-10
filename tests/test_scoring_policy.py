"""Business outcomes for job-aware scoring with fictional vacancies."""

import pytest

from bosshunter.agent_api import AgentRequestError, validate_agent_evaluations
from bosshunter.ai import scorer


def _payload(*, hard: int = 8, practical: int = 10, caps: list[str] | None = None) -> dict:
    return {
        "role_summary": "虚构后端岗位",
        "core_duties": {"score": 34, "evidence": "有后端交付记录"},
        "transferable_evidence": {"score": 23, "evidence": "有可迁移项目"},
        "hard_requirements": {"score": hard, "evidence": "关键框架项目经历待核"},
        "tools_industry": {"score": 8, "evidence": "常用工具符合"},
        "practical_fit": {"score": practical, "evidence": "城市匹配，薪资有交集"},
        "caps": caps if caps is not None else [],
        "hard_gaps": ["关键框架的实际项目经验待核"],
        "reason": "通用后端经验相关，关键框架待核",
        "missing": "实际项目证据",
    }


def _result(**kwargs) -> scorer.ScoreResult:
    result = scorer.validate_structured_score_payload(_payload(**kwargs))
    assert result is not None
    return result


def _job(salary: str = "18-25K", *, review: dict | None = None) -> dict:
    job = {"id": "fictional-job", "salary": salary}
    if review is not None:
        job["manual_company_review"] = review
    return job


def _config(minimum: int = 24, maximum: int = 30) -> dict:
    return {"profile": {"salary_min": minimum, "salary_max": maximum}}


@pytest.mark.parametrize("hard", range(16))
def test_hard_requirement_score_does_not_gain_automatic_cap(hard: int) -> None:
    result = _result(hard=hard)
    assert result.raw_score == 75 + hard
    assert result.score == result.raw_score
    assert result.caps == ()


@pytest.mark.parametrize(
    "salary,minimum,maximum,practical",
    [
        ("18-25K", 24, 30, 6),
        ("18-24K", 24, 30, 5),
        ("24-30K", 24, 30, 10),
        ("20-28K", 24, 30, 10),
        ("27-35K", 24, 30, 10),
        ("面议", 24, 30, 10),
        ("18-25K", 24, 0, 10),
        ("18-25K", 0, 30, 10),
    ],
)
def test_salary_policy_differentiates_narrow_lower_overlap(
    salary: str, minimum: int, maximum: int, practical: int,
) -> None:
    result = scorer.apply_job_score_policy(_result(), _job(salary), _config(minimum, maximum))
    assert result.components["practical_fit"] == practical
    assert result.raw_score == 73 + practical
    assert result.score == result.raw_score
    assert ("实际条件最高" in result.component_evidence["practical_fit"]) is (practical < 10)


def test_explicit_low_priority_caps_final_score_and_reapplication_is_stable() -> None:
    review = {"type": "manual_company_review", "recommendation": "low_priority", "review": "公司用工主体待核"}
    first = scorer.apply_job_score_policy(_result(), _job(review=review), _config())
    second = scorer.apply_job_score_policy(first, _job(review=review), _config())
    assert first.raw_score == 79
    assert first.score == 65
    assert first.caps == ("manual_low_priority",)
    assert second == first


@pytest.mark.parametrize(
    "review",
    [
        None,
        {"type": "manual_company_review", "recommendation": "needs_review", "review": "待核"},
        {"type": "manual_company_review", "recommendation": "low_priority", "review": ""},
    ],
)
def test_unreviewed_or_unconfirmed_company_is_not_automatically_downgraded(review: dict | None) -> None:
    result = scorer.apply_job_score_policy(_result(), _job(review=review), _config())
    assert result.score == 79
    assert "manual_low_priority" not in result.caps


def test_model_cannot_inject_human_or_derived_caps() -> None:
    result = _result(hard=8, caps=["manual_low_priority", "key_requirement_unverified"])
    assert result.caps == ()
    assert result.score == result.raw_score


@pytest.mark.parametrize(
    "cap,expected_score",
    [
        ("technical_required", 55),
        ("sales_acquisition_core", 65),
        ("weak_core_transfer", 70),
    ],
)
def test_explicit_model_caps_still_apply_with_low_hard_requirements(
    cap: str, expected_score: int,
) -> None:
    result = _result(hard=8, caps=[cap])
    assert result.raw_score == 83
    assert result.score == expected_score
    assert result.caps == (cap,)


def test_trace_keeps_component_sum_and_manual_policy_cap() -> None:
    review = {"type": "manual_company_review", "recommendation": "low_priority", "review": "主体待核"}
    result = scorer.apply_job_score_policy(_result(), _job(review=review), _config())
    trace = scorer.build_score_trace(result)
    sanitized = scorer.sanitize_score_trace(trace)
    assert sanitized is not None
    assert sum(part["score"] for part in sanitized["components"].values()) == sanitized["raw_score"] == 79
    assert sanitized["final_score"] == 65
    assert sanitized["caps"] == ["manual_low_priority"]


def test_legacy_trace_keeps_removed_cap_without_recalculating_historical_score() -> None:
    fresh_trace = scorer.build_score_trace(_result())
    assert fresh_trace["caps"] == []
    legacy_trace = {
        **fresh_trace,
        "final_score": 70,
        "caps": ["key_requirement_unverified"],
    }
    sanitized = scorer.sanitize_score_trace(legacy_trace)
    assert sanitized is not None
    assert sanitized["raw_score"] == 83
    assert sanitized["final_score"] == 70
    assert sanitized["caps"] == ["key_requirement_unverified"]


def test_agent_evaluations_apply_salary_and_manual_policy_before_greeting() -> None:
    job = _job(review={
        "type": "manual_company_review", "recommendation": "low_priority", "review": "主体待核",
    })
    evaluation = {"job_id": job["id"], "score": _payload()}
    scored = validate_agent_evaluations(
        [evaluation], 71, jobs_by_id={job["id"]: job}, config=_config(),
    )
    assert scored[0]["score"] == 65
    assert scored[0]["passed"] is False
    assert scored[0]["trace"]["raw_score"] == 79
    assert scored[0]["trace"]["final_score"] == 65
    with pytest.raises(AgentRequestError, match="greeting"):
        validate_agent_evaluations(
            [{**evaluation, "greeting": "您好，这是一段虚构岗位的应聘问候，请核对实际要求后再联系招聘方。"}],
            71, jobs_by_id={job["id"]: job}, config=_config(),
        )
