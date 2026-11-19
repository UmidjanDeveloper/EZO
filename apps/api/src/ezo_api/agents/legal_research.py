"""LegalResearchAgent: answers about Uzbekistan's legislation from official texts only.

Workflow (each step is a logged tool call):

    official_search (synchronized official texts, both Uzbek scripts; outdated acts
    only for history questions)
    → verify_official_document for the top act(s) when its source is enabled
      verified → status as recorded; changed → new revision, search again;
      failed   → the last verified time is disclosed, "in force" is never claimed
    → optional revision comparison ("eski va yangi tahrirni solishtir")
    → answer with numbered citations (EzoCore verifies the citation numbers)

Without synchronized official documents EZO says so and gives general orientation only.
Laws are never "remembered" from model weights as facts.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select

from ezo_api.agents.base import (
    Agent,
    AgentPlan,
    AgentTurn,
    GatherContext,
    Gathered,
    call_tool,
    run_tool,
)
from ezo_api.agents.catalog import AGENTS
from ezo_api.core.intent import Intent
from ezo_api.core.text import normalize
from ezo_api.db.models import LegalDocument
from ezo_api.documents.compare import compare_texts
from ezo_api.knowledge.retrieval.sources import SourceRef, number_sources
from ezo_api.official.base import OfficialSourceError
from ezo_api.official.collections import COLLECTIONS
from ezo_api.official.lookup import find_act, named_act
from ezo_api.official.sync import official_knowledge_ids
from ezo_api.tools.official_tools import revision_texts
from ezo_api.translation.translit import to_cyrillic

MAX_LIVE_CHECKS = 2
_COLLECTION = re.compile(
    r"(asosiy|kerakli|barcha|hamma|zarur|основн|необходим|core|essential)\w*\s+"
    r"(qonun|hujjat|akt|норматив|закон|документ|act|law)\w*.{0,60}?"
    r"(o'rgan|yukla|o'qib chiq|sinxron|изучи|загрузи|learn|load)|"
    r"hokimiyat\w*\s+(uchun\s+)?(to'plam|qonun|hujjat)\w*.{0,40}?(o'rgan|yukla)|"
    r"lex\.?uz\w*.{0,40}?(o'rgan|yukla|o'qib chiq|изучи|learn)"
)


def wants_collection(text: str) -> bool:
    """ "Hokimiyat uchun asosiy qonunlarni o'rgan", "lex.uz'ni o'rganib chiq" — the ready-made
    set of core acts (not one named act: "Mehnat kodeksini o'rgan" reads that code)."""
    return bool(_COLLECTION.search(normalize(text))) and named_act(text) is None


_HISTORY = re.compile(
    r"\b(eski|oldingi|avvalgi|tahrir|redaksiya|tarix|o'zgargan|solishtir|previous|old version|"
    r"revision|history|compare|прежн|предыдущ|редакци|истори|сравн|изменил|эски|олдинги|таҳрир|солиштир)"
)
_COMPARE = re.compile(
    r"\b(solishtir|farq|o'zgargan|compare|differen|сравн|отлич|изменил|солиштир|фарқ)"
)

LEGAL_INSTRUCTIONS = (
    "Role: legal research assistant for Uzbekistan. Answer ONLY from the numbered official "
    "sources below.\n"
    "- For every act you rely on give: official title, number, adoption date, status, the "
    "article/section, the date EZO last retrieved it, and the official URL — exactly as the "
    "source header states; cite with [n].\n"
    "- Status: repeat the status line exactly. If it is 'not confirmed', say the status could "
    "not be confirmed and NEVER say the act is currently in force.\n"
    "- Never invent document numbers, dates, articles, quotes or acts. If the sources do not "
    "answer the question, say exactly what is missing.\n"
    "- Quote article text only from the sources; mark paraphrases as such.\n"
    "- End with one line: informational help, not legal advice; check https://lex.uz for the "
    "authoritative text."
)
NO_SOURCES_NOTE = (
    "No synchronized official legal documents are available in this EZO installation, so no "
    "official text was consulted. Say this plainly. Give only general orientation; do NOT state "
    "document numbers, dates, article contents or whether an act is in force unless you are "
    "certain, and tell the user to verify on https://lex.uz. The owner can enable LEX.UZ "
    "(EZO_OFFICIAL_SOURCES=lexuz in .env, after reviewing its terms); then EZO reads the core "
    "acts (“hokimiyat uchun asosiy qonunlarni o‘rgan”) and any act a question names."
)
NO_MATCH_NOTE = (
    "The synchronized official documents contain nothing relevant to this question. Say so; do "
    "not answer from memory as if it were official. Suggest synchronizing the relevant act."
)


class LegalResearchAgent(Agent):
    spec = AGENTS[Intent.LEGAL_RESEARCH]

    def plan(self, turn: AgentTurn) -> AgentPlan:
        return AgentPlan(
            route=self.spec.route,
            context_mode=self.spec.context_mode,
            instructions=LEGAL_INSTRUCTIONS,
            steps=(
                "official_search",
                "live_verification",
                "compare_revisions",
                "compose_prompt",
                "generate",
            ),
        )

    async def gather(self, ctx: GatherContext) -> Gathered:
        gathered = Gathered()
        tools = ctx.tools
        text = ctx.turn.text
        norm = normalize(text)
        if "lexuz" in tools.services.settings.official_sources:
            if wants_collection(text):
                await self._start_collection(ctx, gathered)
                return gathered
            await self._fetch_named_act(ctx, gathered)
        if not await official_knowledge_ids(tools.session, tools.user_id, include_outdated=True):
            gathered.notes.append(NO_SOURCES_NOTE)
            return gathered
        include_outdated = bool(_HISTORY.search(norm))
        args = {"query": text[:500], "limit": 5, "include_outdated": include_outdated}
        sources = await run_tool(gathered, tools, "official_search", args)
        if not sources:
            gathered.notes.append(NO_MATCH_NOTE)
            return gathered

        changed = False
        checked: list[str] = []
        for legal_id in _distinct_legal_ids(sources)[:MAX_LIVE_CHECKS]:
            result = await call_tool(
                gathered, tools, "verify_official_document", {"legal_document_id": legal_id}
            )
            data = result.data or {}
            legal = await tools.session.get(LegalDocument, uuid.UUID(legal_id))
            label = (legal.document_number or legal.title[:80]) if legal else legal_id
            state = data.get("state")
            last = data.get("last_verified_at") or "unknown"
            not_current = "do not claim the act is currently in force."
            if state == "verified":
                checked.append(
                    f"{label}: the official text was re-checked live at "
                    f"{data.get('checked_at')} and is unchanged."
                )
            elif state == "changed":
                changed = True
                checked.append(
                    f"{label}: the official text changed; EZO saved the new revision and uses it."
                )
            elif state == "disabled":
                checked.append(
                    f"{label}: live verification is not possible right now "
                    f"({data.get('message')}). Last verified retrieval: {last}. Say this and "
                    + not_current
                )
            else:
                checked.append(
                    f"{label}: live verification FAILED ({result.error}). Last verified "
                    f"retrieval: {last}. Tell the user this date and " + not_current
                )
        if changed:
            sources = await run_tool(gathered, tools, "official_search", args)
        if checked:
            gathered.notes.append("Currentness checks:\n- " + "\n- ".join(checked))

        if _COMPARE.search(norm):
            note = await self._comparison(ctx, sources)
            if note:
                gathered.notes.append(note)
        gathered.sources = number_sources(sources)
        return gathered

    async def _start_collection(self, ctx: GatherContext, gathered: Gathered) -> None:
        """ "Hokimiyat uchun asosiy qonunlarni o'rgan": read the ready-made set in the
        background (about 15 s per act at LEX.UZ's polite pace)."""
        tools = ctx.tools
        services = tools.services
        collection = COLLECTIONS["hokimiyat"]
        try:
            run_id = await services.official.start_detached(
                services.db.sessionmaker,
                tools.user_id,
                collection.connector,
                [i.source_doc_id for i in collection.items],
                collection.language,
            )
        except OfficialSourceError as exc:
            gathered.tool_calls.append(
                {"tool": "official_collection", "ok": False, "summary": "", "error": exc.message}
            )
            gathered.notes.append(f"Starting the LEX.UZ reading failed: {exc.message}. Say so.")
            return
        gathered.tool_calls.append(
            {
                "tool": "official_collection",
                "ok": True,
                "summary": f"{collection.key}: {len(collection.items)} acts, run {run_id}",
                "error": None,
            }
        )
        minutes = max(1, round(len(collection.items) * 15 / 60))
        titles = "; ".join(i.title for i in collection.items)
        gathered.notes.append(
            f"EZO STARTED reading {len(collection.items)} core acts from LEX.UZ in the background "
            f"(about {minutes} minutes at LEX.UZ's polite pace; nothing is finished yet): "
            f"{titles}. Tell the user the list in their language, that EZO reads each act's "
            "full official text and its status from LEX.UZ, and that they can ask questions "
            "about these acts once it is done. Any other act is fetched when a question names "
            "it (e.g. “Oila kodeksi bo‘yicha …”)."
        )

    async def _fetch_named_act(self, ctx: GatherContext, gathered: Gathered) -> None:
        """The question names an act EZO has not read yet: find it on LEX.UZ and read it now
        (one act per question; about 15–30 s)."""
        tools = ctx.tools
        services = tools.services
        act = named_act(ctx.turn.text)
        if act is None:
            return
        want = to_cyrillic(act.queries()[0]).lower() if act.queries() else ""
        titles = await tools.session.scalars(
            select(LegalDocument.title).where(LegalDocument.user_id == tools.user_id)
        )
        if want and any(want in to_cyrillic(t or "").lower() for t in titles):
            return
        if tools.on_activity is not None:
            tools.on_activity("searching")
        try:
            connector = services.official.connector("lexuz")
            client = services.official.client(connector, max_requests=4)
            hit = await find_act(connector, client, act)  # type: ignore[arg-type]
        except OfficialSourceError as exc:
            gathered.tool_calls.append(
                {"tool": "lexuz_find", "ok": False, "summary": "", "error": exc.message}
            )
            gathered.notes.append(
                f"EZO tried to find the act on LEX.UZ but could not ({exc.message}). Say so."
            )
            return
        if hit is None:
            gathered.tool_calls.append(
                {"tool": "lexuz_find", "ok": True, "summary": "no match", "error": None}
            )
            gathered.notes.append(
                "EZO searched LEX.UZ for the act the user named and found no matching act. "
                "Say so and ask for its exact title or LEX.UZ number."
            )
            return
        gathered.tool_calls.append(
            {"tool": "lexuz_find", "ok": True, "summary": f"{hit.source_doc_id}", "error": None}
        )
        if tools.on_activity is not None:
            tools.on_activity("reading")
        async with services.db.sessionmaker() as session:
            try:
                run = await services.official.start(
                    session, tools.user_id, "lexuz", [hit.source_doc_id], "uz"
                )
            except OfficialSourceError as exc:
                gathered.notes.append(f"Reading the act from LEX.UZ failed: {exc.message}.")
                return
            ok = run.status in ("completed",) and not run.counts.get("failed")
            gathered.tool_calls.append(
                {
                    "tool": "official_sync",
                    "ok": ok,
                    "summary": f"lexuz {hit.source_doc_id}: {run.status}",
                    "error": run.error,
                }
            )
            if ok:
                gathered.notes.append(
                    f"EZO just read «{hit.title}» (LEX.UZ {hit.source_doc_id}) from LEX.UZ for "
                    "this question; mention that in one short line."
                )

    async def _comparison(self, ctx: GatherContext, sources: list[SourceRef]) -> str | None:
        ids = _distinct_legal_ids(sources)
        if not ids:
            return None
        legal = await ctx.tools.session.get(LegalDocument, uuid.UUID(ids[0]))
        if legal is None:
            return None
        history = await revision_texts(ctx.tools, legal)
        if len(history) < 2:
            return (
                f"Only one revision of {legal.document_number or legal.title} has been retrieved "
                "by EZO, so no earlier text is available to compare. Say so."
            )
        (old, old_text), (new, new_text) = history[-2], history[-1]
        comparison = compare_texts(old_text, new_text)
        return (
            f"Revision comparison of {legal.document_number or legal.title} (EZO-retrieved texts: "
            f"revision {old.revision_number} retrieved {old.retrieved_at:%Y-%m-%d} vs revision "
            f"{new.revision_number} retrieved {new.retrieved_at:%Y-%m-%d}; these are EZO's "
            "retrieval dates, not official amendment dates):\n" + comparison.to_markdown(limit=15)
        )


def _distinct_legal_ids(sources: list[SourceRef]) -> list[str]:
    ids: list[str] = []
    for source in sources:
        legal: dict[str, Any] = source.extra.get("legal") or {}
        value = legal.get("legal_document_id")
        if value and value not in ids:
            ids.append(str(value))
    return ids
