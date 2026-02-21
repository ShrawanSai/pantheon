# pantheon

## OpenRouter Setup

1. Rotate the OpenRouter key you shared and create a new one in the OpenRouter dashboard.
2. Create a local `.env` file (already git-ignored) from this template:

```env
OPENROUTER_API_KEY=your_new_openrouter_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

3. Optional PowerShell session export:

```powershell
$env:OPENROUTER_API_KEY="your_new_openrouter_key_here"
$env:OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
```

Once this is set, I can wire the Python backend client and LangGraph model router directly to OpenRouter.

## Local Python Environment

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip langchain langchain-openai python-dotenv
```

## LangChain + OpenRouter Smoke Test

Available model aliases:
- `llama`
- `qwen`
- `deepseek`
- `gpt_oss`
- `premium` (Gemini)

Run:

```powershell
.\.venv\Scripts\python scripts\pantheon_langchain_openrouter_test.py --model deepseek
```

## MVP Test App (LangGraph + SQLite)

This includes:
- SQL memory (`sqlite`) for sessions/messages/turn-steps/settings
- 3 agents (`researcher`, `writer`, `reviewer`)
- 3 modes (`manual/tag`, `roundtable`, `orchestrator`)
- mode switching mid-conversation (applies on next turn)
- orchestrator manager model configurable from admin endpoint/UI

Run the app:

```powershell
.\.venv\Scripts\python -m uvicorn pantheon_app.main:app --reload
```

Open:
- http://127.0.0.1:8000

Key API endpoints:
- `POST /api/session`
- `GET /api/session/{session_id}/agents`
- `POST /api/session/{session_id}/agents`
- `POST /api/session/{session_id}/mode`
- `POST /api/session/{session_id}/chat`
- `POST /api/session/{session_id}/chat/stream`
- `GET /api/session/{session_id}/messages`
- `GET /api/admin/orchestrator-model`
- `POST /api/admin/orchestrator-model`
