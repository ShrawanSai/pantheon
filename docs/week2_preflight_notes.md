# Week 2 Preflight Notes

Date: 2026-02-21

## Must-Do Before Week 2 Feature Expansion
1. `llm_call_events` migration first.
- Add this as Week 2 Task 0 before metering-integrated chat work.

2. Railway API database env readiness.
- Ensure `DATABASE_URL` and `DATABASE_POOL_URL` are set in Railway API service.
- Run `alembic upgrade head` against Supabase Postgres before DB-dependent routes.

3. Orchestrator routing hardening.
- Do not carry forward comma-split parsing of manager output.
- Use structured output (JSON/function-calling contract) for manager routing.

4. Context budget/summarization.
- Add explicit token budgeting + summarization before deeper multi-turn room rollout.
- Treat as early Week 2 scope, not deferred work.

5. Supabase service-role key rotation.
- Rotate service role key before Week 2 work beyond local dev.
- Update rotated value across local and Railway envs.

6. `users.id` type decision (`String` vs native UUID).
- Decide before Room/Agent CRUD write paths expand.
- If changing to UUID type, do it in earliest Week 2 migration pass.
