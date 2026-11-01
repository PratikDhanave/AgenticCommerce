"""FastAPI + SSE bridge between the ADK agents and the browser.

Two backends, one event contract:

  mode=replay  deterministic pre-written LLM turns, real mandate enforcement
  mode=live    real google-adk Runner driving Gemini

The browser cannot tell them apart, which is the whole point: the stage demo
degrades to replay on bad wifi without changing a line of UI code.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import catalog, trace
from .script import ACTS
from .tools import (
    check_against_mandate,
    execute_payment,
    get_product,
    mandate_for,
    read_mandate,
    reset_mandate,
    search_catalog,
    suggest_alternative,
)

def _load_env() -> None:
    """Read .env into the process without pulling in python-dotenv.

    The key lives in a gitignored, mode-600 file rather than in the shell
    profile, so a shared laptop does not leak it into every other process.
    """
    path = pathlib.Path(__file__).resolve().parent.parent / ".env"
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()


app = FastAPI(title="Agentic Commerce — Pune Product × GCC Forum")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# session_id -> asyncio.Event set when the human taps approve/deny
_approvals: dict[str, asyncio.Event] = {}
_approval_verdict: dict[str, bool] = {}

TOOL_FNS = {
    "read_mandate": read_mandate,
    "check_against_mandate": check_against_mandate,
    "execute_payment": execute_payment,
    "search_catalog": search_catalog,
    "get_product": get_product,
    "suggest_alternative": suggest_alternative,
}

# How fast the pre-written turns type. Tuned for a room reading a projector.
TOKEN_DELAY = float(os.environ.get("DEMO_TOKEN_DELAY", "0.022"))
STEP_PAUSE = float(os.environ.get("DEMO_STEP_PAUSE", "0.42"))

# In voice mode the browser speaks each turn. There is no feedback channel from
# speechSynthesis back to the server, so instead of guessing we spread the text
# stream over the *estimated* speaking time. Tuned against Chrome's default
# rate; raise DEMO_VOICE_WPM if the captions lag behind the audio.
VOICE_WPM = float(os.environ.get("DEMO_VOICE_WPM", "165"))
VOICE_TAIL = float(os.environ.get("DEMO_VOICE_TAIL", "0.5"))


def speech_seconds(text: str) -> float:
    """Rough wall-clock a TTS engine needs for this text."""
    words = max(1, len(text.split()))
    return max(1.0, words / (VOICE_WPM / 60.0))


def inr(n: int) -> str:
    return "₹" + f"{n:,}"


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def chunk(text: str) -> list[str]:
    """Split into token-ish pieces so streaming looks like a real model."""
    return re.findall(r"\S+\s*|\n", text)


# --------------------------------------------------------------------------
# Replay backend
# --------------------------------------------------------------------------

async def run_replay(session_id: str, act_id: str, voice: bool = False):
    act = ACTS[act_id]
    mandate = reset_mandate(session_id)
    trace.current_session.set(session_id)

    yield sse({"kind": "run_started", "act": act_id, "mode": "replay",
               "voice": voice, "title": act["title"], "beat": act["beat"],
               "prompt": act["prompt"], "mandate": mandate.as_dict(),
               "at": time.time()})
    await asyncio.sleep(STEP_PAUSE)
    # The opening line is what the presenter just said out loud, so the client
    # shows it but never speaks it back at them.
    yield sse({"kind": "user_message", "text": act["prompt"], "speak": False})
    await asyncio.sleep(STEP_PAUSE)

    call_n = 0
    for step in act["steps"]:
        kind = step["t"]

        if kind == "user":
            # Mid-act buyer lines are part of the scene, so these do get voiced.
            yield sse({"kind": "user_message", "text": step["text"],
                       "speak": voice})
            await asyncio.sleep(
                speech_seconds(step["text"]) + VOICE_TAIL if voice
                else STEP_PAUSE * 1.6)

        elif kind == "a2a":
            yield sse({"kind": "a2a_message", "frm": step["frm"],
                       "to": step["to"], "text": step["text"]})
            await asyncio.sleep(STEP_PAUSE)

        elif kind == "say":
            agent = step["agent"]
            text = step["text"]
            yield sse({"kind": "agent_thinking", "agent": agent})
            await asyncio.sleep(STEP_PAUSE * 1.3)
            # The client starts speaking on _start, so it needs the whole turn
            # up front; the token stream below is the caption track for it.
            yield sse({"kind": "agent_message_start", "agent": agent,
                       "text": text, "speak": voice})
            pieces = chunk(text)
            delay = (speech_seconds(text) / len(pieces)) if voice else TOKEN_DELAY
            for piece in pieces:
                yield sse({"kind": "agent_token", "agent": agent, "text": piece})
                await asyncio.sleep(delay)
            yield sse({"kind": "agent_message_end", "agent": agent, "text": text})
            await asyncio.sleep(VOICE_TAIL if voice else STEP_PAUSE)

        elif kind == "tool":
            call_n += 1
            call_id = f"call_{call_n:03d}"
            agent, tool = step["agent"], step["tool"]
            yield sse({"kind": "tool_call", "agent": agent, "tool": tool,
                       "args": step["args"], "call_id": call_id})
            await asyncio.sleep(STEP_PAUSE * 0.8)

            # Real tool, real mandate. Only the prose above is pre-written.
            result = TOOL_FNS[tool](**step["args"])

            # Drain whatever semantic events the tool emitted.
            q = trace.queue_for(session_id)
            while not q.empty():
                yield sse(q.get_nowait())

            yield sse({"kind": "tool_result", "agent": agent, "tool": tool,
                       "call_id": call_id, "result": result,
                       "mandate": mandate.as_dict()})
            await asyncio.sleep(STEP_PAUSE)

        elif kind == "approval":
            p = catalog.BY_SKU[step["sku"]]
            m_auto = mandate.auto_approve_below
            ev = asyncio.Event()
            _approvals[session_id] = ev
            yield sse({"kind": "approval_required", "sku": p.sku,
                       "title": p.title, "amount": p.price,
                       "reason": f"Above the {inr(m_auto)} auto-approve ceiling.",
                       "speak": voice, "mandate": mandate.as_dict()})
            # Keep the connection warm while the room watches the presenter.
            waited = 0.0
            while not ev.is_set():
                await asyncio.sleep(0.25)
                waited += 0.25
                if waited % 10 == 0:
                    yield sse({"kind": "heartbeat", "waiting_for": "human"})
            approved = _approval_verdict.get(session_id, True)
            yield sse({"kind": "approval_resolved", "approved": approved,
                       "sku": p.sku})
            if not approved:
                yield sse({"kind": "run_finished", "status": "declined_by_human"})
                return
            await asyncio.sleep(STEP_PAUSE)

        elif kind == "refuse":
            yield sse({"kind": "run_finished", "status": "blocked_by_mandate",
                       "mandate": mandate.as_dict()})
            return

    yield sse({"kind": "run_finished", "status": "completed",
               "mandate": mandate.as_dict()})


# --------------------------------------------------------------------------
# Live ADK backend
# --------------------------------------------------------------------------

# Live mode picks the first model that actually answers. Gemini returns 404 for
# models retired out from under you and 503 when one is under load, and both
# happen mid-demo. Walking a chain beats dying on the first candidate.
# Free-tier quota is per *model* per day, so a spent model does not spend the
# rest of the chain. Ordered newest-capable first, lites last as the cheap
# survivors. Set ADK_MODEL to jump the queue.
MODEL_CHAIN = list(dict.fromkeys(m for m in [
    os.environ.get("ADK_MODEL"),
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
] if m))


async def run_live(session_id: str, act_id: str):
    from google.adk import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from .agent import merchant_agent, root_agent

    act = ACTS[act_id]
    mandate = reset_mandate(session_id)
    trace.current_session.set(session_id)

    svc = InMemorySessionService()
    await svc.create_session(app_name="agentic_commerce",
                             user_id="buyer", session_id=session_id)
    runner = Runner(app_name="agentic_commerce", agent=root_agent,
                    session_service=svc)

    yield sse({"kind": "run_started", "act": act_id, "mode": "live",
               "title": act["title"], "beat": act["beat"],
               "prompt": act["prompt"], "mandate": mandate.as_dict(),
               "at": time.time()})
    yield sse({"kind": "user_message", "text": act["prompt"]})

    msg = types.Content(role="user", parts=[types.Part(text=act["prompt"])])

    # Try each candidate until one yields its first event, then commit to it.
    last_err: Exception | None = None
    for i, model in enumerate(MODEL_CHAIN):
        root_agent.model = model
        merchant_agent.model = model
        started = False   # a model_selected badge went out
        emitted = False   # real content went out; past here we cannot restart
        try:
            async for event in runner.run_async(
                user_id="buyer", session_id=session_id, new_message=msg
            ):
                if not started:
                    started = True
                    yield sse({"kind": "model_selected", "model": model,
                               "fallbacks_tried": i})
                agent = getattr(event, "author", "shopper_agent")

                for part in (getattr(
                    getattr(event, "content", None), "parts", None) or []):
                    if getattr(part, "text", None):
                        emitted = True
                        yield sse({"kind": "agent_token", "agent": agent,
                                   "text": part.text})
                    fc = getattr(part, "function_call", None)
                    if fc is not None:
                        emitted = True
                        yield sse({"kind": "tool_call", "agent": agent,
                                   "tool": fc.name, "args": dict(fc.args or {}),
                                   "call_id": getattr(fc, "id", "") or fc.name})
                    fr = getattr(part, "function_response", None)
                    if fr is not None:
                        yield sse({"kind": "tool_result", "agent": agent,
                                   "tool": fr.name,
                                   "call_id": getattr(fr, "id", "") or fr.name,
                                   "result": dict(fr.response or {}),
                                   "mandate": mandate.as_dict()})

                q = trace.queue_for(session_id)
                while not q.empty():
                    yield sse(q.get_nowait())

                if getattr(event, "partial", False) is False and getattr(
                    event, "content", None
                ) is not None:
                    yield sse({"kind": "turn_boundary", "agent": agent})

            yield sse({"kind": "run_finished", "status": "completed",
                       "mandate": mandate.as_dict()})
            return

        except Exception as exc:
            last_err = exc
            # Only a model-availability failure is worth retrying elsewhere;
            # anything after the run has started would duplicate the turn.
            # ADK wraps provider errors, so the HTTP status is sometimes on
            # the exception and sometimes only in its message. Check both.
            code = getattr(exc, "code", None)
            if code is None:
                m = re.search(r"\b(404|429|503)\b", str(exc))
                code = int(m.group(1)) if m else None
            retryable = code in (404, 429, 503) and not emitted
            yield sse({"kind": "model_unavailable", "model": model,
                       "code": code, "retrying": retryable})
            if not retryable:
                break

    quota = "429" in str(last_err) or "RESOURCE_EXHAUSTED" in str(last_err)
    yield sse({"kind": "error",
               "message": ("Every candidate model is out of free-tier quota "
                           "for today." if quota
                           else f"{type(last_err).__name__}: {last_err}"),
               "hint": ("Free-tier quota is 20 requests/day per model and "
                        "resets ~24h after first use. Replay mode runs the "
                        "full demo with the real mandate meanwhile.")
                       if quota else
                       "All candidate models failed. Switch to replay."})
    yield sse({"kind": "run_finished", "status": "error"})


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "live_available": bool(
            os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        ),
        "model": os.environ.get("ADK_MODEL", "gemini-3.6-flash"),
        "catalog_size": len(catalog.CATALOG),
    }


@app.get("/api/acts")
def acts() -> dict:
    return {
        "acts": [
            {"id": k, "title": v["title"], "beat": v["beat"],
             "prompt": v["prompt"]}
            for k, v in ACTS.items()
        ]
    }


@app.get("/api/catalog")
def full_catalog() -> dict:
    return {"items": [p.as_dict() for p in catalog.CATALOG]}


@app.get("/api/mandate")
def get_mandate(session: str = "demo") -> dict:
    return mandate_for(session).as_dict()


@app.post("/api/approve")
def approve(session: str = "demo", approved: bool = True) -> dict:
    _approval_verdict[session] = approved
    ev = _approvals.get(session)
    if ev is not None:
        ev.set()
    return {"ok": True, "approved": approved}


@app.get("/api/stream")
async def stream(session: str = "demo", act: str = "act1",
                 mode: str = "replay", voice: bool = False) -> StreamingResponse:
    if act not in ACTS:
        act = "act1"
    trace.reset(session)
    gen = (run_live(session, act) if mode == "live"
           else run_replay(session, act, voice=voice))
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"},
    )


# Serve the built frontend if it exists, so one process runs the whole demo.
_DIST = pathlib.Path(__file__).resolve().parent.parent / "web" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_DIST / "index.html")
