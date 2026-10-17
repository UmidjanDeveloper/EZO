from fastapi import FastAPI
from httpx import AsyncClient

from ezo_api.db.models import User

SCENES = [
    {"title": "Muqova", "layout": "cover", "text": "EZO 2026", "duration_seconds": 4},
    {
        "title": "Muammo",
        "layout": "problem_solution",
        "text": "Hujjatlar ko'p",
        "speaker_notes": "Raqamlar bilan ko'rsating",
        "narration": {"text": " ".join(["so'z"] * 36), "voice": "default"},
    },
    {"title": "Yakun", "layout": "closing", "text": "Rahmat", "transition": "fade"},
]


async def create_story(client: AsyncClient, **extra: object) -> dict:  # type: ignore[type-arg]
    body = {
        "title": "Raqamlashtirish loyihasi",
        "goal": "Hokimga loyiha taklifi",
        "audience": "Tuman hokimligi",
        "language": "uz",
        "format": "both",
        "visual_style": "minimal",
        "scenes": SCENES,
        **extra,
    }
    response = await client.post("/api/stories", json=body)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def test_story_crud_and_ordering(client: AsyncClient) -> None:
    story = await create_story(client)
    assert story["scene_count"] == 3 and story["aspect_ratio"] == "16:9"
    assert [(s["index"], s["title"]) for s in story["scenes"]] == [
        (0, "Muqova"),
        (1, "Muammo"),
        (2, "Yakun"),
    ]
    assert story["scenes"][1]["narration"]["voice"] == "default"
    assert story["scenes"][0]["narration"] is None

    ids = [s["id"] for s in story["scenes"]]
    reordered = (
        await client.post(
            f"/api/stories/{story['id']}/scenes/reorder",
            json={"scene_ids": [ids[2], ids[0], ids[1]]},
        )
    ).json()
    assert [s["title"] for s in reordered["scenes"]] == ["Yakun", "Muqova", "Muammo"]
    assert [s["index"] for s in reordered["scenes"]] == [0, 1, 2]

    bad = await client.post(
        f"/api/stories/{story['id']}/scenes/reorder", json={"scene_ids": ids[:2]}
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_order"

    patched = (
        await client.patch(
            f"/api/stories/{story['id']}", json={"title": "Yangi sarlavha", "aspect_ratio": "9:16"}
        )
    ).json()
    assert (
        patched["title"] == "Yangi sarlavha"
        and patched["aspect_ratio"] == "9:16"
        and patched["goal"] == "Hokimga loyiha taklifi"
    )

    replaced = (
        await client.put(
            f"/api/stories/{story['id']}/scenes", json={"scenes": [{"title": "Faqat bitta"}]}
        )
    ).json()
    assert [s["title"] for s in replaced["scenes"]] == ["Faqat bitta"]

    listed = (await client.get("/api/stories")).json()
    assert listed[0]["scene_count"] == 1
    assert (await client.delete(f"/api/stories/{story['id']}")).status_code == 204
    assert (await client.get(f"/api/stories/{story['id']}")).status_code == 404


async def test_timeline_follows_durations_and_narration(client: AsyncClient) -> None:
    story = await create_story(client)
    timed = (await client.post(f"/api/stories/{story['id']}/timeline")).json()
    spans = [(t["start_seconds"], t["end_seconds"]) for t in timed["timeline"]]
    assert spans == [(0.0, 4.0), (4.0, 19.8), (19.8, 25.8)]  # narration of scene 2 needs 15.8 s
    assert timed["total_seconds"] == 25.8
    assert timed["scenes"][1]["narration"]["timing"] == {"start": 4.0, "end": 19.8}
    assert timed["timeline"][2]["animation"] == {"transition": "fade"}

    ids = [s["id"] for s in timed["scenes"]]
    reordered = (
        await client.post(
            f"/api/stories/{story['id']}/scenes/reorder", json={"scene_ids": ids[::-1]}
        )
    ).json()
    assert reordered["timeline"] == []  # the old timeline no longer matches; rebuild it


async def test_assets_link_to_own_artifacts_only(client: AsyncClient, app: FastAPI) -> None:
    artifact = (
        await client.post("/api/artifacts", json={"title": "Diagramma", "content": "graph"})
    ).json()
    scenes = [{"title": "Rasm", "assets": [{"asset_type": "image", "artifact_id": artifact["id"]}]}]
    story = await create_story(client, scenes=scenes)
    assert story["scenes"][0]["assets"][0]["artifact_id"] == artifact["id"]

    services = app.state.services
    async with services.db.sessionmaker() as session:
        stranger = User(email="s@x", display_name="S", preferences={})
        session.add(stranger)
        await session.flush()
        foreign = await services.artifacts.create(
            session,
            stranger.id,
            title="x",
            artifact_type="image",
            filename="x.png",
            data=b"\x89PNG",
        )
        await session.commit()
    bad = await client.post(
        "/api/stories",
        json={
            "title": "t",
            "scenes": [
                {
                    "title": "s",
                    "assets": [{"asset_type": "image", "artifact_id": str(foreign.artifact.id)}],
                }
            ],
        },
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_asset"


async def test_story_access_control_and_project_scope(client: AsyncClient, app: FastAPI) -> None:
    project = (await client.post("/api/projects", json={"name": "P"})).json()
    in_project = await create_story(client, project_id=project["id"])
    await create_story(client)
    scoped = (await client.get("/api/stories", params={"project_id": project["id"]})).json()
    assert [s["id"] for s in scoped] == [in_project["id"]]

    services = app.state.services
    async with services.db.sessionmaker() as session:
        from ezo_api.schemas.stories import StoryIn

        stranger = User(email="o@x", display_name="O", preferences={})
        session.add(stranger)
        await session.flush()
        foreign = await services.stories.create(session, stranger.id, StoryIn(title="Begona"))
        await session.commit()
    assert (await client.get(f"/api/stories/{foreign.id}")).status_code == 404
    assert (await client.delete(f"/api/stories/{foreign.id}")).status_code == 404
    assert all(s["id"] != str(foreign.id) for s in (await client.get("/api/stories")).json())
