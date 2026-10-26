"""Request text → validated JARVIS plan, by fixed rules (no model, no authority).

The planner recognises a small, explicit set of document-workflow requests in Uzbek
(Latin/Cyrillic), English and Russian, such as the owner's reference scenario:

    "Downloads ichidagi eng oxirgi faylni och, PDF'ga aylantir, foiz ko'rsatkichlarini
     undan oldingi faylga o'xshatib tayyorla va Telegram'da Baxtiyorga yubor."

Anything it does not recognise is refused with a reason; it never guesses an action,
a folder or a recipient. Model replies and file contents never reach this module.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from ezo_api.core.text import normalize


class PlanError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class DocumentWorkflowPlan:
    root: str = "downloads"
    """The only folder alias a request may name; the device maps it to the folder the
    owner explicitly authorised on that device."""
    compare_previous: bool = False
    convert_pdf: bool = False
    percentages: bool = False
    recipient: str | None = None
    """A recipient label as the owner named it; resolved only against verified recipients."""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "compare_previous": self.compare_previous,
            "convert_pdf": self.convert_pdf,
            "percentages": self.percentages,
            "recipient": self.recipient,
        }


_DOWNLOADS = re.compile(r"\b(downloads?|yuklab ?olingan(lar)?|zagruzki|загрузк)", re.I)
_LATEST = re.compile(
    r"(eng (oxirgi|so'nggi|yangi)|latest|newest|most recent|последн|самый новый|охирги)", re.I
)
_PREVIOUS = re.compile(r"(oldingi|avvalgi|undan oldingi|previous|prior|предыдущ|олдинги)", re.I)
_PDF = re.compile(r"\bpdf", re.I)
_PERCENT = re.compile(r"(foiz|percent|%|процент|фоиз)", re.I)
_TELEGRAM = re.compile(r"(telegram|телеграм)", re.I)
# "Baxtiyorga yubor", "send it to Baxtiyor", "отправь Бахтиёру"
_RECIPIENT = (
    re.compile(r"(?:telegram\S*\s+)?([A-ZЀ-Я][\wЀ-ӿ'ʻ’-]{1,40}?)(?:ga|ka|qa)\s+yubor", re.U),
    re.compile(r"send(?: it| them| the \w+)? to ([A-Z][\w'-]{1,40})", re.U),
    re.compile(r"отправ\w*\s+([А-ЯЁ][а-яё-]{1,40}?)(?:у|ю|е)?\b", re.U),
)


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("ʻ", "'").replace("’", "'").replace("‘", "'")
    return text


def plan_document_workflow(text: str) -> DocumentWorkflowPlan:
    """Parse a document-workflow request; raise PlanError when it is not one."""
    raw = _clean(text)
    lowered = normalize(raw).lower()
    if not _DOWNLOADS.search(lowered):
        raise PlanError(
            "unsupported_request",
            "Only requests about the authorised Downloads folder are supported.",
        )
    if not _LATEST.search(lowered):
        raise PlanError("unsupported_request", "Say which file: the latest (eng oxirgi) file.")
    recipient = None
    if _TELEGRAM.search(lowered):
        for pattern in _RECIPIENT:
            match = pattern.search(raw)
            if match:
                recipient = match.group(1).strip("'-")
                break
        if recipient is None:
            raise PlanError(
                "recipient_unclear", "Who should receive it on Telegram? Name the person."
            )
    plan = DocumentWorkflowPlan(
        compare_previous=bool(_PREVIOUS.search(lowered)),
        convert_pdf=bool(_PDF.search(lowered)),
        percentages=bool(_PERCENT.search(lowered)),
        recipient=recipient,
    )
    if plan.percentages and not plan.compare_previous:
        raise PlanError(
            "unsupported_request",
            "Percentages are prepared by comparing with the previous file; say so explicitly.",
        )
    if not (plan.convert_pdf or plan.percentages or plan.recipient):
        raise PlanError(
            "unsupported_request", "Nothing to do: ask for a PDF, percentages or sending."
        )
    return plan
