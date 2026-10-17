import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.models import User
from ezo_api.db.session import Database
from ezo_api.knowledge.vectorstores import LocalVectorStore, VectorFilter, VectorRecord
from tests.conftest import migrate


@pytest.fixture
async def session(tmp_path) -> AsyncIterator[AsyncSession]:  # type: ignore[no-untyped-def]
    url = f"sqlite:///{tmp_path / 'v.db'}"
    migrate(url)
    db = Database(url)
    async with db.sessionmaker() as s:
        yield s
    await db.dispose()


async def _user(session: AsyncSession) -> uuid.UUID:
    user = User(email=f"{uuid.uuid4()}@x", display_name="x", preferences={})
    session.add(user)
    await session.flush()
    return user.id


async def test_search_orders_by_cosine_and_filters(session: AsyncSession) -> None:
    store = LocalVectorStore()
    user, other = await _user(session), await _user(session)
    project = uuid.uuid4()
    a, b, c, d = (uuid.uuid4() for _ in range(4))
    await store.upsert(
        session,
        [
            VectorRecord("chunk", a, user, "m", [1.0, 0.0]),
            VectorRecord("chunk", b, user, "m", [0.7, 0.7]),
            VectorRecord("chunk", c, user, "m", [1.0, 0.0], project_id=project),
            VectorRecord("chunk", d, other, "m", [1.0, 0.0]),
            VectorRecord("chunk", uuid.uuid4(), user, "other-model", [1.0, 0.0]),
        ],
    )
    hits = await store.search(session, [1.0, 0.0], VectorFilter(user, "chunk", "m"), 10)
    assert [h.owner_id for h in hits] == [a, b]  # no other user, project or model
    assert hits[0].score == pytest.approx(1.0)

    scoped = await store.search(
        session, [1.0, 0.0], VectorFilter(user, "chunk", "m", project_scope=project), 10
    )
    assert {h.owner_id for h in scoped} == {a, b, c}

    await store.delete_owners(session, "chunk", [a])
    assert a not in {
        h.owner_id
        for h in await store.search(session, [1.0, 0.0], VectorFilter(user, "chunk", "m"), 10)
    }
    assert await store.count(session, user, "chunk") == 3


async def test_upsert_replaces_vector(session: AsyncSession) -> None:
    store = LocalVectorStore()
    user, owner = await _user(session), uuid.uuid4()
    await store.upsert(session, [VectorRecord("memory", owner, user, "m", [1.0, 0.0])])
    await store.upsert(session, [VectorRecord("memory", owner, user, "m", [0.0, 1.0])])
    hits = await store.search(session, [0.0, 1.0], VectorFilter(user, "memory", "m"), 5)
    assert len(hits) == 1 and hits[0].score == pytest.approx(1.0)
