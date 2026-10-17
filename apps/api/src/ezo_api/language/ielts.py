"""IELTS-style speaking structure: three parts, an original question bank and band maths.

This is a *simulator*. The questions below were written for EZO (they are not taken from
any published test), and every band EZO gives is an *estimate*, never an official score.

Structure (as publicly described for the IELTS Speaking test):
- Part 1: questions about familiar topics;
- Part 2: a long turn on a cue card (about one minute to prepare, up to two minutes to speak);
- Part 3: a discussion of more abstract questions related to Part 2.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

PART1_QUESTIONS_PER_TEST = 5
PART3_QUESTIONS_PER_TEST = 4

PART1_TOPICS: dict[str, list[str]] = {
    "hometown": [
        "Where are you from, and what is your hometown known for?",
        "What do you like most about the place where you grew up?",
        "Has your hometown changed much in recent years?",
    ],
    "work_study": [
        "Do you work or are you a student at the moment?",
        "What do you enjoy most about your work or studies?",
        "Is there anything you would like to change about your daily routine?",
    ],
    "free_time": [
        "What do you usually do in your free time?",
        "Do you prefer spending free time alone or with other people? Why?",
        "Is there a hobby you would like to try in the future?",
    ],
    "food": [
        "What kind of food do you enjoy eating most?",
        "Do you often cook at home?",
        "Is there a dish from your country that you would recommend to visitors?",
    ],
    "technology": [
        "How often do you use your phone during the day?",
        "Which app do you find most useful, and why?",
        "Do you think you spend too much time online?",
    ],
    "weather": [
        "What is the weather usually like where you live?",
        "Which season do you like best, and why?",
        "Does the weather affect your mood?",
    ],
}


@dataclass(frozen=True, slots=True)
class CueCard:
    id: str
    task: str
    points: tuple[str, ...]
    follow_up: str
    discussion: tuple[str, ...]


CUE_CARDS: tuple[CueCard, ...] = (
    CueCard(
        "skill",
        "Describe a skill you learned that you are proud of.",
        (
            "what the skill is",
            "how and when you learned it",
            "who helped you",
            "and explain why you are proud of it",
        ),
        "Do you still use this skill today?",
        (
            "Which skills do you think young people should learn at school?",
            "Is it better to learn a skill from a teacher or by yourself? Why?",
            "How has technology changed the way people learn new skills?",
            "Do you think some skills will become less important in the future?",
        ),
    ),
    CueCard(
        "place",
        "Describe a place in your city where you like to spend time.",
        (
            "where it is",
            "what it looks like",
            "how often you go there",
            "and explain why you like spending time there",
        ),
        "Would you recommend this place to a visitor?",
        (
            "Why do people need public spaces such as parks in cities?",
            "How have cities in your country changed in the last twenty years?",
            "Should governments spend more money on public spaces or on transport?",
            "What will cities look like in fifty years?",
        ),
    ),
    CueCard(
        "person",
        "Describe a person who has had a positive influence on you.",
        (
            "who this person is",
            "how you know them",
            "what they have done",
            "and explain how they have influenced you",
        ),
        "Have you told this person how you feel?",
        (
            "What qualities make someone a good role model?",
            "Do famous people have a responsibility to set a good example?",
            "Are role models more important for children or for adults?",
            "How has social media changed who young people admire?",
        ),
    ),
    CueCard(
        "decision",
        "Describe an important decision you made.",
        (
            "what the decision was",
            "when you made it",
            "what you had to consider",
            "and explain why it was important",
        ),
        "Was it difficult to make this decision?",
        (
            "Do people make better decisions alone or with advice from others?",
            "What important decisions do young people in your country have to make?",
            "Should parents make decisions for their teenage children?",
            "Why do some people find it hard to make decisions?",
        ),
    ),
)


@dataclass(slots=True)
class IeltsState:
    """Where a session is in the test. Stored in LanguageSession.meta["ielts"]."""

    part: int = 1
    answered: dict[str, int] = field(default_factory=lambda: {"1": 0, "2": 0, "3": 0})
    part1: list[str] = field(default_factory=list)
    cue_card: str = ""
    finished: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "part": self.part,
            "answered": dict(self.answered),
            "part1": list(self.part1),
            "cue_card": self.cue_card,
            "finished": self.finished,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> IeltsState:
        if not data:
            return cls()
        return cls(
            part=int(data.get("part", 1)),
            answered={k: int(v) for k, v in (data.get("answered") or {}).items()},
            part1=list(data.get("part1") or []),
            cue_card=str(data.get("cue_card") or ""),
            finished=bool(data.get("finished")),
        )


def new_test(seed: str) -> IeltsState:
    """Pick Part 1 questions and a cue card (deterministic per session)."""
    rng = random.Random(seed)  # noqa: S311 - question choice, not security
    topics = rng.sample(sorted(PART1_TOPICS), 2)
    questions = PART1_TOPICS[topics[0]] + PART1_TOPICS[topics[1]][:2]
    card = rng.choice(CUE_CARDS)
    return IeltsState(part1=questions[:PART1_QUESTIONS_PER_TEST], cue_card=card.id)


def cue_card(card_id: str) -> CueCard:
    return next((c for c in CUE_CARDS if c.id == card_id), CUE_CARDS[0])


def format_cue_card(card: CueCard) -> str:
    points = "\n".join(f"- {p}" for p in card.points)
    return f"{card.task}\nYou should say:\n{points}"


@dataclass(frozen=True, slots=True)
class NextStep:
    part: int
    instruction: str
    finished: bool = False


def advance(state: IeltsState, learner_answered: bool) -> NextStep:
    """Record a learner answer (if any) and say what the examiner does next."""
    key = str(state.part)
    if learner_answered and not state.finished:
        state.answered[key] = state.answered.get(key, 0) + 1
    done = state.answered.get(key, 0)
    if state.part == 1:
        if done < len(state.part1):
            intro = (
                "Start Part 1: greet the candidate briefly, say this is an IELTS-style practice "
                "(not an official test), then ask: "
                if done == 0
                else "Ask the next Part 1 question: "
            )
            return NextStep(1, intro + f"“{state.part1[done]}”")
        state.part = 2
        card = cue_card(state.cue_card)
        return NextStep(
            2,
            "Move to Part 2. Say: “Now I'm going to give you a topic. You have one minute to "
            "prepare, then please talk for one to two minutes.” Then give this task card "
            f"exactly:\n{format_cue_card(card)}",
        )
    if state.part == 2:
        if done < 1:
            return NextStep(2, "Wait for the candidate's long turn; do not interrupt.")
        if done == 1:
            return NextStep(
                2, f"Ask one short rounding-off question: “{cue_card(state.cue_card).follow_up}”"
            )
        state.part = 3
        return NextStep(
            3,
            "Move to Part 3: say you will now discuss some more general questions related to "
            f"the topic, then ask: “{cue_card(state.cue_card).discussion[0]}”",
        )
    discussion = cue_card(state.cue_card).discussion
    if done < PART3_QUESTIONS_PER_TEST and done < len(discussion):
        return NextStep(3, f"Ask the next Part 3 question: “{discussion[done]}”")
    state.finished = True
    return NextStep(
        3,
        "The test is complete. Thank the candidate in one sentence; the feedback follows.",
        finished=True,
    )


# --- band maths ----------------------------------------------------------------------------


def round_band(value: float) -> float:
    """Round to the nearest half band, clamped to 0–9 (halves round up)."""
    value = max(0.0, min(9.0, value))
    return math.floor(value * 2 + 0.5) / 2


def band_range(criteria: list[float], learner_words: int) -> tuple[float, float]:
    """An honest range around the mean of the assessed criteria.

    The range covers the half-band rounding of the mean; with little speech (less
    evidence) it is widened by half a band on each side.
    """
    if not criteria:
        raise ValueError("no criteria to combine")
    mean = sum(criteria) / len(criteria)
    margin = 0.5 if learner_words < 150 else 0.0
    low = math.floor((mean - margin) * 2 + 1e-9) / 2
    high = math.ceil((mean + margin) * 2 - 1e-9) / 2
    return max(0.0, low), min(9.0, high)
