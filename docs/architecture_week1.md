# Pantheon Week 1 Architecture Baseline

Date: 2026-02-20  
Scope: Week 1 foundation structure for MVP implementation

## 1. Objective
Define the production-oriented repository/module structure that will be used from Week 1 onward, while keeping current prototype files as reference.

## 2. Repository Strategy
- Keep current repository.
- Do not delete prototype modules in Week 1.
- Add new production modules in parallel.
- Prototype remains executable as fallback/reference until production paths are stable.

## 3. Target Folder Structure
```text
pantheon/
  docs/
    architecture_week1.md
    env_contract.md
    sprint_week1_checklist.md
    mvp_srs.md

  apps/
    api/                        # FastAPI production backend
      app/
        api/
          v1/
            routes/
              health.py
              auth.py
              rooms.py
              agents.py
              chat.py
              files.py
              billing.py
              admin.py
        core/
          config.py
          security.py
          logging.py
          deps.py
        db/
          session.py
          models/
          repositories/
        services/
          orchestration/
            mode_executor.py
            manager_router.py
            context_manager.py
          llm/
            gateway.py
            pricing.py
          tools/
            search_tool.py
            file_tool.py
          usage/
            meter.py
            recorder.py
          billing/
            wallet.py
            ledger.py
        workers/
          jobs/
            file_parse.py
            retention.py
            rollups.py
          arq_worker.py
        schemas/
          common.py
          auth.py
          rooms.py
          chat.py
          files.py
          billing.py
          admin.py
        main.py
      tests/
        unit/
        integration/

    web/                        # Next.js production frontend
      src/
        app/
        components/
        features/
          auth/
          rooms/
          chat/
          files/
          billing/
          admin/
        lib/
          api/
          auth/
          utils/
        styles/
      public/
      tests/

    worker/                     # Optional dedicated worker package if split from apps/api
      app/
      tests/

  infra/
    alembic/
      versions/
    scripts/
      dev/
      deploy/
    ci/

  pantheon_app/                 # Prototype reference (existing)
  pantheon_llm/                 # Prototype reference (existing)
  scripts/                      # Existing utility scripts
```

## 4. Module Ownership Map
1. `apps/api/app/api/*`
- Public HTTP/streaming endpoints.
- No business logic beyond validation + delegation.

2. `apps/api/app/services/orchestration/*`
- Mode execution orchestration (`manual`, `roundtable`, `orchestrator`).
- Routing contract and context-budget handling.

3. `apps/api/app/services/llm/*`
- OpenRouter adapter, model alias mapping, request/response normalization.
- Token/cost extraction helpers and pricing version hooks.

4. `apps/api/app/services/tools/*`
- Search and file tool wrappers.
- Permission checks delegated from orchestration layer.

5. `apps/api/app/services/usage/*`
- LLM call event recording.
- Token/credit metering and rollup trigger interfaces.

6. `apps/api/app/services/billing/*`
- Wallet operations, ledger transactions, billing policy application.

7. `apps/api/app/workers/*`
- Async jobs via arq for file parsing, retention tasks, rollups.

8. `apps/api/app/db/*`
- Database session management, ORM models (if used), repository layer.

9. `apps/web/src/features/*`
- Feature-oriented frontend slices aligned to backend domains.

10. `infra/alembic/*`
- Migration source of truth for schema evolution.

## 5. Week 1 Implementation Boundaries
- Week 1 creates scaffolding and contracts only.
- Week 1 does not migrate all prototype features.
- Week 2 begins feature migration on top of this structure.

## 6. Compatibility and Transition Rules
1. New production backend path should become primary run target.
2. Prototype API path (`pantheon_app/main.py`) remains available during transition.
3. LangGraph logic can be imported/ported incrementally from `pantheon_app/graph_engine.py`.
4. No breaking deletions of prototype files in Week 1.

## 7. Run Targets (Planned)
1. Backend (production path):
- `uvicorn apps.api.app.main:app --reload`

2. Frontend:
- `next dev` from `apps/web`

3. Worker:
- `arq apps.api.app.workers.arq_worker.WorkerSettings`

