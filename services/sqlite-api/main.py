from fastapi import FastAPI
from fastapi.responses import JSONResponse
import sqlite3
import json
import uuid
from datetime import datetime, timezone

app = FastAPI(title="SQLite Answer Store")

DB_PATH = "/data/answers.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS answers ("
        "  id TEXT PRIMARY KEY,"
        "  question TEXT NOT NULL,"
        "  answer TEXT NOT NULL,"
        "  metadata TEXT,"
        "  created_at TEXT NOT NULL"
        ")"
    )
    conn.commit()
    return conn


@app.post("/answers")
def save_answer(payload: dict):
    question = payload.get("question", "")
    answer = payload.get("answer", "")
    metadata = payload.get("metadata", {})
    row_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = get_db()
    conn.execute(
        "INSERT INTO answers (id, question, answer, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
        (row_id, question, answer, json.dumps(metadata), now),
    )
    conn.commit()
    conn.close()
    return {"id": row_id, "created_at": now}


@app.get("/answers")
def list_answers(limit: int = 50, offset: int = 0):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM answers ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
    conn.close()
    return {
        "total": total,
        "results": [dict(r) for r in rows],
    }


@app.get("/answers/{answer_id}")
def get_answer(answer_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM answers WHERE id = ?", (answer_id,)).fetchone()
    conn.close()
    if not row:
        return JSONResponse(status_code=404, content={"error": "not found"})
    return dict(row)


@app.delete("/answers/{answer_id}")
def delete_answer(answer_id: str):
    conn = get_db()
    conn.execute("DELETE FROM answers WHERE id = ?", (answer_id,))
    conn.commit()
    conn.close()
    return {"deleted": True}


@app.get("/health")
def health():
    return {"status": "ok"}
