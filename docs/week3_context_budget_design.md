# Pantheon MVP - Week 3 Context Budget And Summarization Design (F23)

Date: 2026-02-21  
Owner: Codex  
Status: Approved (clarified for implementation; gate-complete for W3-03)

## 1) Goal
Prevent context overflow and uncontrolled token growth in multi-turn sessions while preserving answer quality and predictable cost.

## 2) Scope
Applies to Week 3 session/turn execution paths:
- session-scoped chat memory assembly
- preflight token budgeting
- automatic summarization and pruning
- overflow failure behavior

Out of scope for this design:
- advanced long-term semantic memory retrieval
- cross-session memory reuse
- provider-specific cache-hit optimization logic

## 3) Inputs And Constraints
- Model context windows vary by `model_alias`.
- Session history can grow beyond practical limits around turn 8-10.
- First implementation must be deterministic, observable, and testable.
- Guardrail must work even when token estimator precision is imperfect.
- `max_output_tokens` source of truth is global API settings:
  - `apps/api/app/core/config.py` -> `Settings.context_max_output_tokens: int`
  - environment variable: `CONTEXT_MAX_OUTPUT_TOKENS`
  - default: `2048`

## 4) Budget Policy
For each turn:
1. Resolve model context window: `model_context_limit`.
2. Reserve output budget:
   - `output_reserve = min(settings.context_max_output_tokens, floor(model_context_limit * 0.20))`
3. Reserve system/tool overhead:
   - `overhead_reserve = max(1024, floor(model_context_limit * 0.05))`
4. Compute input budget:
   - `input_budget = model_context_limit - output_reserve - overhead_reserve`
5. Enforce hard cap:
   - request is invalid if `input_budget <= 0`

Default fallback if model context metadata is unavailable:
- `model_context_limit = 8192`

## 5) Trigger Thresholds
- `summary_trigger_ratio = 0.70`
- `prune_trigger_ratio = 0.90`
- `mandatory_summary_turn = 8`

Actions:
- If estimated input usage >= 70% budget OR turn count since last summary (or since session start if none) >= 8: summarize eligible history.
- If estimated input usage >= 90% budget after summarization: prune older low-value messages.
- If still over budget after prune: reject turn with explicit overflow error and recovery guidance.

## 6) Context Assembly Order
Build prompt context in strict priority:
1. System instructions (global + mode + agent role)
2. Room goal and active mode metadata
3. Latest summary block(s), if any
4. Recent raw conversation window (newest-first selection)
5. User’s current message

Never drop:
- active system prompt layers
- latest user message
- latest assistant/tool outputs tied to unresolved turn state
  - MVP definition of unresolved turn state:
    - latest `turns` record where `status != "completed"`, or
    - latest `turns` record where `assistant_output IS NULL`, or
    - latest `turns` record with any `turn_steps.status != "success"`

## 7) Summarization Strategy
Eligible range:
- older messages outside the protected recent window (e.g., keep last 4 turns raw)

Summarization output contract:
- `summary_text`
- `key_facts[]`
- `open_questions[]`
- `decisions[]`
- `action_items[]`

Persistence target (new table in implementation phase):
- `session_summaries`
  - `id`, `session_id`, `from_message_id`, `to_message_id`, `summary_text`, `created_at`

Replacement behavior:
- summarized message range excluded from active raw window
- newest summary inserted as a synthetic system-context block

## 8) Pruning Strategy
If still near/over budget after summarization:
- prune oldest low-signal assistant/tool chatter first
- retain semantic anchors by policy:
  - retain messages referenced by the most recent summary's `key_facts[]`, `decisions[]`, or `open_questions[]`
- keep most recent `N` turns raw (`N` configurable; default 4)

## 9) Failure Handling
- If summarization call fails:
  - fallback to deterministic truncation with pinned anchors + warning log
- If token estimator fails:
  - fallback estimator `ceil(char_count / 4 * 1.25)` for safety
- If overflow persists after summarize+prune:
  - return `422` with code `context_budget_exceeded`
  - message instructs user to shorten input or start new session

## 10) Observability And Audit
Per turn record:
- `model_context_limit`
- `input_budget`
- estimated tokens before/after summarize/prune
- whether summary/prune triggered
- overflow rejection flag

Persistence target for observability:
- `turn_context_audit` (new table)
  - `id`, `turn_id`, `session_id`, `model_alias`
  - `model_context_limit`, `input_budget`
  - `estimated_input_tokens_before`
  - `estimated_input_tokens_after_summary`
  - `estimated_input_tokens_after_prune`
  - `summary_triggered`, `prune_triggered`, `overflow_rejected`
  - `created_at`

Metrics:
- `context_summary_count`
- `context_prune_count`
- `context_overflow_reject_count`
- `avg_prompt_tokens_per_turn`

## 11) Test Requirements (for implementation phase)
- unit tests for budget math and threshold triggers
- unit tests for fallback estimator behavior
- integration tests:
  - summary triggered at threshold
  - prune triggered after summary
  - overflow rejection path
  - pinned context is preserved

## 12) Week 3 Implementation Dependencies
Before coding W3-05/W3-07:
1. Approve this design.
2. Define config defaults in environment/app settings (`CONTEXT_MAX_OUTPUT_TOKENS`, threshold defaults).
3. Add `session_summaries` Alembic migration before W3-07 implementation starts.
4. Add `turn_context_audit` Alembic migration before W3-07 implementation starts.
