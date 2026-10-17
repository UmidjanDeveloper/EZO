"""Decide deterministically whether a request is one agent's job or a multi-agent mission.

No model call: the factors are counted from the text, so routing is cheap, fast
and testable. A mission needs several *independent* specialist roles or several
deliverables — "PDFni qisqartir" stays a single DocumentAgent turn.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ezo_api.core.text import normalize
from ezo_api.orchestration.models import MAX_STEPS, AgentType, MissionPlan, StepSpec

_ROLE_SIGNALS: dict[AgentType, re.Pattern[str]] = {
    "research": re.compile(
        r"\b(bozor\w*|raqobatchi|competitor|o'rgan|tadqiq|izla|top\b|topib|research|market|"
        r"исследу|конкурент|рын\w*|найди)"
    ),
    "business": re.compile(
        r"\b(biznes ?(model|reja)|business (model|plan)|moliya|financial|unit economics|"
        r"бизнес-?(модел|план)|финанс)"
    ),
    "document": re.compile(r"\b(hisobot|report|hujjat|document|отч[её]т|документ)"),
    "presentation": re.compile(r"\b(taqdimot|pitch ?deck|presentation|slayd|slide|презентац)"),
    "visual": re.compile(r"\b(logo|logotip|brend|brand|rasm|image|dizayn|логотип|бренд)"),
    "developer": re.compile(
        r"\b(website|veb-?sayt|sayt|repo(?:sitor\w*|'?ni|'?si|'?da)?|kod|code|"
        r"bug(?:s|lar\w*|ni|i)?|test qil|deploy|frontend|backend|сайт|баг|код|репозитор\w*)\b"
    ),
    "legal_research": re.compile(r"\b(qaror|farmon|qonun|decree|law|постановлени|указ|закон)"),
}
# A whole-venture request implies the usual team even when no role is named.
_BUNDLES: tuple[tuple[re.Pattern[str], tuple[AgentType, ...]], ...] = (
    (
        re.compile(r"\b(startap\w*|startup\w*|стартап\w*)"),
        ("research", "business", "document", "visual", "presentation"),
    ),
)
# Independent areas of one codebase that can be reviewed in parallel.
_DEV_AREAS: dict[str, re.Pattern[str]] = {
    "frontend": re.compile(r"\bfrontend|\bui\b|фронтенд"),
    "backend": re.compile(r"\bbackend|\bapi\b|бэкенд"),
    "security": re.compile(r"\bsecurity|xavfsizlik|безопасност"),
    "tests": re.compile(r"\btest(s|lar)?\b|тест"),
    "database": re.compile(r"\bdatabase|ma'lumotlar bazasi|баз[аы] данных"),
}
_SCOPE = re.compile(
    r"\b(boshidan oxirigacha|to'liq|full|end[- ]to[- ]end|from scratch|hammasini|"
    r"полностью|под ключ|parallel)"
)
_SEQUENCE = re.compile(r"\b(keyin|so'ng|va|then|and|затем|потом|и)\b")
_APPROVAL = re.compile(
    r"\b(push|deploy|publish|e-?mail yubor|send email|o'chir|delete|pul|to'lov|pay|"
    r"опубликуй|удали|отправь)"
)
MISSION_THRESHOLD = 3.0


@dataclass(frozen=True, slots=True)
class Complexity:
    score: float
    roles: tuple[AgentType, ...]
    needs_approval: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)
    dev_areas: tuple[str, ...] = ()

    @property
    def is_mission(self) -> bool:
        independent = len(self.roles) >= 2 or len(self.dev_areas) >= 2
        return independent and self.score >= MISSION_THRESHOLD


def assess(text: str) -> Complexity:
    norm = normalize(text)
    found = {role for role, pattern in _ROLE_SIGNALS.items() if pattern.search(norm)}
    for pattern, bundle in _BUNDLES:
        if pattern.search(norm):
            found.update(bundle)
    roles = tuple(role for role in _ROLE_SIGNALS if role in found)
    areas = (
        tuple(a for a, p in _DEV_AREAS.items() if p.search(norm)) if "developer" in roles else ()
    )
    reasons = [f"{len(roles)} specialist role(s)"]
    score = float(len(roles))
    if len(areas) >= 2:
        score += 0.5 * len(areas)
        reasons.append(f"{len(areas)} independent code areas")
    if _SCOPE.search(norm):
        score += 1.5
        reasons.append("whole-project scope")
    joins = len(_SEQUENCE.findall(norm))
    if joins >= 2:
        score += 0.5
        reasons.append("several chained tasks")
    count = re.search(r"\b(\d{2,3})\s*ta\b|\b(\d{2,3})\s+(competitors|companies)", norm)
    if count:
        score += 0.5
        reasons.append("many items to cover")
    approval = bool(_APPROVAL.search(norm))
    if approval:
        reasons.append("contains actions that need approval")
    return Complexity(round(score, 2), roles, approval, tuple(reasons), areas)


_ORDER: tuple[AgentType, ...] = (
    "research",
    "legal_research",
    "business",
    "document",
    "visual",
    "presentation",
    "developer",
)
_TITLES: dict[AgentType, str] = {
    "research": "Research the topic and sources",
    "legal_research": "Find and check the official documents",
    "business": "Business model and assumptions",
    "document": "Write the report",
    "visual": "Visual direction",
    "presentation": "Build the presentation",
    "developer": "Build and test the code",
    "qa": "Final quality check",
}


def draft_plan(text: str, complexity: Complexity | None = None) -> MissionPlan:
    """A deterministic plan: research first, producers in parallel after it, QA last.

    Dependencies follow the data: everything waits for research; the presentation
    also waits for the business model and the report when they exist, so it can use
    their structured output. Repository changes always need the user's approval.
    """
    complexity = complexity or assess(text)
    roles = [r for r in _ORDER if r in complexity.roles] or ["research", "document"]
    steps: list[StepSpec] = []
    first = [r for r in roles if r in ("research", "legal_research")]
    for role in roles:
        depends: list[str] = [] if role in first else list(first)
        if role == "developer" and len(complexity.dev_areas) >= 2:
            # Parallel read-only reviews, then one approved change set built on all of them.
            for area in complexity.dev_areas:
                steps.append(
                    StepSpec(
                        id=f"review_{area}",
                        title=f"Review: {area}",
                        agent_type="developer",
                        depends_on=list(depends),
                    )
                )
            depends = [f"review_{a}" for a in complexity.dev_areas]
        if role == "presentation":
            depends += [r for r in ("business", "document") if r in roles]
        steps.append(
            StepSpec(
                id=role,
                title=_TITLES[role],
                agent_type=role,
                depends_on=depends,
                requires_approval=role == "developer",
                approval_reason=(
                    "Code changes will be written to an isolated branch; nothing is pushed "
                    "or deployed without your approval."
                    if role == "developer"
                    else ""
                ),
            )
        )
    steps.append(
        StepSpec(
            id="qa",
            title=_TITLES["qa"],
            agent_type="qa",
            depends_on=[s.id for s in steps],
        )
    )
    title = " ".join(text.split())[:80] or "Mission"
    return MissionPlan(title=title, goal=text[:4_000] or title, steps=steps[:MAX_STEPS])
