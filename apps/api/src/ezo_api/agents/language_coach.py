# ruff: noqa: E501  (prompt text is kept as written, one instruction per line)
"""LanguageCoachAgent: real practice sessions with state, not just a prompt.

Each turn (decided without a model call):

    progress question  → facts from past sessions (trends, recurring mistakes, goals)
    "finish"/"feedback" → assessment of the whole session (reasoning route, validated)
                          → metrics, mistakes and vocabulary stored → report artifact
    anything else       → practice: start or continue a session, record the turn,
                          IELTS-style part/question flow, recurring weak points woven in

Practice replies use the cheap chat route. Mistakes are collected silently and
discussed after the section or session, not after every sentence. Bands are always
*estimates* from a simulator; pronunciation is only a transcript-assisted estimate.
"""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy import select

from ezo_api.agents.base import Agent, AgentPlan, AgentTurn, GatherContext, Gathered, call_tool
from ezo_api.agents.catalog import AGENTS
from ezo_api.agents.llm import complete, extract_json, sources_block
from ezo_api.core.intent import Intent
from ezo_api.core.text import normalize
from ezo_api.db.base import utcnow
from ezo_api.db.models import LanguageSession, LanguageTurn, Message
from ezo_api.knowledge.retrieval.keyword import has_searchable_documents
from ezo_api.knowledge.retrieval.sources import number_sources
from ezo_api.language import exam
from ezo_api.language import service as lang
from ezo_api.language.analysis import describe
from ezo_api.language.assessment import (
    ASSESSMENT_SYSTEM,
    CEFR_ASSESSMENT_SYSTEM,
    Assessment,
    validate,
)
from ezo_api.language.ielts import IeltsState, advance
from ezo_api.language.modes import (
    CEFR_GUIDE,
    MODE_GUIDE,
    detect_cefr,
    detect_command,
    detect_goal,
    detect_mode,
)
from ezo_api.language.report import build_report, report_title
from ezo_api.language.targets import LANGUAGE_ACTIVITY, detect_practice_language, language_name
from ezo_api.providers.router import AllProvidersFailedError, StreamInterruptedError
from ezo_api.providers.types import ChatMessage

logger = logging.getLogger(__name__)

TRANSCRIPT_CHARS = 30_000
LANGUAGE_NAMES = {"uz": "Uzbek (Latin script)", "en": "English", "ru": "Russian"}

_ACTIVITY = re.compile(LANGUAGE_ACTIVITY)

COACH_INSTRUCTIONS = """Role: EZO's language coach and speaking examiner simulator (English by default; EZO's notes name the practised language).
- Practice and exam turns are in THE PRACTISED LANGUAGE named in EZO's notes, even when the learner writes in Uzbek or Russian; this overrides the general reply-language rule for practice. Explanations, feedback and progress answers are in the learner's own language.
- Never call yourself an official examiner and never give an "official" score or certificate. In IELTS mode you are an "IELTS-style examiner simulator" and any band is an "estimated band"; in exam mode you are EZO's exam simulator and the level is an estimate.
- Do NOT correct every mistake during practice: respond naturally and keep the conversation going. Correct briefly only if a mistake makes the meaning unclear. Detailed feedback comes after the section or session.
- One question at a time. Keep your turns short so the learner speaks more than you.
- Follow EZO's notes below exactly (mode, level, the next question, recurring weak points, assessment results).
- For a word-by-word pronunciation check, point the learner to the “Talaffuz” card on the Til mashqlari (Language) page: they read a sentence aloud and EZO marks each word (a recognition-based estimate, not phoneme-level). Never claim you heard their pronunciation in this chat."""

OFFLINE_NOTE = (
    "No AI provider is connected: EZO cannot run a practice conversation or estimate bands. "
    "Tell the user briefly; measured numbers from past sessions are still available."
)


def uses_cefr(session: LanguageSession) -> bool:
    """The exam simulator and every language but English are assessed by CEFR level (EZO's
    0–9 criteria scale), never with IELTS bands."""
    return session.mode == "exam" or (session.language or "en") != "en"


class LanguageCoachAgent(Agent):
    spec = AGENTS[Intent.LANGUAGE_COACH]

    def plan(self, turn: AgentTurn) -> AgentPlan:
        return AgentPlan(
            route="chat",  # practice replies: cheap route; assessments use "reasoning" in gather
            context_mode="teacher",
            instructions=COACH_INSTRUCTIONS,
            steps=("language_session", "practice_or_assess", "compose_prompt", "generate"),
        )

    async def gather(self, ctx: GatherContext) -> Gathered:
        gathered = Gathered()
        tools = ctx.tools
        db = tools.session
        turn = ctx.turn
        active = await lang.active_session(db, tools.user_id, tools.conversation_id)
        command = detect_command(turn.text, has_active_session=active is not None)
        trace = {"tool": "language_session", "ok": True, "error": None}

        goal = detect_goal(turn.text)
        if goal is not None:
            saved = await lang.set_goal(
                db,
                tools.user_id,
                description=goal.description,
                target_band=goal.target_band,
                cefr=goal.cefr,
            )
            gathered.notes.append(
                f"Saved the learner's goal: {saved.description}"
                + (f" (target band {saved.target_band:g})" if saved.target_band else "")
                + (f" (target level {saved.cefr_target})" if saved.cefr_target else "")
                + ". Acknowledge it in one sentence."
            )

        if command == "progress":
            await self._progress(ctx, gathered)
            gathered.tool_calls.append({**trace, "summary": "progress"})
            return gathered
        if command == "finish" and active is not None:
            await self._finish(ctx, gathered, active)
            gathered.tool_calls.append({**trace, "summary": f"finish session {active.id}"})
            return gathered
        if tools.services.router.is_offline:
            gathered.notes.append(OFFLINE_NOTE)
            return gathered

        mode = detect_mode(turn.text)
        wanted = detect_practice_language(turn.text)
        norm = normalize(turn.text)
        switching_language = (
            active is not None
            and wanted is not None
            and wanted != active.language
            # A short command ("endi nemis tilida gaplashamiz"), not a learner's answer that
            # happens to mention a language.
            and len(norm.split()) <= 12
            and (mode is not None or bool(_ACTIVITY.search(norm)))
        )
        starting = (
            active is None or (mode is not None and mode != active.mode) or switching_language
        )
        if starting:
            practice = "en" if mode == "ielts" else (wanted or "en")
            active = await self._start(ctx, gathered, mode, practice)
        else:
            assert active is not None
            await self._record_coach_reply(ctx, active)
            await lang.add_turn(
                db,
                active,
                role="learner",
                text=turn.text,
                channel=turn.channel,
                speech_seconds=turn.speech_seconds,
            )
        gathered.tool_calls.append(
            {
                **trace,
                "summary": f"{'start' if starting else 'turn'} mode={active.mode} part={active.ielts_part}",
            }
        )

        name = language_name(active.language)
        gathered.notes.append(
            f"Practised language: {name}. Ask and answer the practice or exam turns in {name}."
        )
        if active.mode == "exam":
            meta = dict(active.meta or {})
            exam_step = exam.advance(meta, learner_answered=not starting)
            active.meta = meta
            if exam_step.finished:
                gathered.notes.append(exam_step.instruction)
                await self._finish(ctx, gathered, active)
                return gathered
            gathered.notes.append(f"{exam.EXAMINER_GUIDE}\n{exam_step.instruction}")
        elif active.mode == "ielts":
            state = IeltsState.from_dict((active.meta or {}).get("ielts"))
            step = advance(state, learner_answered=not starting)
            active.meta = {**(active.meta or {}), "ielts": state.to_dict()}
            active.ielts_part = step.part
            if step.finished:
                gathered.notes.append(step.instruction)
                await self._finish(ctx, gathered, active)
                return gathered
            gathered.notes.append(f"IELTS-style test, Part {step.part}. {step.instruction}")
        else:
            guide = MODE_GUIDE.get(active.mode) or MODE_GUIDE["free_conversation"]
            gathered.notes.append(guide.replace("English", name))
        if active.cefr_target:
            gathered.notes.append(CEFR_GUIDE[active.cefr_target].replace("English", name))
        await db.flush()
        return gathered

    # --- practice ---------------------------------------------------------------------------

    async def _start(
        self, ctx: GatherContext, gathered: Gathered, mode: str | None, practice: str = "en"
    ) -> LanguageSession:
        tools = ctx.tools
        db = tools.session
        cefr = detect_cefr(ctx.turn.text)
        if cefr is None:
            goals = (await lang.progress(db, tools.user_id, limit=1)).goals
            cefr = goals[0].cefr_target if goals else None
        session = await lang.start_session(
            db,
            user_id=tools.user_id,
            conversation_id=tools.conversation_id,
            project_id=tools.project_scope,
            mode=mode or "free_conversation",
            cefr=cefr,
            ui_language=ctx.turn.language,
            language=practice,
        )
        recurring = (
            await lang.recurring_mistakes(db, tools.user_id, limit=3) if practice == "en" else []
        )
        gathered.notes.append(
            f"A new {session.mode.replace('_', ' ')} practice session started"
            + (f" (target level {cefr})" if cefr else "")
            + f" in {language_name(practice)}"
            + f". Greet the learner in one short sentence in their language, then continue in {language_name(practice)}."
            + (
                ""
                if mode
                else " No specific mode was asked for: start a friendly free conversation and mention in one line that an exam simulator (CEFR level), IELTS-style speaking, job interview, travel or grammar practice are also possible, in English, Russian, German, French, Turkish, Korean and other languages."
            )
        )
        if recurring:
            areas = ", ".join(r.category.replace("_", " ") for r in recurring)
            gathered.notes.append(
                f"From earlier sessions the learner often struggles with: {areas}. Naturally ask "
                "questions that make them use these structures (e.g. past events for tenses). Do NOT mention these weak points now."
            )
        return session

    async def _record_coach_reply(self, ctx: GatherContext, session: LanguageSession) -> None:
        """Store EZO's previous reply (the question the learner is answering) once."""
        tools = ctx.tools
        db = tools.session
        if tools.conversation_id is None:
            return
        last = await db.scalar(
            select(Message)
            .where(
                Message.conversation_id == tools.conversation_id,
                Message.role == "assistant",
                Message.created_at >= session.started_at,
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        meta = session.meta or {}
        if last is None or meta.get("last_coach_message") == str(last.id):
            return
        await lang.add_turn(db, session, role="coach", text=last.content)
        session.meta = {**meta, "last_coach_message": str(last.id)}

    # --- assessment -------------------------------------------------------------------------

    async def _finish(
        self, ctx: GatherContext, gathered: Gathered, session: LanguageSession
    ) -> None:
        tools = ctx.tools
        db = tools.session
        await self._record_coach_reply(ctx, session)
        turns = await lang.turns_of(db, session)
        learner_turns = [t for t in turns if t.role == "learner"]
        if not learner_turns:
            session.status = "abandoned"
            session.ended_at = utcnow()
            gathered.notes.append(
                "The session ended before the learner said anything, so there is nothing to assess. Say so and offer to start again."
            )
            return
        metrics = lang.learner_metrics(turns)
        ui_language = str((session.meta or {}).get("ui_language") or ctx.turn.language)
        data = None
        provider = model = None
        if not tools.services.router.is_offline:
            if tools.on_activity is not None:
                tools.on_activity("working")
            prompt = await self._assessment_prompt(ctx, gathered, session, turns, describe(metrics))
            try:
                completion = await complete(
                    tools.services.router,
                    "reasoning",
                    system=(CEFR_ASSESSMENT_SYSTEM if uses_cefr(session) else ASSESSMENT_SYSTEM)
                    .replace("{feedback_language}", LANGUAGE_NAMES.get(ui_language, "English"))
                    .replace("{practice_language}", language_name(session.language)),
                    messages=[ChatMessage("user", prompt)],
                    max_output_tokens=6_000,
                    language=ui_language,
                )
                gathered.tool_calls.append(
                    completion.trace("assess_language", f"{len(completion.text)} chars")
                )
                data = extract_json(completion.text)
                provider, model = completion.provider, completion.model
            except (AllProvidersFailedError, StreamInterruptedError) as exc:
                logger.warning("Language assessment failed: %s", exc)
        assessment = validate(
            data,
            learner_text="\n".join(t.text for t in learner_turns),
            learner_words=metrics.words,
            spoken_share=lang.spoken_share(turns),
        )
        if uses_cefr(session):
            # An exam or a language other than English: the criteria are on EZO's 0–9 scale and the result is the
            # CEFR estimate; no "band" is shown.
            assessment.band_low = assessment.band_high = None
        if data is None:
            assessment.notes.append(
                "No AI assessment was available (no provider or the provider failed), so only measured numbers are given."
            )
        await lang.save_assessment(db, session, assessment, metrics, turns)
        result = await call_tool(
            gathered,
            tools,
            "create_document",
            {
                "title": report_title(session, ui_language),
                "markdown": build_report(session, assessment, metrics, ui_language),
                "format": "docx",
                "artifact_type": "report",
                "metadata": {"language_session_id": str(session.id), "action": "language_report"},
                "provider": provider,
                "model": model,
            },
        )
        if result.ok:
            gathered.artifacts.append(result.data["artifact"])
            session.report_artifact_id = uuid.UUID(result.data["artifact"]["id"])
        gathered.notes.append(
            self._results_note(session, assessment, metrics_text=describe(metrics))
        )

    async def _assessment_prompt(
        self,
        ctx: GatherContext,
        gathered: Gathered,
        session: LanguageSession,
        turns: list[LanguageTurn],
        metrics_text: str,
    ) -> str:
        lines = []
        for t in turns:
            who = "Learner" if t.role == "learner" else "Coach"
            details = [f"Part {t.ielts_part}"] if t.ielts_part else []
            if t.channel == "voice":
                details.append(f"spoken, {t.speech_seconds:g} s" if t.speech_seconds else "spoken")
            label = f"{who} ({', '.join(details)})" if details else who
            lines.append(f"{label}: {t.text}")
        transcript = "\n".join(lines)[-TRANSCRIPT_CHARS:]
        prompt = (
            f"Mode: {session.mode}. Target level: {session.cefr_target or 'not set'}.\n"
            f"Computed measurements of the learner's language (exact): {metrics_text}\n"
            f"Share of spoken (voice) learner turns: {lang.spoken_share(turns):.0%}.\n\n"
            f"Transcript:\n{transcript}"
        )
        tools = ctx.tools
        if await has_searchable_documents(tools.session, tools.user_id, tools.project_scope):
            search = await call_tool(
                gathered,
                tools,
                "knowledge_search",
                {"query": "IELTS speaking band descriptors criteria", "limit": 3, "strict": True},
            )
            sources = number_sources(list(search.sources)) if search.ok else []
            if sources:
                prompt += (
                    "\n\nReference material from the learner's own files (use only if relevant):\n"
                    + sources_block(sources)
                )
        return prompt

    @staticmethod
    def _results_note(session: LanguageSession, assessment: Assessment, metrics_text: str) -> str:
        s = assessment.scores
        if uses_cefr(session):
            band_line = (
                f"{language_name(session.language)} — CEFR level estimate (simulator, not an "
                "official exam); the criteria below are on EZO's 0–9 scale, not IELTS bands."
            )
        elif assessment.band_low is not None and assessment.band_high is not None:
            band = (
                f"{assessment.band_low:g}"
                if assessment.band_low == assessment.band_high
                else f"{assessment.band_low:g}–{assessment.band_high:g}"
            )
            band_line = f"Estimated band range (simulator, not official): {band}."
        else:
            band_line = "No band estimate was given."
        criteria = ", ".join(
            f"{name} {value:g}"
            for name, value in (
                ("fluency/coherence", s.get("fluency_coherence")),
                ("vocabulary", s.get("lexical_resource")),
                ("grammar", s.get("grammatical_range_accuracy")),
            )
            if value is not None
        )
        mistakes = "; ".join(f"“{m.original}” → “{m.correction}”" for m in assessment.mistakes[:3])
        parts = [
            "The practice session is finished and was assessed. Give the learner their feedback now, in their language, warmly and concretely (at most ~10 short lines):",
            band_line,
            f"Criteria estimates: {criteria}." if criteria else "",
            f"Pronunciation: {'transcript-assisted estimate ' + format(s['pronunciation'], 'g') if s.get('pronunciation') is not None else 'not assessed'}.",
            f"Estimated level: {assessment.cefr_estimate}." if assessment.cefr_estimate else "",
            f"Measured: {metrics_text}.",
            "Strengths: " + "; ".join(assessment.strengths[:3]) if assessment.strengths else "",
            "Weaknesses: " + "; ".join(assessment.weaknesses[:3]) if assessment.weaknesses else "",
            f"Mistakes to show (quote exactly): {mistakes}." if mistakes else "",
            f"Practice target: {assessment.practice_target}" if assessment.practice_target else "",
            "Honesty notes to mention briefly: " + " ".join(assessment.notes)
            if assessment.notes
            else "",
            "A full report was saved as a file (card under your message)."
            if session.report_artifact_id
            else "",
        ]
        return "\n".join(p for p in parts if p)

    # --- progress ---------------------------------------------------------------------------

    async def _progress(self, ctx: GatherContext, gathered: Gathered) -> None:
        tools = ctx.tools
        progress = await lang.progress(tools.session, tools.user_id)
        if not progress.sessions:
            gathered.notes.append(
                "The learner has no completed practice sessions yet, so there is no progress to analyse. Say so and offer to start one (e.g. an IELTS-style speaking practice)."
            )
            return
        lines = [
            f"Facts from the learner's last {len(progress.sessions)} completed sessions (newest first; use only these numbers; all bands are simulator estimates):"
        ]
        for s in progress.sessions:
            band = (
                f"band {s.band_low:g}–{s.band_high:g}"
                if s.band_low is not None and s.band_high is not None
                else "no band"
            )
            scores = ", ".join(
                f"{n} {v:g}"
                for n, v in (
                    ("fluency", s.fluency_score),
                    ("vocabulary", s.lexical_score),
                    ("grammar", s.grammar_score),
                )
                if v is not None
            )
            lines.append(
                f"- {s.started_at:%Y-%m-%d} {s.mode}: {band}"
                + (f" ({scores})" if scores else "")
                + f", {s.user_words} words"
            )
        for name, (older, newer) in progress.criteria_trend.items():
            direction = (
                "improved" if newer > older else "declined" if newer < older else "unchanged"
            )
            lines.append(
                f"Trend {name.replace('_', ' ')}: {older:g} → {newer:g} ({direction}; older half vs newer half of sessions)"
            )
        if progress.recurring:
            lines.append(
                "Most frequent mistake types: "
                + "; ".join(
                    f"{r.category.replace('_', ' ')} ×{r.count} in {r.sessions} session(s), e.g. {r.example}"
                    for r in progress.recurring
                )
            )
        if progress.speaking_minutes:
            lines.append(f"Measured speaking time: {progress.speaking_minutes:g} minutes.")
        for goal in progress.goals:
            lines.append(f"Active goal: {goal.description}")
        if len(progress.sessions) < 3:
            lines.append("Only a few sessions exist, so trends are not reliable yet — say so.")
        gathered.notes.append("\n".join(lines))
