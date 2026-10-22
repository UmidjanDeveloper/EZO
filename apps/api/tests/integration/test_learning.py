"""Knowledge OS K1: learning websites, GitHub repositories and packages into libraries —
the API, the reading rules (scope, robots, depth, limits), prompt-injection flags, licence
review, persistence across a restart, privacy, deletion, and chat."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from ezo_api.db.models import AuditLog, KnowledgeDocument, LearnedSource, User
from ezo_api.main import create_app
from ezo_api.providers.base import ModelProvider
from tests.conftest import make_settings
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat
from tests.learning_web import DOCS, FakeWeb, docs_site, github_repo, npm_package, pypi_package


def build(database_url: str, providers: dict[str, ModelProvider], web: FakeWeb) -> FastAPI:
    return create_app(make_settings(database_url), providers=providers, fetcher=web.fetcher())


@pytest.fixture
def web() -> FakeWeb:
    return FakeWeb()


@pytest.fixture
def learning_app(database_url: str, providers: dict[str, ModelProvider], web: FakeWeb) -> FastAPI:
    return build(database_url, providers, web)


@pytest.fixture
async def api(learning_app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=learning_app), base_url="http://t") as c:
        yield c
    await learning_app.state.services.db.dispose()


@pytest.mark.parametrize(
    ("language", "text"),
    [("uz", "bilim kutubxonasi"), ("en", "knowledge library"), ("ru", "Библиотека знаний")],
)
async def test_deleted_library_notice_matches_owner_language(
    api: AsyncClient, language: str, text: str
) -> None:
    await api.patch("/api/me/preferences", json={"ui_language": language})
    library = (await api.post("/api/learning/libraries", json={"name": "Scoped library"})).json()
    events = await stream_chat(api, message="Salom", library_id=library["id"])
    conversation_id = next(data["conversation_id"] for name, data in events if name == "meta")
    assert (await api.delete(f"/api/learning/libraries/{library['id']}")).status_code == 204
    messages = (await api.get(f"/api/conversations/{conversation_id}/messages")).json()
    assert messages[-1]["language"] == language
    assert text in messages[-1]["content"]


async def learn(api: AsyncClient, target: str, **body: Any) -> dict[str, Any]:
    body.setdefault("limits", {"min_interval_seconds": 0})
    response = await api.post("/api/learning/sources", json={"target": target, **body})
    assert response.status_code == 202, response.text
    detail = await api.get(f"/api/learning/sources/{response.json()['id']}")
    return detail.json()  # type: ignore[no-any-return]


async def test_website_is_read_within_its_folder_rules_and_limits(
    api: AsyncClient, web: FakeWeb, learning_app: FastAPI
) -> None:
    docs_site(web)
    source = await learn(api, f"{DOCS}/guide/")
    assert source["status"] == "indexed", source
    urls = {d["url"] for d in source["documents"]}
    assert f"{DOCS}/guide/" in urls and f"{DOCS}/guide/quickstart.html" in urls
    assert f"{DOCS}/guide/api/deep.html" in urls  # depth 2
    assert f"{DOCS}/guide/api/deeper.html" not in web.requests  # depth 3: never requested
    assert f"{DOCS}/guide/private.html" not in web.requests  # robots.txt
    assert f"{DOCS}/blog/" not in web.requests  # outside the folder
    assert not any("other.example.com" in u for u in web.requests)  # other host
    assert not any(u.endswith((".png", ".zip")) for u in web.requests)  # never requested
    assert all(d["status"] in ("indexed", "partial") for d in source["documents"])
    assert (
        source["title"] == "Widget guide" and source["profile"]["publisher"] == "docs.example.org"
    )
    # Learned pages are listed under their source, not among the user's own files.
    assert (await api.get("/api/knowledge/documents")).json() == []
    everything = (await api.get("/api/knowledge/documents?include_learned=true")).json()
    assert len(everything) == len(source["documents"])
    # The injection attempt is recorded, not obeyed, and audit-logged.
    [flag, *_] = source["security_flags"]
    assert flag["kind"] == "override" and flag["location"].endswith("quickstart.html")
    async with learning_app.state.services.db.sessionmaker() as session:
        actions = (await session.scalars(select(AuditLog.action))).all()
    assert "learning.injection_suspected" in actions and "learning.read" in actions
    assert source["profile"]["license_review"]["category"] == "unknown"

    # A page limit stops the reading and says why.
    small = await learn(
        api, f"{DOCS}/guide/api/", limits={"max_pages": 1, "min_interval_seconds": 0}
    )
    assert small["status"] == "partial" and small["stats"]["stopped"] == "page_limit"
    assert len(small["documents"]) == 1


async def test_knowledge_survives_a_restart_and_is_searchable(
    database_url: str, providers: dict[str, ModelProvider], web: FakeWeb
) -> None:
    docs_site(web)
    first = build(database_url, providers, web)
    async with AsyncClient(transport=ASGITransport(app=first), base_url="http://t") as api:
        source = await learn(api, f"{DOCS}/guide/")
    await first.state.services.db.dispose()

    second = build(database_url, providers, FakeWeb())  # a fresh process, no network
    async with AsyncClient(transport=ASGITransport(app=second), base_url="http://t") as api:
        listed = (await api.get("/api/learning/sources")).json()
        assert [s["id"] for s in listed] == [source["id"]] and listed[0]["status"] == "indexed"
        found = await api.post("/api/knowledge/search", json={"query": "widget.connect token"})
        hits = found.json()["results"]
        assert any("widget.connect" in h["excerpt"] for h in hits)
        assert any(h["url"].startswith(DOCS) for h in hits)
    await second.state.services.db.dispose()


async def test_github_repository_via_api_without_running_anything(
    api: AsyncClient, web: FakeWeb
) -> None:
    github_repo(web)
    source = await learn(api, "https://github.com/acme/widget/tree/main")
    assert source["kind"] == "github" and source["target"] == "github:acme/widget"
    assert source["status"] == "indexed", source
    assert source["version"] == "a" * 12 and source["license"] == "mit"  # the commit read
    assert source["profile"]["latest_release"] == "v1.4.0"
    assert source["profile"]["commit"] == "a" * 40
    assert source["profile"]["license_review"]["needs_review"] is False
    paths = [d["url"].split("/blob/" + "a" * 40 + "/")[1] for d in source["documents"]]
    # README, licence and manifest first; docs; then code as text only.
    assert paths[:3] == ["README.md", "LICENSE", "pyproject.toml"]
    assert {"docs/usage.md", "examples/basic.py", "src/widget/__init__.py"} <= set(paths)
    assert not any("node_modules" in p or p.endswith(".png") for p in paths)
    assert not any("docs/huge.md" in u for u in web.requests)  # over the file size limit
    assert "install.sh" not in paths  # shell scripts are not read
    assert {"folder": "docs", "files": 2} in source["profile"]["structure"]
    # The API was used without a token; nothing was sent to raw files as authorization.
    assert all("authorization" not in h for h in web.headers)


async def test_github_falls_back_to_raw_files_when_the_api_is_refused(
    api: AsyncClient, web: FakeWeb
) -> None:
    github_repo(web, api=False)
    source = await learn(api, "github:acme/widget")
    assert source["status"] == "partial", source  # degraded reading is never "indexed"
    assert source["profile"]["access"] == "raw_fallback"
    assert "exact commit is unknown" in source["profile"]["access_note"]
    assert source["license"] == "mit"  # recognised from the LICENSE text
    assert source["version"] is None
    urls = {d["url"] for d in source["documents"]}
    assert "https://github.com/acme/widget/blob/HEAD/README.md" in urls


async def test_packages_from_pypi_and_npm(api: AsyncClient, web: FakeWeb) -> None:
    pypi_package(web)
    npm_package(web)
    pypi = await learn(api, "pip install widget")
    assert pypi["kind"] == "pypi" and pypi["version"] == "1.4.0" and pypi["license"] == "apache-2.0"
    assert pypi["profile"]["dependencies"] == ["httpx>=0.27"]
    assert pypi["profile"]["docs_site"]["pages_read"] >= 3  # the linked documentation site
    urls = [d["url"] for d in pypi["documents"]]
    assert urls[:2] == ["https://pypi.org/project/widget/1.4.0", "https://pypi.org/project/widget/"]

    npm = await learn(api, "npm:@acme/widget")
    assert npm["version"] == "2.0.1" and npm["license"] == "gpl-3.0"
    review = npm["profile"]["license_review"]
    assert review["needs_review"] is True and review["category"] == "copyleft_or_restricted"
    assert npm["profile"]["entry_points"] == ["dist/index.js", "dist/index.d.ts"]

    missing = await learn(api, "pypi:does-not-exist")
    assert missing["status"] == "failed" and "was not found" in missing["error"]


async def test_registry_privacy_refresh_and_deletion(
    api: AsyncClient, web: FakeWeb, learning_app: FastAPI
) -> None:
    docs_site(web)
    library = await api.post("/api/learning/libraries", json={"name": "Python kutubxonalari"})
    assert library.status_code == 201
    assert (
        await api.post("/api/learning/libraries", json={"name": "python KUTUBXONALARI"})
    ).status_code == 409
    source = await learn(api, f"{DOCS}/guide/", library_id=library.json()["id"])
    again = await api.post(
        "/api/learning/sources",
        json={"target": f"{DOCS}/guide/", "library_id": library.json()["id"]},
    )
    assert again.status_code == 200 and again.json()["created"] is False

    refreshed = await api.post(f"/api/learning/sources/{source['id']}/refresh")
    assert refreshed.status_code == 202
    detail = (await api.get(f"/api/learning/sources/{source['id']}")).json()
    assert detail["stats"]["changed"] == 0 and detail["stats"]["content_changed"] is False
    versions_path = f"/api/learning/sources/{source['id']}/versions"
    versions = (await api.get(versions_path)).json()
    assert len(versions) == 2
    assert versions[0]["content_hash"] == versions[1]["content_hash"]
    assert versions[0]["previous_content_hash"] == versions[1]["content_hash"]
    assert versions[0]["documents"]
    assert all(d["revision_id"] and d["content_hash"] for d in versions[0]["documents"])
    assert all(
        set(d) == {"document_id", "revision_id", "content_hash"} for d in versions[0]["documents"]
    )
    assert len((await api.get(versions_path + "?limit=1")).json()) == 1
    assert (await api.get(versions_path + "?offset=100")).json() == []
    assert (await api.get(versions_path + "?limit=51")).status_code == 422
    assert (await api.get(f"/api/learning/sources/{uuid.uuid4()}/versions")).status_code == 404

    # Unsafe or unknown targets are refused before anything is registered.
    private = await api.post("/api/learning/sources", json={"target": "http://internal.corp/docs"})
    assert private.status_code == 422 and private.json()["error"]["code"] == "blocked"
    local = await api.post("/api/learning/sources", json={"target": "http://127.0.0.1:8000/"})
    assert local.status_code == 422
    bad = await api.post("/api/learning/sources", json={"target": "just some words"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "bad_target"
    wrong_kind = await api.post(
        "/api/learning/sources", json={"target": f"{DOCS}/guide/", "kind": "pypi"}
    )
    assert wrong_kind.status_code == 422

    # Another user sees nothing.
    async with learning_app.state.services.db.sessionmaker() as session:
        session.add(User(email="other@x", display_name="Other", preferences={}))
        await session.commit()
    fake = uuid.uuid4()
    assert (await api.get(f"/api/learning/sources/{fake}")).status_code == 404
    assert (await api.delete(f"/api/learning/libraries/{fake}")).status_code == 404

    # Deleting removes the documents, chunks, vectors and stored files.
    storage = learning_app.state.services.storage
    async with learning_app.state.services.db.sessionmaker() as session:
        keys = (
            await session.scalars(
                select(KnowledgeDocument.storage_key).where(
                    KnowledgeDocument.source_url.like(f"{DOCS}%")
                )
            )
        ).all()
    assert keys and all([await storage.exists(k) for k in keys if k])
    assert (await api.delete(f"/api/learning/sources/{source['id']}")).status_code == 204
    async with learning_app.state.services.db.sessionmaker() as session:
        left = await session.scalar(select(func.count()).select_from(KnowledgeDocument))
        sources = await session.scalar(select(func.count()).select_from(LearnedSource))
    assert left == 0 and sources == 0
    assert not any([await storage.exists(k) for k in keys if k])
    assert (await api.delete(f"/api/learning/libraries/{library.json()['id']}")).status_code == 204
    assert (await api.get("/api/learning/libraries")).json() == []


async def test_chat_learns_a_source_and_lists_what_it_learned(
    api: AsyncClient, web: FakeWeb, fake_anthropic: FakeProvider
) -> None:
    pypi_package(web)
    fake_anthropic.replies = ["O'rgandim."]
    events = await stream_chat(
        api, message="Ezo, mana bu Python kutubxonasini o'rgan: https://pypi.org/project/widget/"
    )
    assert ("activity", {"stage": "reading"}) in events
    system = fake_anthropic.requests[-1].system or ""
    assert "Role: EZO's Knowledge OS" in system
    assert "EZO read the source into the library “Asosiy kutubxona”" in system
    assert "status: indexed" in system and "version 1.4.0" in system
    assert "Never say EZO installed, activated" in system

    fake_anthropic.replies = ["Mana ro'yxat."]
    await stream_chat(api, message="O'rgangan manbalaringni ko'rsat")
    system = fake_anthropic.requests[-1].system or ""
    assert "[Asosiy kutubxona] «widget»" in system  # titles reach the notes quoted

    fake_anthropic.replies = ["Bloklandi."]
    await stream_chat(api, message="Shu website'ni o'rgan: http://internal.corp/wiki")
    system = fake_anthropic.requests[-1].system or ""
    assert "EZO refused to read" in system and "private network" in system


async def test_an_unreachable_documentation_site_makes_the_package_partial(
    api: AsyncClient, web: FakeWeb
) -> None:
    pypi_package(web)
    web.routes = {k: v for k, v in web.routes.items() if not k.startswith(DOCS)}
    source = await learn(api, "pypi:widget")
    assert source["status"] == "partial"
    assert "documentation website" in source["error"]
    assert source["profile"]["docs_site"]["pages_read"] == 0
    assert len(source["documents"]) == 2  # facts + README are still usable


async def test_library_scoped_search_excludes_other_files_on_both_search_paths(
    api: AsyncClient, web: FakeWeb, learning_app: FastAPI
) -> None:
    """Keyword and vector search (the fake OpenAI provider makes embeddings) both honour
    the library: the user's own file with the same words stays out of a scoped search."""
    docs_site(web)
    source = await learn(api, f"{DOCS}/guide/", library_name="Widget docs")
    upload = await api.post(
        "/api/knowledge/documents",
        files={"file": ("notes.txt", b"My private notes: widget.connect token session.")},
    )
    assert upload.status_code == 201
    query = {"query": "widget.connect token session"}
    everything = (await api.post("/api/knowledge/search", json=query)).json()
    assert everything["mode"] == "hybrid"  # keyword + vector
    urls = {hit.get("url") for hit in everything["results"]}
    assert any(u and u.startswith(DOCS) for u in urls) and None in urls  # both kinds found

    scoped = await api.post(
        "/api/knowledge/search", json={**query, "library_id": source["library_id"]}
    )
    hits = scoped.json()["results"]
    assert hits and all((hit.get("url") or "").startswith(DOCS) for hit in hits)

    stranger = await api.post(
        "/api/knowledge/search", json={**query, "library_id": str(uuid.uuid4())}
    )
    assert stranger.status_code == 404


@pytest.mark.parametrize("interrupted_status", ["queued", "processing", "indexed"])
async def test_restart_indexes_unchanged_document_interrupted_before_publication(
    api: AsyncClient,
    web: FakeWeb,
    learning_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    interrupted_status: str,
) -> None:
    import asyncio

    docs_site(web)
    runner = learning_app.state.services.learning

    async def do_not_start_yet(source_id):
        pass

    with monkeypatch.context() as hold:
        hold.setattr(runner, "submit", do_not_start_yet)
        created = await api.post(
            "/api/learning/sources",
            json={
                "target": f"{DOCS}/guide/",
                "limits": {"min_interval_seconds": 0},
            },
        )
    assert created.status_code == 202
    source_id = uuid.UUID(created.json()["id"])

    original_ingest = runner.service.knowledge.ingest

    async def crash(*args, **kwargs):
        if interrupted_status == "indexed":
            await original_ingest(*args, **kwargs)
        raise asyncio.CancelledError

    with monkeypatch.context() as crash_point:
        # Both real commit boundaries exist in production: file registration and
        # the ingest() processing-status commit before parsing/index publication.
        crash_point.setattr(
            runner.service.knowledge,
            "_run_pipeline" if interrupted_status == "processing" else "ingest",
            crash,
        )
        with pytest.raises(asyncio.CancelledError):
            await runner.service.run(source_id)
    async with learning_app.state.services.db.sessionmaker() as session:
        [interrupted] = (await session.scalars(select(KnowledgeDocument))).all()
        interrupted_id = interrupted.id
        assert interrupted.status == interrupted_status
        interrupted_revision = interrupted.current_revision_id
        assert (interrupted_revision is not None) == (interrupted_status == "indexed")
    # Real startup recovery; fetch again returns identical bytes, not new content.
    assert await runner.resume_unfinished() == 1
    async with learning_app.state.services.db.sessionmaker() as session:
        recovered = await session.get(KnowledgeDocument, interrupted_id)
        assert recovered.status == "indexed"
        assert recovered.current_revision_id is not None
        if interrupted_revision is not None:
            assert recovered.current_revision_id == interrupted_revision
        before = dict(
            (
                await session.execute(
                    select(KnowledgeDocument.id, KnowledgeDocument.current_revision_id)
                )
            ).all()
        )
        source = await session.get(LearnedSource, source_id)
        assert source.status == "indexed"

    async def healthy_duplicates_must_not_reindex(*args, **kwargs):
        raise AssertionError("Already indexed identical input was needlessly reindexed")

    with monkeypatch.context() as no_repeat:
        no_repeat.setattr(runner.service.knowledge, "ingest", healthy_duplicates_must_not_reindex)
        await runner.service.run(source_id)
    async with learning_app.state.services.db.sessionmaker() as session:
        assert (
            dict(
                (
                    await session.execute(
                        select(KnowledgeDocument.id, KnowledgeDocument.current_revision_id)
                    )
                ).all()
            )
            == before
        )
        assert (await session.get(LearnedSource, source_id)).status == "indexed"


@pytest.mark.parametrize("terminal_status", ["failed", "needs_ocr"])
async def test_source_refresh_does_not_revive_unchanged_terminal_document(
    api: AsyncClient,
    web: FakeWeb,
    learning_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    terminal_status: str,
) -> None:
    docs_site(web)
    source = await learn(api, f"{DOCS}/guide/")
    source_id = uuid.UUID(source["id"])
    async with learning_app.state.services.db.sessionmaker() as session:
        document = await session.scalar(select(KnowledgeDocument).limit(1))
        document.status, document.error = terminal_status, "terminal fixture error"
        document_id, revision_id = document.id, document.current_revision_id
        await session.commit()

    retried = []

    async def must_not_retry(*args, **kwargs):
        retried.append(args)
        raise AssertionError("Unchanged terminal input was implicitly retried")

    monkeypatch.setattr(
        learning_app.state.services.learning.service.knowledge, "ingest", must_not_retry
    )
    await learning_app.state.services.learning.service.run(source_id)
    assert not retried
    async with learning_app.state.services.db.sessionmaker() as session:
        document = await session.get(KnowledgeDocument, document_id)
        assert (document.status, document.error) == (terminal_status, "terminal fixture error")
        assert document.current_revision_id == revision_id
