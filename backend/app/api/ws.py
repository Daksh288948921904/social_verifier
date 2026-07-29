import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core import db
from app.events.bus import bus

router = APIRouter(tags=["events"])


@router.websocket("/api/sessions/{session_id}/events")
async def session_events(websocket: WebSocket, session_id: str):
    await websocket.accept()
    queue = bus.subscribe(session_id)

    # Replay recent state so a client connecting mid-session isn't starting blind.
    rows = db.fetch_all(
        "SELECT * FROM clips WHERE session_id=? AND status!='deleted' ORDER BY start_seconds",
        (session_id,),
    )
    for row in rows:
        await websocket.send_json({
            "type": "clip_ready",
            "clip_id": row["id"],
            "title": row["title"],
            "video_url": f"/api/clips/{row['id']}/video",
            "thumbnail_url": f"/api/clips/{row['id']}/thumbnail",
        })

    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(session_id, queue)
