"""Cross-user isolation sweep (P8 / section 11): every owner-scoped resource family.

Runs the real token-mode app: user A creates one resource of each kind; user B (another
ordinary account) and the installation owner (without the super-admin role) must neither
list, read, download nor delete it. A leak anywhere here is a P0 defect. Resources that need
infrastructure this repository never holds (a paired device, a Telegram bot, an executor host)
are out of scope; their routes are covered by the JARVIS suites with fakes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from ezo_api.db.models import User
from ezo_api.main import create_app
from tests.conftest import make_settings
from tests.fakes import FakeProvider

OWNER_TOKEN = "owner-installation-token-0123456789abcdef"
OWNER = {"Authorization": f"Bearer {OWNER_TOKEN}"}


@pytest.fixture
async def token_app(database_url: str) -> AsyncIterator[FastAPI]:
    settings = make_settings(database_url, EZO_AUTH_MODE="token", EZO_API_TOKEN=OWNER_TOKEN)
    app = create_app(settings, providers={"anthropic": FakeProvider("anthropic")})
    yield app
    await app.state.services.db.dispose()


@pytest.fixture
async def api(token_app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=token_app), base_url="http://t") as client:
        yield client


async def _two_users(api: AsyncClient, app: FastAPI) -> tuple[dict[str, str], dict[str, str]]:
    await api.get("/api/me", headers=OWNER)
    async with app.state.services.db.sessionmaker() as session, session.begin():
        owner = await session.scalar(select(User).where(User.role != "super_admin"))
        assert owner is not None
        owner.role = "super_admin"
    headers = []
    for email in ("a@example.com", "b@example.com"):
        created = await api.post(
            "/api/admin/users", headers=OWNER, json={"email": email, "display_name": email}
        )
        assert created.status_code == 201, created.text
        token = await api.post(
            f"/api/admin/users/{created.json()['id']}/tokens", headers=OWNER, json={"label": "t"}
        )
        assert token.status_code == 201, token.text
        headers.append({"Authorization": f"Bearer {token.json()['token']}"})
    # The owner keeps the ordinary role for the sweep: being the installation owner must not
    # expose other users' data either.
    async with app.state.services.db.sessionmaker() as session, session.begin():
        owner = await session.scalar(select(User).where(User.role == "super_admin"))
        assert owner is not None
        owner.role = "user"
    return headers[0], headers[1]


def _ids(items: Any) -> set[str]:
    rows = items if isinstance(items, list) else items.get("items") or items.get("documents") or []
    return {str(row["id"]) for row in rows if isinstance(row, dict) and "id" in row}


async def test_every_owner_scoped_resource_is_invisible_to_other_accounts(
    api: AsyncClient, token_app: FastAPI
) -> None:
    a, b = await _two_users(api, token_app)

    created: list[tuple[str, str, str]] = []  # (family, list route, read/delete route)

    def record(family: str, list_route: str, item_route: str) -> None:
        created.append((family, list_route, item_route))

    project = await api.post("/api/projects", headers=a, json={"name": "A loyihasi"})
    assert project.status_code == 201, project.text
    record("project", "/api/projects", f"/api/projects/{project.json()['id']}")

    memory = await api.post("/api/memories", headers=a, json={"content": "A ning sirli rejasi"})
    assert memory.status_code == 201, memory.text
    record("memory", "/api/memories", f"/api/memories/{memory.json()['id']}")

    artifact = await api.post(
        "/api/artifacts",
        headers=a,
        json={"title": "A hujjati", "type": "document", "format": "markdown", "content": "# Sir"},
    )
    assert artifact.status_code == 201, artifact.text
    record("artifact", "/api/artifacts", f"/api/artifacts/{artifact.json()['id']}")

    goal = await api.post("/api/personal/goals", headers=a, json={"title": "IELTS 7.5"})
    assert goal.status_code == 201, goal.text
    record("goal", "/api/personal/goals", f"/api/personal/goals/{goal.json()['id']}")

    ielts = await api.post("/api/ielts/sessions", headers=a, json={"target_band": 7.0})
    assert ielts.status_code in (200, 201), ielts.text
    record("ielts session", "/api/ielts/history", f"/api/ielts/sessions/{ielts.json()['id']}")

    library = await api.post("/api/learning/libraries", headers=a, json={"name": "A kutubxonasi"})
    assert library.status_code == 201, library.text
    record("library", "/api/learning/libraries", f"/api/learning/libraries/{library.json()['id']}")

    story = await api.post("/api/stories", headers=a, json={"title": "A hikoyasi"})
    assert story.status_code == 201, story.text
    record("story", "/api/stories", f"/api/stories/{story.json()['id']}")

    organization = await api.post(
        "/api/writing/organizations", headers=a, json={"name": "A tashkiloti"}
    )
    assert organization.status_code == 201, organization.text
    record(
        "organization",
        "/api/writing/organizations",
        f"/api/writing/organizations/{organization.json()['id']}",
    )

    document = await api.post(
        "/api/knowledge/documents",
        headers=a,
        files={"file": ("sir.txt", b"A ning maxfiy matni. " * 20, "text/plain")},
    )
    assert document.status_code == 201, document.text
    doc_id = document.json().get("id") or document.json().get("document", {}).get("id")
    assert doc_id, document.text
    record("knowledge document", "/api/knowledge/documents", f"/api/knowledge/documents/{doc_id}")

    assert len(created) == 9

    leaks: list[str] = []
    for who, headers in (("user B", b), ("installation owner", OWNER)):
        for family, list_route, item_route in created:
            item_id = item_route.rsplit("/", 1)[1]
            listed = await api.get(list_route, headers=headers)
            if listed.status_code == 200 and item_id in _ids(listed.json()):
                leaks.append(f"{who} lists A's {family}")
            read = await api.get(item_route, headers=headers)
            if read.status_code == 200:
                leaks.append(f"{who} reads A's {family} ({read.status_code})")
            elif read.status_code not in (403, 404, 405):  # 405: no single-item GET route
                leaks.append(f"{who} reading A's {family}: unexpected {read.status_code}")
            deleted = await api.delete(item_route, headers=headers)
            if deleted.status_code in (200, 204):
                leaks.append(f"{who} deletes A's {family}")
    assert leaks == [], leaks

    # A still owns everything: nothing above deleted or hid it.
    for family, list_route, item_route in created:
        still = await api.get(item_route, headers=a)
        if still.status_code == 405:  # families without a single-item GET: check the listing
            listed = await api.get(list_route, headers=a)
            assert listed.status_code == 200 and item_route.rsplit("/", 1)[1] in _ids(
                listed.json()
            ), family
        else:
            assert still.status_code == 200, (family, still.status_code, still.text)
