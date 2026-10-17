from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in body.strip().split("\n\n"):
        name, data = "", ""
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = line[len("data: ") :]
        if name:
            events.append((name, json.loads(data)))
    return events


async def stream_chat(client: AsyncClient, **body: Any) -> list[tuple[str, dict[str, Any]]]:
    response = await client.post("/api/chat/stream", json=body)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_sse(response.text)


async def count_vectors(app: FastAPI, owner_type: str | None = None) -> int:
    """Vectors in whichever store is active (pgvector table on PostgreSQL, JSON table otherwise)."""
    async with app.state.services.db.sessionmaker() as session:
        store = await app.state.services.vectors.get(session)
        table = "pgvector_entries" if store.name == "pgvector" else "vector_entries"
        where = " WHERE owner_type = :t" if owner_type else ""
        result = await session.execute(
            text(f"SELECT count(*) FROM {table}{where}"),  # noqa: S608 - constant table names
            {"t": owner_type},
        )
        return int(result.scalar_one())
