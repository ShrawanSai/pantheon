# Pantheon MVP - Sprint Week 8 Checklist

Sprint window: Week 8 (Cycle 3, Part 2 - File Tools Foundation)  
Owner: Codex  
Reviewer: External supervising engineer  
Last updated: 2026-02-22

## Sprint Goal
Ship the file tools foundation for MVP: room-scoped upload, async parse via arq, file_read tool service, and mode-executor wiring with telemetry and permission enforcement.

## Definition of Done (Week 8)
- Carry-forward triage (F53-F57) is explicitly resolved (fix/defer/accept) before feature work.
- `uploaded_files` schema exists and is migrated from current staging head.
- File upload endpoint validates ownership, format, and size, writes to Supabase Storage, persists DB row, and enqueues parse job.
- arq file_parse job parses TXT/MD/CSV and updates parse status reliably.
- file_read tool service returns parsed content or typed not-ready/error responses without 5xx.
- mode_executor supports permission-gated file_read node and emits tool telemetry.
- Staging validation demonstrates upload -> parse -> read flow end-to-end with telemetry.
- Week 8 handoff is published with migration chain and Week 9 gates.

## Locked Decisions (Pre-Implementation)
1. File format scope (Week 8): `txt`, `md`, `csv` only.
2. File storage backend: Supabase Storage.
3. Upload flow: API-proxied upload (no presigned URLs in Week 8).
4. File size limit: `FILE_MAX_BYTES` env var, default `1048576` (1 MB).
5. File scoping: room-scoped files.
6. Telemetry extension policy: reuse `tool_call_events` schema as-is.

## Entry Gates (Must Resolve Before W8-02)
1. Decisions 1-6 above are locked and documented in this checklist.
2. `REDIS_URL` is set and staging arq worker is confirmed healthy (`health_ping` path available).
3. Supabase Storage bucket exists and service-role key has read/write access.
4. File read trigger format locked: `file: <file_id>` heuristic prefix for Week 8.

## Tracking Rules
- Every task has an ID and status.
- Status values: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`.
- After each task state change, update:
  1. status
  2. evidence/notes
  3. changelog entry

## Supervisor Checkpoint Rule
- Stop for supervisor review after each task that changes:
  1. migration/schema behavior
  2. upload/storage runtime behavior
  3. mode executor runtime behavior

## Staging Evidence Rule
- Staging evidence is required to close any task that touches:
  1. migration behavior
  2. auth behavior
  3. upload/parse/read runtime behavior
- Local tests are necessary but not sufficient for those task types.

## Test Accounting Rule
- State test count at each task close.
- If test count drops or remains flat where coverage should increase, flag before `DONE`.

## Migration Rule
- Confirm `down_revision` against current staging head before migration authoring.
- Confirm live constraint/index names from DB before hardcoding in migration files.

## Technical Constraints Locked In (Week 8)
- `file_read` executes synchronously during turn execution and only reads pre-parsed text.
- Parsing is async-only via arq `file_parse` job.
- If file is not ready (`pending`/`failed`), file_read returns structured tool error (not 500).
- Transaction policy applies: stage DB writes before single route commit.
- file_read is permission-gated through existing `tool_permissions_json` pipeline.
- Manager/orchestrator router does not invoke tool nodes directly.
- `search` and `file_read` tool nodes can coexist when permissions allow.

## Carry-Forward Triage (W8-01 Resolution Targets)
- F53: Defer (accepted for Cycle 3; heuristic triggers remain).
- F54: Defer to Week 9 (header hardening follow-up).
- F55: Fix now via cleanup migration (`status` server default alignment).
- F56: Document intentional no-FK on `ToolCallEvent.user_id` (audit retention).
- F57: Accept permanently (`room_id` String(36) is functionally valid for UUIDs).

## Dependency Rules (Critical Path)
- W8-01 -> W8-02 -> W8-03 -> W8-04 -> W8-05 -> W8-06 -> W8-07 -> W8-08
- W8-06 depends on W8-05 implementation completion.

## Week 8 Task Checklist

| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W8-01 | Carry-forward triage (F53-F57) | DONE | F53-F57 each marked fix/defer/accept with rationale and any implementation tasks spawned | Approved by supervisor. Triage locked: F53 `defer`, F54 `defer`, F55 `fix-now`, F56 `document-intent`, F57 `accept`. F55 implemented via migration `20260222_0008` (status default alignment). F56 documented in ORM with explicit no-FK comment on `ToolCallEvent.user_id`. Entry gate checks: (2) Redis/worker staging health previously validated during W7 staging runs, (3) Supabase Storage `pantheon-files` staging bucket confirmed by user, (4) `file: <file_id>` trigger format locked. |
| W8-02 | `uploaded_files` schema + migration | DONE | Migration creates `uploaded_files` table: `id`, `user_id`, `room_id`, `filename`, `storage_key`, `content_type`, `file_size`, `parse_status`, `parsed_text`, `error_message`, `created_at`; migration chains from `20260222_0008` | Approved by supervisor. ORM + migration aligned with constraints/defaults/indexing requirements. Logged F58 (future user_id index consideration) as non-blocking follow-up. |
| W8-03 | File upload endpoint | DONE | `POST /rooms/{room_id}/files` validates room ownership, format, size; uploads to Supabase Storage; stages DB row and enqueues arq parse job; returns metadata | Approved by supervisor. Route, lifespan arq pool wiring, and test coverage accepted. Carry-forwards logged: F59 (per-request Supabase client instantiation) and F60 (sync upload call blocks event loop in async API path). |
| W8-04 | arq `file_parse` job implementation | DONE | Worker job downloads file from storage, parses TXT/MD/CSV, updates `uploaded_files.parse_status` and `parsed_text`; errors write `failed` + `error_message`; registered in `WorkerSettings.functions` | Approved by supervisor. `file_parse` job, worker registration, and tests accepted. Logged F61 for missing `not_found` and CSV-success test coverage in job test suite (non-blocking). |
| W8-05 | `file_read` tool service implementation | DONE | `file_tool.py` replaced with protocol implementation that reads parsed text by `(file_id, room_id)`, returns content on completed state and structured error on pending/failed/missing | Approved by supervisor. `DefaultFileReadTool` plus five unit tests accepted (`73` -> `78`). |
| W8-06 | Wire `file_read` into mode_executor | DONE | Add permission-gated `maybe_file_read` node when `file_read` allowed; parse trigger `file: <file_id>`; inject result into messages; emit tool telemetry row payload in state | Approved by supervisor. Implemented in `mode_executor.py`: `FILE_READ_TOOL_NAME` integration, `room_id` and `file_id_trigger` state fields, `_extract_file_id`, `maybe_file_read`, and explicit 4-topology compile graph (`none`, `search-only`, `file-only`, `search+file`). Added non-cached graph path when `file_read` is allowed to close over per-turn DB session. Updated `TurnExecutionInput` with `room_id` and wired `room_id=session.room_id` in `sessions.py`. Added 3 integration tests in `tests/test_langgraph_mode_executor.py` (completed, pending, not-permitted). Local validation: `81/81` tests passing, Ruff critical rules passing. |
| W8-07 | Staging validation | DONE | 4-leg flow confirmed: health/auth, upload success, async parse completes, file_read turn produces telemetry; no 5xx | Final successful run evidence: health `200`; auth/me `200`; upload `201` (`file_id=5ea32430-254f-4e53-8308-da07d84832db`, parse_status `pending`); parse completion row `('5ea32430-254f-4e53-8308-da07d84832db','w8_validation.txt','completed',53,NULL)`; session `8cad3a66-5f34-4b0d-a49e-5a3f4bfda801`; turn `ae0df06f-784b-4521-962c-3cfeefc1d06a`; telemetry row count `1`. Additional clean run with exact trigger format (`file: <file_id>`) verified success telemetry: `turn_id=65b0c5de-9822-4eab-a83b-ac2b092d9da1`, row `tool_name='file_read'`, `status='success'`, `latency_ms=75`, `telemetry_count=1`. |
| W8-08 | Week 8 handoff document | DONE | `docs/sprint_week8_handoff.md` published with completion snapshot, artifacts, migration chain, carry-forwards, Week 9 gates/order | Published `docs/sprint_week8_handoff.md` with finalized Week 8 closure state, staging evidence summary, migration chain through `20260222_0009`, and Week 9 entry gates/build order. |

## Current Focus
- Active task: Week 9 planning
- Next after active: Supervisor review of Week 8 handoff

## Assumptions And Follow-Ups
- Week 8 excludes PDF/DOCX parsing by scope lock; revisit in later sprint.
- Tool billing rates for file tools remain out-of-scope (credits recorded as zero for Week 8).
- Existing `tool_call_events` schema is reused without additive columns in Week 8.
- If storage ACL/model details require additional policy docs, log as follow-up during W8-03.
- W8-06 graph topology pre-flag: `_compile_graph` must explicitly handle all four tool combinations (`none`, `search-only`, `file-only`, `search+file`), with sequential order `maybe_search -> maybe_file_read -> call_model` when both are allowed.
- F58 (Low): no index on `uploaded_files.user_id`; add only if user-scoped/admin file queries become frequent.
- F59 (Low): `SupabaseStorageService.upload_bytes()` creates a Supabase client per call; migrate to singleton before higher-volume production usage.
- F60 (Low): Upload route uses synchronous Supabase storage call under async API path; wrap in `asyncio.to_thread` or async client in a future hardening pass.
- F61 (Low): `tests/test_file_parse_job.py` does not yet cover `not_found` return path or CSV-success parse path; add in future test hardening.
- F62 (Low): Per-turn file_read graph compilation instantiates a fresh checkpointer object (no shared in-memory state); acceptable with current per-turn thread IDs.
- F63 (Low): No runtime test yet for combined `search+file_read` dual-tool topology.
- F64 (Low): Worker direct-DB IPv6 connectivity can fail on Railway; worker runtime now prefers `DATABASE_POOL_URL` with fallback to `DATABASE_URL`.

## Change Log
- 2026-02-22: Initialized Week 8 checklist with locked scope/decisions, entry gates, and W8-01..W8-08 dependency chain.
- 2026-02-22: Set W8-01 to `IN_PROGRESS` pending explicit F53-F57 triage logging before schema work starts.
- 2026-02-22: Logged W8-01 triage outcomes (F53 defer, F54 defer, F55 fix-now, F56 document, F57 accept) and confirmed entry gates 2-4 evidence for supervisor review.
- 2026-02-22: Added migration `20260222_0008_tool_call_status_default.py` to align DB default for `tool_call_events.status` with ORM (F55).
- 2026-02-22: Documented intentional no-FK design on `ToolCallEvent.user_id` in ORM model (F56).
- 2026-02-22: Supervisor approved W8-01 as `DONE`.
- 2026-02-22: Started W8-02 (`IN_PROGRESS`), added `UploadedFile` ORM model and migration `20260222_0009_create_uploaded_files.py` chained from `20260222_0008`.
- 2026-02-22: Supervisor approved W8-02 as `DONE`; logged F58 follow-up (optional future `uploaded_files.user_id` index).
- 2026-02-22: Started W8-03 (`IN_PROGRESS`), implemented upload endpoint, Supabase storage dependency, arq app-state pool dependency, and 4 upload route tests.
- 2026-02-22: Validation after W8-03 implementation: `70/70` tests passing and Ruff critical checks passing.
- 2026-02-22: Supervisor approved W8-03 as `DONE`; logged F59 and F60 carry-forwards.
- 2026-02-22: Started W8-04 (`IN_PROGRESS`), implemented `file_parse` arq job with dedicated worker DB session flow and registered it in `WorkerSettings.functions`.
- 2026-02-22: Added file parse job tests (success / unsupported format / download failure); validation now `73/73` tests passing and Ruff critical checks passing.
- 2026-02-22: Supervisor approved W8-04 as `DONE`; logged F61 low-priority test coverage follow-up.
- 2026-02-22: Started W8-05 (`IN_PROGRESS`), implemented file read tool service and added five unit tests for completed/pending/failed/not-found/cross-room paths.
- 2026-02-22: Supervisor approved W8-05 as `DONE`.
- 2026-02-22: Started W8-06 (`IN_PROGRESS`), implemented file_read mode-executor wiring with explicit four-topology graph handling and added three integration tests.
- 2026-02-22: Validation after W8-06 implementation: `81/81` tests passing and Ruff critical checks passing.
- 2026-02-22: Supervisor approved W8-06 as `DONE`; logged F62 and F63 carry-forwards.
- 2026-02-22: Started W8-07 staging validation; blocked by staging deploy drift after upload route returned 404 while other API routes returned 200/201.
- 2026-02-22: Re-ran W8-07 staging validation end-to-end; upload endpoint still 404 while health/auth/room/agent endpoints succeed, confirming staging deploy drift persists.
- 2026-02-22: Applied staging DB migrations to head (`20260222_0009`), reran W8-07. Upload now succeeds (201) and row persists, but parse job did not execute within polling window (status remained `pending`), so W8-07 remains `BLOCKED` pending worker-side fix.
- 2026-02-22: Diagnosed worker failure from Railway logs (`psycopg.OperationalError` IPv6 unreachable on direct DB host). Updated `file_parse` worker DB URL resolution to prefer `DATABASE_POOL_URL` and validated locally (`81/81`, Ruff critical pass).
- 2026-02-22: W8-07 unblocked and completed after worker redeploy + env alignment. Confirmed parse completion and `file_read` telemetry row (`status='success'`, non-null latency, count=1) on staging.
- 2026-02-22: Set W8-08 to `IN_PROGRESS` for Week 8 handoff publication.
- 2026-02-22: Published `docs/sprint_week8_handoff.md` and marked W8-08 as `DONE`.
