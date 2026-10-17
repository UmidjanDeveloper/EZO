from typing import ClassVar

from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy import select

from ezo_api.db.models import ToolCall, User
from ezo_api.tools.base import Tool, ToolContext, ToolResult
from ezo_api.tools.registry import ToolRegistry, redact
from tests.fakes import FakeProvider
from tests.integration.helpers import count_vectors, stream_chat


class EchoArgs(BaseModel):
    text: str
    api_key: str = ""


class EchoTool(Tool[EchoArgs]):
    name: ClassVar[str] = "echo"
    description: ClassVar[str] = "echo"
    args_model: ClassVar[type[BaseModel]] = EchoArgs

    async def run(self, args: EchoArgs, ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, summary=args.text)


class DeleteEverything(EchoTool):
    name: ClassVar[str] = "delete_everything"
    dangerous: ClassVar[bool] = True


async def test_registry_validates_denies_and_logs(app: FastAPI) -> None:
    services = app.state.services
    registry = ToolRegistry([EchoTool(), DeleteEverything()])
    async with services.db.sessionmaker() as session:
        user = User(email="t@x", display_name="t", preferences={})
        session.add(user)
        await session.flush()
        ctx = ToolContext(session=session, services=services, user_id=user.id)

        ok = await registry.execute("echo", {"text": "salom", "api_key": "sk-secret"}, ctx)
        bad = await registry.execute("echo", {"wrong": 1}, ctx)
        unknown = await registry.execute("rm_rf", {}, ctx)
        dangerous = await registry.execute("delete_everything", {"text": "x"}, ctx)
        assert ok.ok and ok.summary == "salom"
        assert not bad.ok and "Invalid arguments" in (bad.error or "")
        assert not unknown.ok and not dangerous.ok
        assert "confirmation" in (dangerous.error or "")

        rows = (await session.scalars(select(ToolCall).order_by(ToolCall.created_at))).all()
        assert [(r.tool_name, r.status) for r in rows] == [
            ("echo", "ok"),
            ("echo", "error"),
            ("rm_rf", "denied"),
            ("delete_everything", "denied"),
        ]
        assert rows[0].arguments["api_key"] == "[redacted]"


def test_redact_shortens_long_values() -> None:
    assert redact({"text": "x" * 600})["text"].endswith("…")


async def test_semantic_memory_vectors_follow_memories(client: AsyncClient, app: FastAPI) -> None:
    created = (
        await client.post(
            "/api/memories", json={"content": "Men qahva o'rniga yashil choy ichaman"}
        )
    ).json()
    assert await count_vectors(app, "memory") == 1
    await client.delete(f"/api/memories/{created['id']}")
    assert await count_vectors(app) == 0


async def test_semantic_memory_retrieval_is_selective(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    await client.post(
        "/api/memories", json={"content": "Yashil choy ichishni yaxshi ko'raman", "importance": 0.6}
    )
    await client.post("/api/memories", json={"content": "Mashinam qora rangda", "importance": 0.6})
    await stream_chat(client, message="Qanday choy tavsiya qilasan?")
    system = fake_anthropic.requests[-1].system or ""
    assert "Yashil choy" in system
    assert "Mashinam" not in system  # unrelated memories are not injected


async def test_auto_captured_memories_are_embedded(client: AsyncClient, app: FastAPI) -> None:
    await stream_chat(client, message="Eslab qol: men minimalist dizaynni yoqtiraman.")
    assert await count_vectors(app, "memory") == 1
