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
from ezo_api.official.sync import official_knowledge_ids
from ezo_api.tools.official_tools import revision_texts

MAX_LIVE_CHECKS = 2
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
    "(EZO_OFFICIAL_SOURCES=lexuz, after reviewing its terms) and synchronize documents by their "
    "LEX.UZ number."
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
