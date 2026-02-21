from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import AsyncIterator
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from pantheon_app.graph_engine import ChatGraphEngine
from pantheon_app.memory import SqlMemory, VALID_MODES
from pantheon_llm.openrouter_langchain import SUPPORTED_LLMS


class CreateSessionRequest(BaseModel):
    mode: Literal["manual", "roundtable", "orchestrator"] = "roundtable"


class SetModeRequest(BaseModel):
    mode: Literal["manual", "roundtable", "orchestrator"]


class ChatRequest(BaseModel):
    text: str = Field(min_length=1)
    tagged_agents: list[str] = Field(default_factory=list)


class SetManagerModelRequest(BaseModel):
    model_alias: str


class AgentConfig(BaseModel):
    id: str
    name: str
    model_alias: str
    role_prompt: str


class SetAgentsRequest(BaseModel):
    agents: list[AgentConfig]


app = FastAPI(title="Pantheon MVP Test App", version="0.1.0")
memory = SqlMemory()
engine = ChatGraphEngine()

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def root() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/models")
def list_models() -> dict[str, list[str]]:
    return {"models": sorted(SUPPORTED_LLMS.keys())}


@app.post("/api/session")
def create_session(req: CreateSessionRequest) -> dict:
    return memory.create_session(req.mode)


@app.get("/api/session/{session_id}")
def get_session(session_id: str) -> dict:
    session = memory.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/api/session/{session_id}/messages")
def get_messages(session_id: str) -> dict:
    session = memory.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"messages": memory.get_messages(session_id)}


@app.get("/api/session/{session_id}/agents")
def get_agents(session_id: str) -> dict:
    session = memory.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"agents": memory.get_agents(session_id)}


@app.post("/api/session/{session_id}/agents")
def set_agents(session_id: str, req: SetAgentsRequest) -> dict:
    session = memory.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not req.agents:
        raise HTTPException(status_code=400, detail="At least one agent is required")
    ids = [a.id for a in req.agents]
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=400, detail="Agent IDs must be unique")
    for a in req.agents:
        if a.model_alias not in SUPPORTED_LLMS:
            raise HTTPException(status_code=400, detail=f"Unknown model alias '{a.model_alias}'")
    memory.replace_agents(session_id, [a.model_dump() for a in req.agents])
    return {"agents": memory.get_agents(session_id)}


@app.post("/api/session/{session_id}/mode")
def set_mode(session_id: str, req: SetModeRequest) -> dict:
    session = memory.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    memory.set_pending_mode(session_id, req.mode)
    return {"session_id": session_id, "pending_mode": req.mode}


@app.get("/api/admin/orchestrator-model")
def get_orchestrator_model() -> dict:
    value = memory.get_setting("orchestrator_manager_alias", "deepseek")
    return {"orchestrator_manager_alias": value}


@app.post("/api/admin/orchestrator-model")
def set_orchestrator_model(req: SetManagerModelRequest) -> dict:
    if req.model_alias not in SUPPORTED_LLMS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported model alias '{req.model_alias}'. Allowed: {sorted(SUPPORTED_LLMS.keys())}",
        )
    memory.set_setting("orchestrator_manager_alias", req.model_alias)
    return {"orchestrator_manager_alias": req.model_alias}


@app.post("/api/session/{session_id}/chat")
async def chat(session_id: str, req: ChatRequest) -> dict:
    session = memory.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    effective_mode = memory.resolve_mode_for_turn(session_id)
    if effective_mode not in VALID_MODES:
        raise HTTPException(status_code=500, detail=f"Invalid mode in session: {effective_mode}")

    history = memory.get_messages(session_id, limit=20)
    history_text = "\n".join([f"{m['role']}: {m['content']}" for m in history[-12:]])
    memory.add_message(session_id, "user", req.text, effective_mode)
    agents = memory.get_agents(session_id)

    manager_alias = memory.get_setting("orchestrator_manager_alias", "deepseek") or "deepseek"
    result = await engine.run_turn(
        mode=effective_mode,
        user_input=req.text,
        history_text=history_text,
        manager_alias=manager_alias,
        tagged_agents=req.tagged_agents,
        agents=agents,  # dynamic room roster
    )

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    request_id = str(uuid.uuid4())
    steps = result.get("steps", [])
    memory.add_turn_steps(session_id, request_id, effective_mode, steps)

    assistant_text = result.get("assistant_output", "")
    for step in steps:
        memory.add_message(
            session_id,
            "assistant",
            step.get("output_text", ""),
            effective_mode,
            agent_name=step.get("agent_name"),
        )
    if not steps and assistant_text:
        memory.add_message(session_id, "assistant", assistant_text, effective_mode)

    session_after = memory.get_session(session_id) or {}
    return {
        "request_id": request_id,
        "effective_mode": effective_mode,
        "session": session_after,
        "assistant_output": assistant_text,
        "steps": steps,
        "messages": memory.get_messages(session_id),
    }


@app.post("/api/session/{session_id}/chat/stream")
async def chat_stream(session_id: str, req: ChatRequest) -> StreamingResponse:
    session = memory.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    effective_mode = memory.resolve_mode_for_turn(session_id)
    if effective_mode not in VALID_MODES:
        raise HTTPException(status_code=500, detail=f"Invalid mode in session: {effective_mode}")

    history = memory.get_messages(session_id, limit=20)
    history_text = "\n".join([f"{m['role']}: {m['content']}" for m in history[-12:]])
    memory.add_message(session_id, "user", req.text, effective_mode)
    agents = memory.get_agents(session_id)

    manager_alias = memory.get_setting("orchestrator_manager_alias", "deepseek") or "deepseek"
    request_id = str(uuid.uuid4())

    async def event_stream() -> AsyncIterator[bytes]:
        collected_steps: list[dict] = []
        try:
            async for event in engine.stream_turn(
                mode=effective_mode,
                user_input=req.text,
                history_text=history_text,
                manager_alias=manager_alias,
                tagged_agents=req.tagged_agents,
                agents=agents,  # dynamic room roster
            ):
                etype = event.get("type")
                if etype == "step":
                    step = event["step"]
                    collected_steps.append(step)
                    memory.add_message(
                        session_id,
                        "assistant",
                        step.get("output_text", ""),
                        effective_mode,
                        agent_name=step.get("agent_name"),
                    )
                elif etype == "done":
                    memory.add_turn_steps(session_id, request_id, effective_mode, collected_steps)
                    event["session"] = memory.get_session(session_id) or {}
                payload = (json.dumps(event) + "\n").encode("utf-8")
                yield payload
        except Exception as exc:
            yield (json.dumps({"type": "error", "error": str(exc)}) + "\n").encode("utf-8")

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
