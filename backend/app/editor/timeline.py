import json

from app.core import db


def default_timeline(check_id: str) -> list[dict]:
    """A fresh editor session starts with every claim clip from this check,
    in their original chronological order -- the starting point the user
    then removes from, reorders, and splices uploaded video into."""
    row = db.fetch_one("SELECT claims_json FROM reel_checks WHERE id=?", (check_id,))
    if not row or not row["claims_json"]:
        return []
    claims = json.loads(row["claims_json"])
    return [{"type": "claim", "claim_index": i} for i in range(len(claims))]


def get_timeline(check_id: str) -> list[dict]:
    row = db.fetch_one("SELECT items_json FROM editor_timelines WHERE check_id=?", (check_id,))
    if row:
        return json.loads(row["items_json"])
    return default_timeline(check_id)


def set_timeline(check_id: str, items: list[dict]) -> None:
    db.execute(
        "INSERT INTO editor_timelines (check_id, items_json, updated_at) "
        "VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(check_id) DO UPDATE SET items_json=excluded.items_json, "
        "updated_at=excluded.updated_at",
        (check_id, json.dumps(items)),
    )
