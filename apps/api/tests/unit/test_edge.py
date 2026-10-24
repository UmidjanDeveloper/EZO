"""The edge guard refuses unauthenticated and oversized requests before the body is read."""

from __future__ import annotations

from typing import Any

from starlette.types import Message, Receive, Scope, Send

from ezo_api.security.edge import AUTHENTICATED, FAILED_AUTH_PER_MINUTE, EdgeGuardMiddleware

TOKEN = "edge-guard-test-token-with-enough-length"


class Probe:
    """An inner app that records whether it ran and reads the whole body."""

    def __init__(self) -> None:
        self.called = False
        self.scope: Scope = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.called = True
        self.scope = scope
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def call(
    guard: EdgeGuardMiddleware,
    *,
    path: str = "/api/chat",
    method: str = "POST",
    headers: dict[str, str] | None = None,
    chunks: list[bytes] | None = None,
) -> tuple[int, list[Message], int]:
    """(status, sent messages, number of body reads)."""
    reads = 0
    pending = list(chunks if chunks is not None else [b""])

    async def receive() -> Message:
        nonlocal reads
        reads += 1
        body = pending.pop(0) if pending else b""
        return {"type": "http.request", "body": body, "more_body": bool(pending)}

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    scope: dict[str, Any] = {
        "type": "http",
        "path": path,
        "method": method,
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    await guard(scope, receive, send)
    return sent[0]["status"], sent, reads


def guard(probe: Probe, token: str | None = TOKEN, limit: int = 1000) -> EdgeGuardMiddleware:
    return EdgeGuardMiddleware(probe, token=token, max_body_bytes=limit)


async def test_missing_or_wrong_token_is_refused_before_the_body_is_read() -> None:
    probe = Probe()
    edge = guard(probe)
    for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": f"Basic {TOKEN}"}):
        status, sent, reads = await call(edge, headers={**headers, "Content-Length": "999999999"})
        assert status == 401 and reads == 0 and not probe.called
        assert b"unauthorized" in sent[1]["body"]


async def test_failed_attempts_share_one_small_budget() -> None:
    probe = Probe()
    edge = guard(probe)
    statuses = [(await call(edge))[0] for _ in range(FAILED_AUTH_PER_MINUTE + 2)]
    assert statuses[:FAILED_AUTH_PER_MINUTE] == [401] * FAILED_AUTH_PER_MINUTE
    assert statuses[-1] == 429
    # The owner is never slowed down by an attacker's failures.
    status, _, _ = await call(edge, headers={"Authorization": f"Bearer {TOKEN}"})
    assert status == 200 and probe.scope["state"][AUTHENTICATED] is True


async def test_body_limits_for_declared_and_streamed_bodies() -> None:
    probe = Probe()
    edge = guard(probe, limit=10)
    owner = {"Authorization": f"Bearer {TOKEN}"}
    status, _, reads = await call(edge, headers={**owner, "Content-Length": "11"})
    assert status == 413 and reads == 0 and not probe.called
    status, _, _ = await call(edge, headers={**owner, "Content-Length": "x"})
    assert status == 400
    status, sent, _ = await call(edge, headers=owner, chunks=[b"123456", b"789012"])
    assert status == 413 and b"too_large" in sent[1]["body"]
    status, _, _ = await call(
        edge, headers={**owner, "Content-Length": "10"}, chunks=[b"0123456789"]
    )
    assert status == 200


async def test_public_paths_preflight_and_local_mode_pass() -> None:
    probe = Probe()
    edge = guard(probe)
    assert (await call(edge, path="/api/health", method="GET"))[0] == 200
    assert (await call(edge, path="/", method="GET"))[0] == 200
    assert (await call(edge, method="OPTIONS"))[0] == 200
    local = guard(Probe(), token=None)
    status, _, _ = await call(local)
    assert status == 200


async def test_local_mode_refuses_cross_site_state_changes_before_the_route() -> None:
    """F23: a page on another site cannot make the owner's browser POST to a local API."""
    probe = Probe()
    edge = EdgeGuardMiddleware(
        probe, token=None, max_body_bytes=1000, allowed_origins=["http://localhost:3000/"]
    )
    for origin in ("https://evil.example", "null", "http://localhost:3001"):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            status, sent, reads = await call(
                edge,
                path="/api/student/uploads",
                method=method,
                headers={"Origin": origin, "Content-Type": "text/plain"},
            )
            assert status == 403 and reads == 0 and not probe.called
            assert b"cross_site" in sent[1]["body"]
    # The configured web app, non-browser clients (no Origin) and reads still work.
    assert (await call(edge, headers={"Origin": "http://localhost:3000"}))[0] == 200
    assert (await call(edge))[0] == 200
    assert (await call(edge, method="GET", headers={"Origin": "https://evil.example"}))[0] == 200


async def test_token_mode_does_not_need_the_origin_check() -> None:
    probe = Probe()
    edge = guard(probe)
    owner = {"Authorization": f"Bearer {TOKEN}", "Origin": "capacitor://localhost"}
    assert (await call(edge, headers=owner))[0] == 200
