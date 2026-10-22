"""Actual HTTP arithmetic and owned durable receipts; not a device/voice mock claim."""

import json
import uuid

from sqlalchemy import select

from ezo_api.db.models import AuditLog, User


async def test_percentage_result_and_private_durable_receipt(client, app):
    response = await client.post(
        "/api/jarvis/percentages",
        json={
            "method": "percent_change",
            "pairs": [{"id": "income", "previous": "100", "current": "125"}],
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["results"][0]["result_percent"] == "25.0000"
    receipt = result["receipt"]
    assert receipt["external_delivery"] == "not_attempted"
    assert receipt["outcome"] == "completed_deterministic_calculation"
    path = "/api/jarvis/receipts/" + receipt["id"]
    assert (await client.get(path)).json() == receipt
    async with app.state.services.db.sessionmaker() as session:
        row = await session.get(AuditLog, uuid.UUID(receipt["id"]))
        stored = json.dumps(row.details)
        assert '"previous"' not in stored and '"current"' not in stored and "income" not in stored
        foreign = User(email=f"jarvis-{uuid.uuid4()}@example.com", display_name="Foreign")
        session.add(foreign)
        await session.flush()
        row.user_id = foreign.id
        await session.commit()
    assert (await client.get(path)).status_code == 404


async def test_capabilities_do_not_claim_missing_devices_or_sending(client):
    response = await client.get("/api/jarvis/capabilities")
    assert response.status_code == 200, response.text
    data = response.json()
    assert "calculate_percentages" in {tool["name"] for tool in data["tools"]}
    assert all(feature["available"] is False for feature in data["device_features"].values())
    assert all(tool["execution_authorized"] is False for tool in data["tools"])
    for path in ("execute", "shell", "send", "install"):
        assert (await client.post("/api/jarvis/" + path, json={})).status_code == 404


async def test_ambiguity_invalid_arithmetic_and_forged_authority_do_not_create_receipts(
    client, app
):
    body = {"pairs": [{"id": "x", "previous": "1", "current": "2"}]}
    assert (await client.post("/api/jarvis/percentages", json=body)).status_code == 422
    assert (
        await client.post(
            "/api/jarvis/percentages", json={**body, "method": "percent_of", "allow_send": True}
        )
    ).status_code == 422
    assert (
        await client.post(
            "/api/jarvis/percentages",
            json={"method": "percent_of", "pairs": [{"id": "x", "previous": "0", "current": "2"}]},
        )
    ).status_code == 422
    async with app.state.services.db.sessionmaker() as session:
        assert (
            await session.scalars(select(AuditLog).where(AuditLog.action == "jarvis.calculation"))
        ).all() == []


async def test_actual_graph_inspection_is_non_executing_and_hash_bound(client, app):
    body = {
        "nodes": [
            {
                "id": "compute",
                "tool": "calculate_percentages",
                "arguments": {
                    "method": "percent_change",
                    "pairs": [{"id": "x", "previous": "100", "current": "125"}],
                },
            },
            {
                "id": "research",
                "tool": "knowledge_search",
                "arguments": {"query": "Income definition"},
            },
        ],
        "links": [{"source": "compute", "target": "research"}],
    }
    response = await client.post("/api/jarvis/inspect-plan", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["execution_authorized"] is False
    assert result["nodes"][1]["depends_on"] == ["compute"]
    assert result["nodes"][1]["authorization"] == "not_checked_no_execution_authority"
    assert len(result["sha256"]) == 64
    assert (await client.post("/api/jarvis/inspect-plan", json=body)).json()["sha256"] == result[
        "sha256"
    ]
    async with app.state.services.db.sessionmaker() as session:
        assert (
            await session.scalars(select(AuditLog).where(AuditLog.action == "jarvis.calculation"))
        ).all() == []


async def test_graph_rejects_cycles_unknown_tools_arguments_and_forged_approvals(client):
    node = {"id": "first", "tool": "knowledge_search", "arguments": {"query": "Hello"}}
    bad = [
        {"nodes": [node], "links": [{"source": "first", "target": "first"}]},
        {"nodes": [node, node]},
        {"nodes": [node], "links": [{"source": "missing", "target": "first"}]},
        {"nodes": [{**node, "tool": "shell_exec"}]},
        {"nodes": [{**node, "arguments": {"query": "Hello", "allow_dangerous": True}}]},
        {"nodes": [{**node, "execution_authorized": True}]},
        {"nodes": [{**node, "arguments": {"query": "x" * 5000}}]},
        {"nodes": [node], "owner_approved": True},
    ]
    for body in bad:
        response = await client.post("/api/jarvis/inspect-plan", json=body)
        assert response.status_code == 422, response.text
