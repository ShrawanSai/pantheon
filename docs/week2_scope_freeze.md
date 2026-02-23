# Pantheon MVP - Week 2 Scope Freeze

Date: 2026-02-21  
Status: Frozen for execution (pre-feature gates first)

## Source Inputs
- `docs/mvp_srs.md`
- `docs/sprint_week1_handoff.md` (Week 2 Start Checklist)
- `docs/week2_preflight_notes.md`
- Supervisor guidance from Week 1 closeout

## Ordered Week 2 Execution (Must Follow)
1. Freeze Week 2 scope (this document).
2. Define `llm_call_events` schema contract.
3. Implement first Week 2 migration: `llm_call_events`.
4. Apply migration to Supabase Postgres and verify.
5. Confirm Railway API DB env readiness (`DATABASE_URL`, `DATABASE_POOL_URL`).
6. Only then start Room/Agent CRUD feature expansion.

## In Scope (Week 2)
1. Data foundations
- Add `llm_call_events` migration with SRS-required metering fields.
- Validate FK/index strategy for usage lookup patterns.

2. Environment/ops readiness
- Ensure DB env vars are present for API service.
- Validate migration path against Supabase DB.

3. Runtime guardrails (design-level if not fully implemented in Week 2)
- Structured output contract for orchestrator routing.
- Context budget/summarization planning for multi-turn stability.

4. Feature kickoff
- Start Room/Agent CRUD implementation only after foundations above are complete.

## Out Of Scope (Week 2)
- Stripe payment collection implementation.
- Referral system implementation.
- Non-MVP tools (code execution/browser automation).
- Full direct-chat polish beyond already approved MVP baseline.
- Any feature branch that depends on metering without `llm_call_events` in place.

## Non-Negotiable Gates
- Gate A: No DB-backed feature routes before migration readiness.
- Gate B: No orchestrator production rollout with comma-split routing parser.
- Gate C: No broad rollout without service-role key rotation task scheduled/executed.

## Week 2 Success Criteria
- `llm_call_events` table exists and is queryable in Supabase.
- Railway API can run DB-dependent routes with validated env configuration.
- Room/Agent CRUD work starts on stable schema/runtime foundations.
