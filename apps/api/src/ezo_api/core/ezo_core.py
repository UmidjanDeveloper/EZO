"""EzoCore: the turn pipeline behind every conversation.

    prepare  -> detect language, classify intent, select agent,
                persist the user message and open an AgentRun
    execute  -> load context, retrieve memory, plan, compose the prompt,
                stream from the routed model (with fallback), verify quality,
                persist the reply, capture memories, close the AgentRun

Every step is recorded in the AgentRun trace (names, timings, summaries —
never hidden model reasoning).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.academic.requests import citation_request, wants_research_plan
from ezo_api.agents.base import AgentPlan, AgentTurn, GatherContext, Gathered
from ezo_api.agents.learning import wants_learning
from ezo_api.agents.references import latest_artifact
from ezo_api.agents.registry import AgentRegistry, AgentSelection
from ezo_api.agents.student_adapter import STUDENT_SPEC, StudentAdapterAgent, wants_student
from ezo_api.core import messages
from ezo_api.core.intent import Intent, IntentResult, classify_intent
from ezo_api.core.language import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    Language,
    detect_language,
)
from ezo_api.core.text import normalize
from ezo_api.core.trace import Tracer
from ezo_api.db.base import utcnow
from ezo_api.db.models import (
    AgentRun,
    Conversation,
    KnowledgeDocument,
    KnowledgeLibrary,
    Message,
    Project,
    User,
)
from ezo_api.db.models.artifacts import ARTIFACT_TYPES
from ezo_api.documents.pdf.requests import parse_pdf_request
from ezo_api.education.catalog import wants_education
from ezo_api.knowledge.retrieval.citations import (
    CITATION_RULES,
    format_sources_for_prompt,
    verify_citations,
)
from ezo_api.knowledge.retrieval.sources import number_sources
from ezo_api.language.service import active_session as active_language_session
from ezo_api.memory.service import MemoryIndex, MemoryService, RetrievedMemory
from ezo_api.personality.profile import HumorLevel, PersonalityProfile
from ezo_api.personality.prompt import PromptContext, PromptMemory, build_system_prompt
from ezo_api.providers.router import (
    AllProvidersFailedError,
    ModelRouter,
    RoutedStream,
    RoutingConfigError,
    StreamInterruptedError,
)
from ezo_api.providers.types import ChatMessage, ChatRequest, StreamEnd, TextDelta, Usage
from ezo_api.tools.base import ToolContext
from ezo_api.translation.requests import wants_translation
from ezo_api.visual.kinds import wants_edit as wants_visual_edit
from ezo_api.writing.catalog import wants_writing

if TYPE_CHECKING:
    from ezo_api.services import Services

# Agents whose answers come from retrieval: in a library-scoped conversation they answer
# only from that library's sources.
LIBRARY_ANSWER_AGENTS = frozenset({"general", "research", "knowledge_os"})

logger = logging.getLogger(__name__)

TITLE_MAX_CHARS = 60
TRUNCATION_REASONS = {"max_tokens", "length", "MAX_TOKENS"}


class TurnError(Exception):
    """A request problem detected before streaming starts (maps to 4xx)."""

    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class TurnInput:
    text: str
    conversation_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    library_id: uuid.UUID | None = None
    clear_library: bool = False
    forced_agent: str | None = None
    channel: Literal["text", "voice"] = "text"
    speech_seconds: float | None = None
    attachments: tuple[uuid.UUID, ...] = ()
    # Language the speech recogniser heard; used when the words themselves are ambiguous.
    language_hint: Language | None = None


@dataclass(slots=True)
class PreparedTurn:
    user: User
    conversation: Conversation
    project: Project | None
    user_message: Message
    run: AgentRun
    language: str
    language_is_fixed: bool
    intent: IntentResult
    selection: AgentSelection
    tracer: Tracer
    created_conversation: bool
    channel: Literal["text", "voice"] = "text"
    speech_seconds: float | None = None
    attachments: tuple[uuid.UUID, ...] = ()
    library: KnowledgeLibrary | None = None


@dataclass(frozen=True, slots=True)
class CoreMeta:
    conversation_id: uuid.UUID
    conversation_title: str
    created_conversation: bool
    user_message_id: uuid.UUID
    run_id: uuid.UUID
    intent: str
    intent_confidence: float
    agent: str
    requested_agent: str
    requested_agent_available: bool
    language: str
    library_id: uuid.UUID | None = None
    library_name: str | None = None
    type: Literal["meta"] = "meta"


@dataclass(frozen=True, slots=True)
class CoreActivity:
    """What EZO is visibly doing before it answers: searching, reading, working…"""

    stage: str
    type: Literal["activity"] = "activity"


@dataclass(frozen=True, slots=True)
class CoreDelta:
    text: str
    type: Literal["delta"] = "delta"


@dataclass(frozen=True, slots=True)
class CoreDone:
    message: Message
    run: AgentRun
    type: Literal["done"] = "done"


@dataclass(frozen=True, slots=True)
class CoreError:
    code: str
    message: str
    hint: str
    run_id: uuid.UUID
    attempts: list[dict[str, Any]] = field(default_factory=list)
    type: Literal["error"] = "error"


CoreEvent = CoreMeta | CoreActivity | CoreDelta | CoreDone | CoreError


def make_title(text: str) -> str:
    title = " ".join(text.split())
    if len(title) <= TITLE_MAX_CHARS:
        return title
    cut = title[:TITLE_MAX_CHARS].rsplit(" ", 1)[0]
    return (cut or title[:TITLE_MAX_CHARS]) + "…"


async def _owned_attachments(
    session: AsyncSession, user_id: uuid.UUID, ids: tuple[uuid.UUID, ...]
) -> tuple[tuple[uuid.UUID, ...], list[str]]:
    """The attached files (in the given order) and their names; another user's (or an
    unknown) file is an error."""
    if not ids:
        return (), []
    rows = (
        await session.execute(
            select(KnowledgeDocument.id, KnowledgeDocument.filename, KnowledgeDocument.title).where(
                KnowledgeDocument.id.in_(ids), KnowledgeDocument.user_id == user_id
            )
        )
    ).all()
    names = {row.id: row.filename or row.title for row in rows}
    if any(i not in names for i in ids):
        raise TurnError(404, "attachment_not_found", "An attached file was not found.")
    return ids, [names[i] for i in ids]


async def _latest_artifact_is_image(
    session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> bool:
    latest = await latest_artifact(session, user_id, conversation_id, ARTIFACT_TYPES)
    return latest is not None and latest.artifact_type == "image"


class EzoCore:
    def __init__(
        self,
        router: ModelRouter,
        agents: AgentRegistry,
        personality: PersonalityProfile,
        timezone: str,
        context_message_limit: int,
        context_char_budget: int,
        max_output_tokens: int,
    ) -> None:
        self.router = router
        self.agents = agents
        self.personality = personality
        self.tz = ZoneInfo(timezone)
        self.context_message_limit = context_message_limit
        self.context_char_budget = context_char_budget
        self.max_output_tokens = max_output_tokens
        # Set by build_services once all services exist (tools need them).
        self.services: Services | None = None
        self.memory_index: MemoryIndex | None = None

    # ------------------------------------------------------------------ prepare

    async def prepare(self, session: AsyncSession, user: User, turn: TurnInput) -> PreparedTurn:
        tracer = Tracer()
        conversation, project, library, created = await self._load_conversation(session, user, turn)

        preferences = user.preferences or {}
        fixed = preferences.get("response_language")
        with tracer.step("detect_language") as step:
            if fixed in SUPPORTED_LANGUAGES:
                language, language_is_fixed = str(fixed), True
                step.summary = f"{language} (user preference)"
            else:
                fallback = turn.language_hint or DEFAULT_LANGUAGE
                language, language_is_fixed = detect_language(turn.text, fallback), False
                step.summary = language

        with tracer.step("classify_intent") as step:
            intent = classify_intent(turn.text)
            if (
                intent.intent == Intent.GENERAL
                and turn.forced_agent is None
                and await active_language_session(session, user.id, conversation.id) is not None
            ):
                # An ongoing practice session keeps the coach: learner answers are ordinary
                # sentences that would otherwise look like general chat.
                intent = IntentResult(
                    Intent.LANGUAGE_COACH, 1.0, ("active_language_session",), intent.scores
                )
            elif (
                turn.forced_agent is None
                and not turn.attachments
                and wants_learning(turn.text, intent.intent)
            ):
                # "Shu website'ni o'rgan: https://…", "github:owner/repo ni o'rgan",
                # "O'rgangan manbalaringni ko'rsat": the Knowledge OS reads the source.
                intent = IntentResult(Intent.LEARNING, 1.0, ("learning",), intent.scores)
            elif (
                intent.intent == Intent.GENERAL
                and turn.forced_agent is None
                and wants_visual_edit(turn.text)
                and await _latest_artifact_is_image(session, user.id, conversation.id)
            ):
                # "Fonini ko'k qil" right after an image: a change to that image.
                intent = IntentResult(Intent.VISUAL, 1.0, ("image_follow_up",), intent.scores)
            elif (
                intent.intent
                in (
                    Intent.GENERAL,
                    Intent.LANGUAGE_COACH,
                    Intent.LEGAL_RESEARCH,
                    Intent.RESEARCH,
                    Intent.BUSINESS,
                )
                and turn.forced_agent is None
                and wants_translation(turn.text)
                and await active_language_session(session, user.id, conversation.id) is None
            ):
                # "Inglizchaga tarjima qil: …", "Kirillga o'gir", "Glossariyga qo'sh: …":
                # translation work, whatever the text is about (not language practice;
                # presentations and images keep their own agents).
                intent = IntentResult(Intent.DOCUMENT, 1.0, ("translation",), intent.scores)
            elif (
                turn.forced_agent is None
                and (wants_research_plan(turn.text) or citation_request(turn.text) is not None)
                and intent.intent
                in (Intent.GENERAL, Intent.RESEARCH, Intent.LANGUAGE_COACH, Intent.BUSINESS)
                and await active_language_session(session, user.id, conversation.id) is None
            ):
                # "Ilmiy manbalarni top, tadqiqot rejasini tuz", "APA formatiga o'tkaz":
                # literature, plan and reference list as files.
                intent = IntentResult(Intent.DOCUMENT, 1.0, ("academic",), intent.scores)
            elif (
                turn.forced_agent is None
                and (education := wants_education(turn.text)) is not None
                and (
                    intent.intent
                    in (Intent.GENERAL, Intent.LANGUAGE_COACH, Intent.RESEARCH, Intent.BUSINESS)
                    or (intent.intent == Intent.PRESENTATION and education.key == "lesson")
                )
                and await active_language_session(session, user.id, conversation.id) is None
            ):
                # "Test tuz", "dars ishlanmasi (taqdimoti bilan)", "o'qish rejasi":
                # teaching materials (Word + Excel, slides for lessons).
                intent = IntentResult(Intent.DOCUMENT, 1.0, ("education",), intent.scores)
            elif (
                intent.intent == Intent.GENERAL
                and turn.forced_agent is None
                and wants_writing(normalize(turn.text)) is not None
            ):
                # "Tushuntirish xati yoz", "CV tayyorla": a document to draft.
                intent = IntentResult(Intent.DOCUMENT, 1.0, ("writing",), intent.scores)
            elif (
                intent.intent == Intent.GENERAL
                and turn.forced_agent is None
                and (turn.attachments or parse_pdf_request(turn.text))
            ):
                # Files attached to the message (or a recognised PDF operation such as
                # "2-betni o'chir"): the request is about documents.
                intent = IntentResult(Intent.DOCUMENT, 1.0, ("attached_files",), intent.scores)
            elif (
                turn.forced_agent is None
                and wants_student(turn.text)
                and await active_language_session(session, user.id, conversation.id) is None
            ):
                intent = IntentResult(Intent.GENERAL, 1.0, ("student",), intent.scores)
            step.summary = f"{intent.intent.value} ({intent.confidence:.2f})" + (
                f" signals={list(intent.signals)}" if intent.signals else ""
            )

        with tracer.step("select_agent") as step:
            if self.services and self.services.settings.deployment_profile == "free-beta":
                selection = self.agents.select(Intent.GENERAL, "general")
            elif turn.forced_agent == "student" or (
                turn.forced_agent is None
                and wants_student(turn.text)
                and await active_language_session(session, user.id, conversation.id) is None
            ):
                selection = AgentSelection(agent=StudentAdapterAgent(), requested=STUDENT_SPEC)
            else:
                selection = self.agents.select(intent.intent, turn.forced_agent)
            step.summary = selection.agent.spec.key + (
                f" covering unavailable {selection.requested.key}" if selection.is_fallback else ""
            )

        attachments, attachment_names = await _owned_attachments(session, user.id, turn.attachments)
        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            content=turn.text,
            language=language,
            meta={"channel": turn.channel}
            | (
                {
                    "attachments": [str(a) for a in attachments],
                    "attachment_names": attachment_names,
                }
                if attachments
                else {}
            ),
        )
        run = AgentRun(
            user_id=user.id,
            conversation_id=conversation.id,
            status="running",
            intent=intent.intent.value,
            intent_confidence=intent.confidence,
            agent=selection.agent.spec.key,
            language=language,
            steps=[],
            attempts=[],
            tool_calls=[],
        )
        conversation.updated_at = utcnow()
        session.add_all([user_message, run])
        await session.commit()

        return PreparedTurn(
            user=user,
            conversation=conversation,
            project=project,
            user_message=user_message,
            run=run,
            language=language,
            language_is_fixed=language_is_fixed,
            intent=intent,
            selection=selection,
            tracer=tracer,
            created_conversation=created,
            channel=turn.channel,
            speech_seconds=turn.speech_seconds,
            attachments=attachments,
            library=library,
        )

    async def _load_conversation(
        self, session: AsyncSession, user: User, turn: TurnInput
    ) -> tuple[Conversation, Project | None, KnowledgeLibrary | None, bool]:
        library: KnowledgeLibrary | None = None

        if turn.conversation_id is not None:
            conversation = await session.get(Conversation, turn.conversation_id)
            if conversation is None or conversation.user_id != user.id:
                raise TurnError(404, "conversation_not_found", "Conversation not found.")
            project = (
                await session.get(Project, conversation.project_id)
                if conversation.project_id
                else None
            )
            if turn.clear_library:
                conversation.library_id = None
            elif turn.library_id is not None:
                lib_check = await session.get(KnowledgeLibrary, turn.library_id)
                if lib_check is None:
                    raise TurnError(404, "library_not_found", "Knowledge library not found.")
                if lib_check.user_id != user.id:
                    raise TurnError(404, "library_not_found", "Knowledge library not found.")
                conversation.library_id = turn.library_id
            created = False
        else:
            project = None
            if turn.project_id is not None:
                project = await session.get(Project, turn.project_id)
                if project is None or project.user_id != user.id:
                    raise TurnError(404, "project_not_found", "Project not found.")
            target_lib_id = turn.library_id if not turn.clear_library else None
            if target_lib_id is not None:
                lib_check = await session.get(KnowledgeLibrary, target_lib_id)
                if lib_check is None:
                    raise TurnError(404, "library_not_found", "Knowledge library not found.")
                if lib_check.user_id != user.id:
                    raise TurnError(404, "library_not_found", "Knowledge library not found.")
            conversation = Conversation(
                user_id=user.id,
                project_id=project.id if project else None,
                library_id=target_lib_id,
                title=make_title(turn.text),
            )
            session.add(conversation)
            await session.flush()
            created = True

        if conversation.library_id is not None:
            library = await session.get(KnowledgeLibrary, conversation.library_id)
            if library is None:
                raise TurnError(404, "library_not_found", "Knowledge library not found.")
            if library.user_id != user.id:
                raise TurnError(404, "library_not_found", "Knowledge library not found.")

        return conversation, project, library, created

    # ------------------------------------------------------------------ execute

    async def execute(
        self, session: AsyncSession, prepared: PreparedTurn
    ) -> AsyncIterator[CoreEvent]:
        selection = prepared.selection
        yield CoreMeta(
            conversation_id=prepared.conversation.id,
            conversation_title=prepared.conversation.title,
            created_conversation=prepared.created_conversation,
            user_message_id=prepared.user_message.id,
            run_id=prepared.run.id,
            intent=prepared.intent.intent.value,
            intent_confidence=prepared.intent.confidence,
            agent=selection.agent.spec.key,
            requested_agent=selection.requested.key,
            requested_agent_available=selection.requested.available,
            language=prepared.language,
            library_id=prepared.library.id if prepared.library else None,
            library_name=prepared.library.name if prepared.library else None,
        )

        tracer = prepared.tracer
        routed: RoutedStream | None = None
        try:
            history = await self._load_history(session, prepared)
            memories = await self._retrieve_memories(session, prepared)
            plan = self._plan(prepared)
            gathered = Gathered()
            async for item in self._gather_with_activity(session, prepared, history):
                if isinstance(item, CoreActivity):
                    yield item
                else:
                    gathered = item
            system_prompt = self._compose_prompt(prepared, plan, memories, gathered)

            with tracer.step("route_model") as step:
                routed = self.router.open(plan.route)
                step.summary = f"route={plan.route} candidates=" + ",".join(
                    f"{c.provider.name}/{c.model}" for c in routed.candidates
                )
            prepared.run.route = plan.route

            request = ChatRequest(
                model="",  # filled per candidate by the router
                messages=history,
                system=system_prompt,
                max_output_tokens=self.max_output_tokens,
                hints={"language": prepared.language, "agent": selection.agent.spec.key},
            )
            parts: list[str] = []
            end: StreamEnd | None = None
            with tracer.step("generate") as step:
                async for event in routed.stream(request):
                    if isinstance(event, TextDelta):
                        parts.append(event.text)
                        yield CoreDelta(event.text)
                    else:
                        end = event
                selected = routed.selected
                step.summary = (
                    f"{selected.provider.name}/{end.model if end else selected.model}"
                    if selected
                    else ""
                )

            reply, quality = self._verify(prepared, "".join(parts), end)
            if quality.get("appended"):
                yield CoreDelta(str(quality["appended"]))

            with tracer.step("verify_citations") as step:
                check = verify_citations(reply, gathered.sources)
                reply = check.text
                quality["citations"] = len(check.cited)
                if check.invalid_numbers:
                    quality["invalid_citations_removed"] = check.invalid_numbers
                step.summary = (
                    f"sources={len(gathered.sources)} cited={len(check.cited)} "
                    f"removed={check.invalid_numbers}"
                )
            quality["citation_sources"] = [source.to_metadata() for source in check.cited]

            message = await self._finish_success(
                session, prepared, routed, end, reply, quality, memories, gathered
            )
            yield CoreDone(message=message, run=prepared.run)
        except (AllProvidersFailedError, StreamInterruptedError, RoutingConfigError) as exc:
            yield await self._finish_failure(session, prepared, routed, exc)
        except BaseException as exc:
            # Includes client disconnects (cancellation): record the failure in the
            # trace, shielded from the cancellation, then let the exception propagate.
            with anyio.CancelScope(shield=True):
                await self._record_abort(session, prepared, routed, exc)
            raise

    async def _load_history(
        self, session: AsyncSession, prepared: PreparedTurn
    ) -> list[ChatMessage]:
        with prepared.tracer.step("load_context") as step:
            rows = (
                await session.scalars(
                    select(Message)
                    .where(Message.conversation_id == prepared.conversation.id)
                    .order_by(Message.created_at.desc())
                    .limit(self.context_message_limit)
                )
            ).all()
            history: list[ChatMessage] = []
            used = 0
            for row in rows:  # newest first
                if row.role not in ("user", "assistant"):
                    continue
                if history and used + len(row.content) > self.context_char_budget:
                    break
                used += len(row.content)
                history.append(ChatMessage(row.role, row.content))  # type: ignore[arg-type]
            history.reverse()
            step.summary = f"{len(history)} messages, {used} chars"
            return history

    async def _retrieve_memories(
        self, session: AsyncSession, prepared: PreparedTurn
    ) -> list[RetrievedMemory]:
        with prepared.tracer.step("retrieve_memory") as step:
            retrieved = await MemoryService(session, self.memory_index).retrieve(
                prepared.user.id,
                prepared.user_message.content,
                prepared.conversation.project_id,
            )
            step.summary = f"{len(retrieved)} memories"
            return retrieved

    async def _gather_with_activity(
        self, session: AsyncSession, prepared: PreparedTurn, history: list[ChatMessage]
    ) -> AsyncIterator[CoreActivity | Gathered]:
        """Run the gather step and stream the visible stage of each tool as it starts."""
        stages: asyncio.Queue[str] = asyncio.Queue()
        task = asyncio.create_task(self._gather(session, prepared, history, stages.put_nowait))
        last = ""
        try:
            while True:
                getter = asyncio.ensure_future(stages.get())
                done, _ = await asyncio.wait({task, getter}, return_when=asyncio.FIRST_COMPLETED)
                if getter not in done:
                    getter.cancel()
                    break
                stage = getter.result()
                if stage != last:
                    last = stage
                    yield CoreActivity(stage)
            yield task.result()
        finally:
            if not task.done():  # the client went away mid-gather
                task.cancel()
                with anyio.CancelScope(shield=True):
                    await asyncio.gather(task, return_exceptions=True)

    async def _gather(
        self,
        session: AsyncSession,
        prepared: PreparedTurn,
        history: list[ChatMessage],
        on_activity: Callable[[str], None] | None = None,
    ) -> Gathered:
        """Let the agent collect sources with tools (knowledge base, web)."""
        with prepared.tracer.step("gather") as step:
            if self.services is None:
                step.summary = "tools unavailable"
                return Gathered()
            earlier_user = [m.content for m in history[:-1] if m.role == "user"]
            selection = prepared.selection
            gathered = await selection.agent.gather(
                GatherContext(
                    turn=AgentTurn(
                        text=prepared.user_message.content,
                        language=prepared.language,
                        intent=prepared.intent,
                        requested=selection.requested,
                        channel=prepared.channel,
                        speech_seconds=prepared.speech_seconds,
                        attachments=prepared.attachments,
                    ),
                    tools=ToolContext(
                        session=session,
                        services=self.services,
                        user_id=prepared.user.id,
                        run_id=prepared.run.id,
                        project_scope=prepared.conversation.project_id,
                        library_scope=prepared.conversation.library_id,
                        conversation_id=prepared.conversation.id,
                        on_activity=on_activity,
                    ),
                    history_hint=earlier_user[-1][:500] if earlier_user else "",
                )
            )
            number_sources(gathered.sources)
            step.summary = f"sources={len(gathered.sources)} tools=" + ",".join(
                f"{c['tool']}:{'ok' if c['ok'] else 'failed'}" for c in gathered.tool_calls
            )
            return gathered

    def _plan(self, prepared: PreparedTurn) -> AgentPlan:
        with prepared.tracer.step("plan") as step:
            selection = prepared.selection
            plan = selection.agent.plan(
                AgentTurn(
                    text=prepared.user_message.content,
                    language=prepared.language,
                    intent=prepared.intent,
                    requested=selection.requested,
                    channel=prepared.channel,
                    speech_seconds=prepared.speech_seconds,
                    attachments=prepared.attachments,
                )
            )
            step.summary = f"route={plan.route} mode={plan.context_mode} steps={len(plan.steps)}"
            return plan

    def _compose_prompt(
        self,
        prepared: PreparedTurn,
        plan: AgentPlan,
        memories: list[RetrievedMemory],
        gathered: Gathered,
    ) -> str:
        with prepared.tracer.step("compose_prompt") as step:
            humor_pref = (prepared.user.preferences or {}).get("humor", "default")
            humor: HumorLevel = (
                humor_pref if humor_pref in ("off", "light", "normal") else self.personality.humor
            )
            project = prepared.project
            instructions = plan.instructions
            if prepared.library is not None:
                lib_desc = (
                    f" ({prepared.library.description})" if prepared.library.description else ""
                )
                if prepared.selection.agent.spec.key in LIBRARY_ANSWER_AGENTS:
                    instructions += (
                        f"\n\nSelected Knowledge Library: '{prepared.library.name}'{lib_desc}.\n"
                        "The user has scoped this conversation to this knowledge library only. "
                        "Answer strictly based on the retrieved sources from this library. "
                        "If the retrieved sources do not contain enough information to answer, "
                        "clearly and explicitly state that this knowledge library has no "
                        "relevant info."
                    )
                else:
                    # Translation, writing, practice, slides…: the task decides; the library
                    # is context, and only sources marked as from it may be called so.
                    instructions += (
                        f"\n\nThis conversation is linked to the knowledge library "
                        f"'{prepared.library.name}'. Do the requested task normally; call "
                        "something 'from this library' only when its source says so."
                    )
            prompt = build_system_prompt(
                self.personality,
                PromptContext(
                    mode=plan.context_mode,
                    language=prepared.language,
                    language_is_fixed=prepared.language_is_fixed,
                    humor=humor,
                    now=datetime.now(self.tz),
                    project_name=project.name if project else None,
                    project_description=project.description if project else None,
                    memories=[
                        PromptMemory(m.memory.memory_type, m.memory.category, m.memory.content)
                        for m in memories
                    ],
                    agent_instructions=instructions,
                    sources=(
                        CITATION_RULES + "\n\n" + format_sources_for_prompt(gathered.sources)
                        if gathered.sources
                        else ""
                    ),
                    notes=tuple(gathered.notes),
                    voice=prepared.channel == "voice",
                ),
            )
            step.summary = (
                f"mode={plan.context_mode} channel={prepared.channel} humor={humor} "
                f"chars={len(prompt)}"
            )
            return prompt

    def _verify(
        self, prepared: PreparedTurn, raw_reply: str, end: StreamEnd | None
    ) -> tuple[str, dict[str, Any]]:
        """Quality checks on the final reply (cheap, deterministic)."""
        with prepared.tracer.step("verify") as step:
            reply = raw_reply.strip()
            finish = end.finish_reason if end else None
            quality: dict[str, Any] = {"finish_reason": finish, "truncated": False}
            if not reply:
                reply = messages.text(
                    "refusal" if finish == "refusal" else "empty_reply", prepared.language
                )
                quality["appended"] = reply
                quality["replaced_empty"] = True
            elif finish in TRUNCATION_REASONS:
                notice = "\n\n" + messages.text("truncated", prepared.language)
                reply += notice
                quality["appended"] = notice
                quality["truncated"] = True
            step.summary = (
                ", ".join(f"{k}={v}" for k, v in quality.items() if k != "appended" and v) or "ok"
            )
            return reply, quality

    async def _finish_success(
        self,
        session: AsyncSession,
        prepared: PreparedTurn,
        routed: RoutedStream,
        end: StreamEnd | None,
        reply: str,
        quality: dict[str, Any],
        memories: list[RetrievedMemory],
        gathered: Gathered,
    ) -> Message:
        run = prepared.run
        selected = routed.selected
        usage = end.usage if end else Usage()

        saved_memories = 0
        with prepared.tracer.step("save_memory") as step:
            prefs = prepared.user.preferences or {}
            has_consent = bool(prefs.get("memory_consent", False))
            auto_memory = bool(prefs.get("auto_memory", False))
            if (
                has_consent
                and auto_memory
                and not (self.services and self.services.settings.deployment_profile == "free-beta")
            ):
                capture = await MemoryService(session, self.memory_index).capture_from_message(
                    prepared.user.id,
                    prepared.user_message.content,
                    prepared.conversation.id,
                    prepared.conversation.project_id,
                )
                saved_memories = len(capture.created)
                step.summary = (
                    f"created={len(capture.created)} reinforced={len(capture.reinforced)} "
                    f"skipped_sensitive={capture.skipped_sensitive}"
                )
            elif not has_consent:
                step.summary = "disabled: explicit memory consent required"
            else:
                step.summary = "disabled: auto_memory is turned off in preferences"

        message = Message(
            conversation_id=prepared.conversation.id,
            role="assistant",
            content=reply,
            language=prepared.language,
            agent=prepared.selection.agent.spec.key,
            agent_run_id=run.id,
            meta={
                "provider": selected.provider.name if selected else None,
                "model": end.model if end else (selected.model if selected else None),
                "route": run.route,
                "requested_agent": prepared.selection.requested.key,
                "requested_agent_available": prepared.selection.requested.available,
                "finish_reason": quality.get("finish_reason"),
                "truncated": quality.get("truncated", False),
                "memories_used": [str(m.memory.id) for m in memories],
                "memories_saved": saved_memories,
                "citations": quality.get("citation_sources", []),
                "sources_considered": len(gathered.sources),
                "artifacts": gathered.artifacts,
            },
        )
        session.add(message)

        run.status = "completed"
        run.provider = selected.provider.name if selected else None
        run.model = end.model if end else (selected.model if selected else None)
        run.input_tokens = usage.input_tokens
        run.output_tokens = usage.output_tokens
        run.attempts = [a.as_dict() for a in routed.attempts]
        run.tool_calls = gathered.tool_calls
        run.latency_ms = prepared.tracer.elapsed_ms()
        run.steps = prepared.tracer.as_list()
        run.finished_at = utcnow()
        prepared.conversation.updated_at = utcnow()
        await session.commit()
        return message

    async def _finish_failure(
        self,
        session: AsyncSession,
        prepared: PreparedTurn,
        routed: RoutedStream | None,
        exc: Exception,
    ) -> CoreError:
        language = prepared.language
        if isinstance(exc, AllProvidersFailedError):
            code, message = "all_providers_failed", messages.text("all_providers_failed", language)
            hints = sorted({a.error_kind or "unknown" for a in exc.attempts})
            hint = _provider_hint(hints)
        elif isinstance(exc, StreamInterruptedError):
            code, message = "stream_interrupted", messages.text("stream_interrupted", language)
            hint = exc.error.hint
        else:
            code, message = "config_error", messages.text("config_error", language)
            hint = str(exc)
        logger.warning("Turn failed (%s): %s", code, exc)

        run = prepared.run
        attempts = [a.as_dict() for a in routed.attempts] if routed else []
        run.status = "failed"
        run.error = f"{code}: {exc}"[:2000]
        run.attempts = attempts
        run.latency_ms = prepared.tracer.elapsed_ms()
        run.steps = prepared.tracer.as_list()
        run.finished_at = utcnow()
        await session.commit()
        return CoreError(code=code, message=message, hint=hint, run_id=run.id, attempts=attempts)

    async def _record_abort(
        self,
        session: AsyncSession,
        prepared: PreparedTurn,
        routed: RoutedStream | None,
        exc: BaseException,
    ) -> None:
        try:
            await session.rollback()
            run = await session.get(AgentRun, prepared.run.id)
            if run is None:
                return
            run.status = "failed"
            run.error = f"aborted: {type(exc).__name__}: {exc}"[:2000]
            run.attempts = [a.as_dict() for a in routed.attempts] if routed else []
            run.steps = prepared.tracer.as_list()
            run.latency_ms = prepared.tracer.elapsed_ms()
            run.finished_at = utcnow()
            await session.commit()
        except Exception:
            logger.exception("Could not record aborted run %s", prepared.run.id)
        if not isinstance(exc, Exception):
            logger.info("Turn %s aborted (%s)", prepared.run.id, type(exc).__name__)
        else:
            logger.error("Turn %s crashed", prepared.run.id, exc_info=exc)


def _provider_hint(kinds: list[str]) -> str:
    if "auth" in kinds:
        return "An API key was rejected. Check the keys in your .env file."
    if "model_not_found" in kinds:
        return "A model name is not available. Check apps/api/config/models.toml."
    if "rate_limit" in kinds:
        return "The provider is rate limiting or the account has no credit. Try again later."
    if "unavailable" in kinds or "timeout" in kinds:
        return "Could not reach the provider. Check your internet connection."
    return "See the API logs for details (Settings → Debug shows the attempts)."
