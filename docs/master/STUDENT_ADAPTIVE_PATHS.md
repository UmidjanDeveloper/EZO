# Student V3 source-bound learning paths — backend candidate

This implements a bounded, owner-defined learning path over existing durable
StudyCards and StudyReviews. It is not an automatic expert curriculum, clinical/
exam assessment or proof of mastery. No model is used to invent progress.

## Working behavior

An owner selects current source-bound cards, titles up to30 steps, and declares
prerequisites using earlier step indexes. Each card appears once, with at most200
cards total and20 per step. The backend validates ownership/project scope, source
revision and quoted offsets, then stores the immutable definition. An optional
personal goal must belong to the owner; its manual progress is never overwritten.

A read-only evaluation uses one SQL snapshot for current card versions and their
actual recent recall events. A checkpoint requires the configured1–5 consecutive
`good`/`easy` events on that card, a positive interval and a next due time in the
future. `hard`/`again`, an overdue card, unavailable source or a missing prerequisite
cannot satisfy it. Source changes or card deletion block the step instead of
silently substituting another source. Review-budget exhaustion is explicit.

Recommendations are only `review_card` or `read_source`, with actual document/
revision IDs, Unicode quote offsets, card versions and due dates. They grant no
authority: the existing review POST still requires an explicit authenticated user
action and its normal version fence. Reading/evaluating a path creates no reviews,
AI scores, model calls, memory consent or PersonalGoal progress writes.

A satisfied checkpoint is a current recall-scheduling observation, not “the student
has mastered this concept.” Later lapses/overdue reviews can relock later steps.
No measured pedagogical effectiveness or live tutor quality is claimed.

## Stable additive API for Antigravity

Prefix: `/api/student/learning-paths`. Authentication/rate limits remain unchanged.
Every source, card, goal and project is backend-authorized. Wrong-user or wrong-
project IDs return404. Select the same `project_id` on subsequent scoped requests.

| Method | Contract |
|---|---|
| POST prefix | UUID `request_id`, title, language `uz/en/ru`, optional project/goal, steps with card IDs/prerequisites/required_recalls;201 first creation,200 exact replay |
| GET prefix | metadata-only bounded list (`limit`1–50, bounded offset); no full source text or all definitions materialized |
| GET `/{id}` | evaluated steps and at most20 recommendations; `assessment:self_reported_recall`, `mastery_claim:false`, `action_authority:none` |
| PATCH `/{id}` | explicit `active/paused`, `expected_version`, optional project; stale versions409 |
| DELETE `/{id}?confirm=true` | removes title/definition/goal link; preserves a minimal idempotency tombstone and the independently owned cards/review history |

Reusing a request UUID with different input is409. Deletion replay never recreates
a removed path; a deliberate new request UUID is a separate owner action. Capacity
is100 active paths and1,000 retained admissions/tombstones per owner, serialized
with the owner's database row. Definitions cannot install skills, execute code,
change tools, modify repository files or authorize external agent actions.

Migration0021 follows additive0020/0019. New tables revoke PUBLIC, anon and
authenticated access. Existing Student source/revision/card/review data is preserved;
the upgrade regression exercises0019->0021 with actual Unicode card data and, on
PostgreSQL, intentionally hostile default Data API grants in the disposable test DB.

Frontend integration remains Antigravity-owned. No UI files are changed and no
whole P3/V3 completion claim follows from backend tests. Tests:
`tests/integration/test_learning_paths.py`, `test_master_upgrade.py` plus existing
Student regression suites. Exact executed results are in the evidence report.
