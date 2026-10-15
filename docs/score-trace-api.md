# Score Trace API

Score Trace records the explanation produced by a successful structured AI score. It is a read-only detail endpoint and does not change the existing job-list payload.

## Endpoint

`GET /api/jobs/{job_id}/score-trace`

### Successful response

```json
{
  "job_id": "job-123",
  "state": "available",
  "trace": {
    "schema_version": 1,
    "role_summary": "岗位职责概述",
    "components": {
      "core_duties": {"score": 34, "max_score": 40, "evidence": "..."},
      "transferable_evidence": {"score": 21, "max_score": 25, "evidence": "..."},
      "hard_requirements": {"score": 12, "max_score": 15, "evidence": "..."},
      "tools_industry": {"score": 7, "max_score": 10, "evidence": "..."},
      "practical_fit": {"score": 8, "max_score": 10, "evidence": "..."}
    },
    "raw_score": 82,
    "final_score": 55,
    "caps": ["technical_required"],
    "hard_gaps": ["缺少 Linux 私有化部署经历"],
    "summary_reason": "产品交付经验匹配，但有硬技术缺口",
    "missing": "Linux 部署",
    "review_status": "initial"
  }
}
```

`review_status` is `initial` for the first assessment and `reviewed` after a successful secondary review. New `caps` may contain `technical_required`, `sales_acquisition_core`, `weak_core_transfer`, or `manual_low_priority`. Historical traces may also contain `key_requirement_unverified`; this legacy label remains readable but is no longer applied to new scores.

## Scoring policy

- The hard-requirements component records evidence for mandatory conditions, including gaps when its score is 0–10. It does not trigger an automatic score cap. Preferred skills must not be treated as mandatory.
- New `technical_required` caps require affirmative evidence that the candidate does not meet a core, explicitly mandatory technical requirement and that this prevents the core work. Missing resume details, adjacent experience, and unverified proficiency are pending questions, not grounds for the 55 cap; component scores can still reflect incomplete evidence.
- A proposed technical cap must supply an internal `technical_required_assessment` with `requirement`, `is_core_required`, `evidence_status` (`met`, `adjacent`, `unverified`, or `not_met`), `candidate_evidence`, `blocks_core_work`, and `blocking_reason`. The AI and Agent entry points verify quoted requirements against the JD and quoted candidate evidence against the resume. Unsupported or contradictory cap requests are removed and labeled pending. This internal object and its source quotes are not added to the V1 trace response.
- When secondary review is enabled, either a final or raw score of 68–79 triggers review, as does any proposed technical cap, including one rejected by validation. A valid review can revoke the initial technical cap and replace its obsolete gaps; other cap policies retain their existing behavior. Invalid or unavailable reviews preserve the validated first result, and service-level failures retain the existing pause behavior.
- Salary overlap still passes the existing prefilter. When the vacancy's maximum is below the candidate's target maximum and the overlap covers at most 25% of a fully configured target interval, the practical-fit component is capped at 6/10 (5/10 when only the lower endpoint touches). Broader overlap, higher salary, unparsed salary, and one-sided targets do not trigger this deduction.
- A recorded `manual_company_review` with an explicit `low_priority` recommendation and nonempty review caps the final score at 65. This records application priority; it is not a finding of company misconduct. Company claims and unknowns are supplied to the scorer with their evidence context and are not automatically treated as confirmed risks.
- Both workbench AI scoring and the local Agent submission endpoint apply these rules before comparing the final score with the configured threshold. The Agent endpoint rejects greetings if the adjusted score fails the threshold.
- New scoring reasons retain the latest manual company review. Rescoring does not restore a manually filtered job to `ready`, and the AI-filter reset queue skips manual exclusions.
- Company-review text is a display prefix, not a completed score. Retry selection, funnel counts, missing-trace states, and failure exports classify the scoring text beneath it, so a retained note cannot turn a prefilter or scoring failure into a successful assessment.

Policy changes apply to new evaluations. Historical scores and traces remain unchanged until a separately requested targeted adjustment or rescore.

## States

| HTTP | State | Meaning |
| --- | --- | --- |
| 200 | `available` | A validated V1 trace is available. |
| 200 | `legacy_missing` | The job has historical scoring information but no trace. |
| 200 | `prefilter_only` | The job stopped at pre-filtering, so no AI trace exists. |
| 200 | `failed` | AI scoring failed before a trace could be saved. |
| 200 | `unavailable` | No usable trace is available, including malformed stored data. |
| 404 | — | The job does not exist: `{"error": "job_not_found"}`. |

## Persistence and safety

- The latest trace is written atomically with a successful structured score.
- Pre-filter and AI-score failures do not create a trace and do not overwrite a previously valid trace.
- The API exposes a strict V1 whitelist only; it never returns resumes, raw JD text, API keys, or raw model responses.
