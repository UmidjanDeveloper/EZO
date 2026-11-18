"""SMS through Eskiz.uz (notify.eskiz.uz), the owner's own account.

Configuration (server only, never stored in the database or returned by the API):
EZO_ESKIZ_EMAIL, EZO_ESKIZ_PASSWORD and optionally EZO_ESKIZ_SENDER (the approved
sender name; "4546" is Eskiz's default). Eskiz moderates message texts: a text that is
not approved for the account is refused, and that refusal is shown as the result.

A message counts as sent only when Eskiz accepts it and returns its id. A timeout after
the request was sent is reported as "outcome unknown" and never retried automatically.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

BASE = "https://notify.eskiz.uz"
TOKEN_SECONDS = 25 * 24 * 3600  # Eskiz tokens last 30 days; refresh a little earlier


class SmsError(Exception):
    def __init__(self, code: str, message: str, *, outcome_unknown: bool = False) -> None:
        self.code = code
        self.message = message
        self.outcome_unknown = outcome_unknown
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class SmsReceipt:
    phone: str
    message_id: str
    status: str


class EskizClient:
    def __init__(
        self,
        email: str,
        password: str,
        sender: str = "4546",
        *,
        base_url: str = BASE,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not email or not password:
            raise ValueError("Eskiz email and password are required")
        self._email = email
        self._password = password
        self.sender = sender or "4546"
        self._base = base_url.rstrip("/")
        self._transport = transport
        self._token: str | None = None
        self._token_until = 0.0

    def _redact(self, text: str) -> str:
        for secret in (self._password, self._token or ""):
            if secret:
                text = text.replace(secret, "***")
        return text

    async def _post(self, path: str, data: dict[str, str], *, auth: bool, sends: bool) -> Any:
        headers = {"Authorization": f"Bearer {await self._login()}"} if auth else {}
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=httpx.Timeout(30.0, connect=10.0)
            ) as client:
                response = await client.post(f"{self._base}{path}", data=data, headers=headers)
        except httpx.TimeoutException:
            raise SmsError(
                "timeout", "Eskiz did not answer in time.", outcome_unknown=sends
            ) from None
        except httpx.HTTPError:
            raise SmsError(
                "unreachable", "Eskiz could not be reached.", outcome_unknown=sends
            ) from None
        try:
            body = response.json()
        except ValueError:
            body = None
        if response.status_code == 401 and auth:
            self._token = None
        if response.status_code >= 400 or not isinstance(body, dict):
            detail = ""
            if isinstance(body, dict):
                detail = str(body.get("message") or body.get("error") or "")[:200]
            raise SmsError(
                "rejected",
                self._redact(
                    f"Eskiz refused the request (HTTP {response.status_code}) {detail}"
                ).strip(),
            )
        return body

    async def _login(self) -> str:
        if self._token and time.monotonic() < self._token_until:
            return self._token
        body = await self._post(
            "/api/auth/login",
            {"email": self._email, "password": self._password},
            auth=False,
            sends=False,
        )
        token = (
            (body.get("data") or {}).get("token") if isinstance(body.get("data"), dict) else None
        )
        if not isinstance(token, str) or not token:
            raise SmsError("login_failed", "Eskiz did not accept the email and password.")
        self._token = token
        self._token_until = time.monotonic() + TOKEN_SECONDS
        return token

    async def send(self, phone: str, text: str) -> SmsReceipt:
        body = await self._post(
            "/api/message/sms/send",
            {"mobile_phone": phone, "message": text[:900], "from": self.sender},
            auth=True,
            sends=True,
        )
        message_id = body.get("id")
        if message_id in (None, ""):
            raise SmsError(
                "unverified", "Eskiz's answer does not confirm the message.", outcome_unknown=True
            )
        return SmsReceipt(
            phone=phone, message_id=str(message_id), status=str(body.get("status") or "")
        )
