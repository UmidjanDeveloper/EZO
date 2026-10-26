"""Telegram Bot API adapter: recipient linking and document delivery with real receipts.

Constraints honoured (Telegram Bot API):
- a bot can only message a chat that started it, so every recipient is linked by the
  person sending ``/start <one-time code>`` to EZO's bot; EZO stores that chat id;
- a delivery is only recorded as delivered when Telegram answers ``ok: true`` with a
  ``message_id`` for exactly that chat. Anything else is a failure with its reason.

The bot token is server configuration (``EZO_TELEGRAM_BOT_TOKEN``); it is never logged,
stored in the database, returned by the API or put into error messages.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

API = "https://api.telegram.org"
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024


class _RedactBotURL(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # HTTPX INFO records include full request URLs (and hence bot credentials).
        record.msg = re.sub(
            r"https://api\.telegram\.org/bot[^/\s]+/",
            "https://api.telegram.org/bot[REDACTED]/",
            record.getMessage(),
        )
        record.args = ()
        return True


logging.getLogger("httpx").addFilter(_RedactBotURL())


class TelegramError(Exception):
    def __init__(self, code: str, message: str, *, outcome_unknown: bool = False) -> None:
        self.code = code
        self.message = message
        self.outcome_unknown = outcome_unknown
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class StartMessage:
    chat_id: str
    name: str


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    chat_id: str
    message_id: int
    date: int
    document_sha256: str
    file_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": "telegram",
            "chat_id": self.chat_id,
            "message_id": self.message_id,
            "date": self.date,
            "document_sha256": self.document_sha256,
            "file_name": self.file_name,
        }


class TelegramClient:
    def __init__(self, token: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        if not token or ":" not in token:
            raise ValueError("A Telegram bot token is required")
        self._token = token
        self._transport = transport

    def _url(self, method: str) -> str:
        return f"{API}/bot{self._token}/{method}"

    async def _call(
        self,
        method: str,
        *,
        data: dict[str, Any] | None = None,
        files: Any = None,
        sends: bool = False,
    ) -> Any:
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=httpx.Timeout(30.0, connect=10.0)
            ) as client:
                response = await client.post(self._url(method), data=data, files=files)
        except httpx.TimeoutException:
            # A send may have reached Telegram before the timeout: never auto-retry it.
            raise TelegramError(
                "timeout", "Telegram did not answer in time.", outcome_unknown=sends
            ) from None
        except httpx.HTTPError:
            raise TelegramError(
                "unreachable", "Telegram could not be reached.", outcome_unknown=sends
            ) from None
        try:
            body = response.json()
        except ValueError:
            raise TelegramError(
                "bad_response",
                f"Telegram answered HTTP {response.status_code}.",
                outcome_unknown=sends,
            ) from None
        if not isinstance(body, dict) or body.get("ok") is not True:
            description = (
                str((body or {}).get("description", ""))[:160] if isinstance(body, dict) else ""
            )
            raise TelegramError(
                "rejected",
                f"Telegram refused the request: {description.replace(self._token, chr(42) * 3)}",
            )
        return body.get("result")

    async def bot_username(self) -> str:
        result = await self._call("getMe")
        username = result.get("username") if isinstance(result, dict) else None
        if not username:
            raise TelegramError("bad_response", "Telegram did not return the bot name.")
        return str(username)

    async def find_start(self, code: str) -> StartMessage | None:
        """The private chat that sent exactly ``/start <code>`` (recent updates only)."""
        result = await self._call(
            "getUpdates", data={"limit": 100, "allowed_updates": '["message"]'}
        )
        for update in result if isinstance(result, list) else []:
            message = update.get("message") if isinstance(update, dict) else None
            if not isinstance(message, dict):
                continue
            chat = message.get("chat") or {}
            if chat.get("type") != "private" or message.get("text") != f"/start {code}":
                continue
            sender = message.get("from") or {}
            name = " ".join(
                str(part) for part in (sender.get("first_name"), sender.get("last_name")) if part
            ) or str(sender.get("username") or "")
            return StartMessage(chat_id=str(chat.get("id")), name=name[:120])
        return None

    async def send_document(
        self, chat_id: str, data: bytes, file_name: str, caption: str
    ) -> DeliveryReceipt:
        if not data or len(data) > MAX_DOCUMENT_BYTES:
            raise TelegramError("too_large", "The document is empty or over 20 MB.")
        result = await self._call(
            "sendDocument",
            data={"chat_id": chat_id, "caption": caption[:1000]},
            files={"document": (file_name, data, "application/pdf")},
            sends=True,
        )
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("message_id"), int)
            or str((result.get("chat") or {}).get("id")) != str(chat_id)
            or not result.get("document")
        ):
            raise TelegramError(
                "unverified",
                "Telegram's answer does not confirm this delivery.",
                outcome_unknown=True,
            )
        return DeliveryReceipt(
            chat_id=str(chat_id),
            message_id=int(result["message_id"]),
            date=int(result.get("date") or 0),
            document_sha256=hashlib.sha256(data).hexdigest(),
            file_name=file_name,
        )
