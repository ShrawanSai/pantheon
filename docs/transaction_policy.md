# Pantheon MVP - Transaction Boundary Policy

Last updated: 2026-02-22  
Owner: Codex  
Reviewer: External supervising engineer

## Purpose
Define a single, enforceable transaction model for route write paths so we do not reintroduce the Week 5 F41 partial-commit billing gap.

## Policy (Mandatory)
All new write paths must use a single-transaction staged-write model:

1. Build and validate request/auth/ownership context.
2. Add/modify all primary domain rows in the active DB session.
3. Stage auxiliary rows (`stage_*` helpers) in the same DB session.
4. Use `db.flush()` where early integrity detection is needed (e.g., conflict -> `409` path).
5. Perform exactly one `await db.commit()` for the full unit of work.
6. On exception, `await db.rollback()` and return mapped API error.

## Required Patterns
- Use `stage_llm_usage(db, record)` for usage-event writes in route paths.
- Keep route/service contracts typed; avoid implicit dict payload contracts for write coordination.
- Keep conflict handling explicit:
  - `IntegrityError` at flush/commit -> deterministic client error (e.g., `409`) when appropriate.

## Disallowed Patterns (Without Explicit Exception Approval)
- Multiple commits in a single happy-path request flow.
- Writing usage/audit rows only after domain commit in a second transaction.
- Mixing staged and committed side effects without documented ordering rationale.

## Legacy Compatibility Rule
- `record_llm_usage(...)` remains for backward compatibility.
- Route-level transactional paths should prefer `stage_llm_usage(...)` + single route commit.
- Week 6 F47 requires auditing and migrating in-scope callers toward the staged pattern.

## Exception Process
Any deviation must include:
1. Written rationale in PR/commit notes.
2. Supervisor approval before task is marked `DONE`.
3. Checklist evidence describing risk and mitigation.

## Verification Checklist For New Write Paths
- [ ] Exactly one commit in happy path.
- [ ] Staged usage/audit writes occur before commit.
- [ ] Conflict path is tested (where applicable).
- [ ] Rollback path exists and is reachable on exception.
- [ ] Test count updated at task close.
