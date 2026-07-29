import uuid

from fastapi import APIRouter, HTTPException

from app.core import db
from app.models.schemas import CreateSessionRequest, NewspaperResponse, SessionResponse
from app.rag.newspaper import generate_newspaper
from app.session_runner import SessionRunner, active_sessions

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _row_to_session(row) -> SessionResponse:
    return SessionResponse(**dict(row))


@router.post("", response_model=SessionResponse)
async def create_session(req: CreateSessionRequest):
    session_id = str(uuid.uuid4())
    runner = SessionRunner(session_id, req.url)
    active_sessions[session_id] = runner
    runner.start()
    row = db.fetch_one("SELECT * FROM sessions WHERE id=?", (session_id,))
    return _row_to_session(row)


@router.get("", response_model=list[SessionResponse])
def list_sessions():
    rows = db.fetch_all("SELECT * FROM sessions ORDER BY created_at DESC")
    return [_row_to_session(r) for r in rows]


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: str):
    row = db.fetch_one("SELECT * FROM sessions WHERE id=?", (session_id,))
    if not row:
        raise HTTPException(404, "session not found")
    return _row_to_session(row)


@router.post("/{session_id}/stop", response_model=SessionResponse)
async def stop_session(session_id: str):
    runner = active_sessions.get(session_id)
    if not runner:
        raise HTTPException(404, "session not active")
    await runner.stop()
    del active_sessions[session_id]
    row = db.fetch_one("SELECT * FROM sessions WHERE id=?", (session_id,))
    return _row_to_session(row)


@router.post("/{session_id}/newspaper", response_model=NewspaperResponse)
def create_newspaper(session_id: str):
    if not db.fetch_one("SELECT id FROM sessions WHERE id=?", (session_id,)):
        raise HTTPException(404, "session not found")
    content = generate_newspaper(session_id)
    row = db.fetch_one("SELECT created_at FROM session_newspapers WHERE session_id=?", (session_id,))
    return NewspaperResponse(session_id=session_id, content=content, created_at=row["created_at"])


@router.get("/{session_id}/newspaper", response_model=NewspaperResponse)
def get_newspaper(session_id: str):
    row = db.fetch_one(
        "SELECT content, created_at FROM session_newspapers WHERE session_id=?", (session_id,)
    )
    if not row:
        raise HTTPException(404, "newspaper not generated yet")
    return NewspaperResponse(session_id=session_id, content=row["content"], created_at=row["created_at"])
