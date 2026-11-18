"""Knowledge OS routing: real Knowledge OS commands are recognised, and requests that
belong to other agents (slides, documents, speaking practice, images, ordinary questions)
are never taken over."""

from __future__ import annotations

import pytest

from ezo_api.agents.learning import wants_learning
from ezo_api.core.intent import classify_intent


def routed(text: str) -> bool:
    return wants_learning(text, classify_intent(text).intent)


@pytest.mark.parametrize(
    "text",
    [
        "Ezo, shu website'ni o'rgan: https://docs.example.org/guide/",
        "Mana bu GitHub repository'ni o'rgan va qanday ishlashini tushuntir: github:psf/requests",
        "Mana bu GitHub repository'ni tahlil qil: https://github.com/psf/requests",
        "pypi:requests ni o'rgan",
        "npm:react kutubxonasini o'rganib chiq",
        "Ezo, mana bu Python kutubxonasining dokumentatsiyasini o'rgan: https://pypi.org/project/httpx/",
        "Learn this website: https://docs.example.org/",
        "Изучи https://docs.example.org/guide/",
        "O'rgangan manbalaringni ko'rsat",
        "«Python kutubxonalari» kutubxonasining imkoniyatlarini tahlil qil",
        "Analyze the capabilities of github:psf/requests",
        # Plain words, as the owner types them (no URL, no "pypi:" prefix).
        "fastapi kutubxonasini o'rgan",
        "fastapi kutibxonani organ",
        "npm axios paketini o'rganib chiq",
        "pallets/flask repozitoriyasini o'rgan",
        "Изучи библиотеку httpx",
        "Please learn the zod library",
    ],
)
def test_knowledge_os_commands(text: str) -> None:
    assert routed(text), text


@pytest.mark.parametrize(
    "text",
    [
        # From the independent review: these went to the Knowledge OS before.
        "Prezentatsiya tayyorla: sun'iy intellekt qanday imkoniyatlar beradi",
        "Toshkentda yoshlar uchun qanday imkoniyatlar bor?",
        "Что ты можешь получить из этого отчёта?",
        "Please analyze the documentation I attached and summarise it",
        "Make a presentation to help students learn Python from https://docs.python.org",
        "I study at https://wiut.uz and want to improve my IELTS speaking",
        "Shu maqolani tahlil qil: https://kun.uz/news/2026/10/19/test",
        "Rasm chiz: o'rganayotgan bola, https://example.com uslubida",
        "Men ingliz tilini o'rganmoqchiman",
        "https://example.org saytini tarjima qil",
        "Python kutubxonalarini o'rganmoqchiman",
        "Toshkent kutubxonasiga bordim",
        "I want to learn the pandas library",
        "bu kutubxonani o'rgan",
    ],
)
def test_other_tasks_are_not_taken_over(text: str) -> None:
    assert not routed(text), text


@pytest.mark.parametrize(
    ("text", "kind", "identifier"),
    [
        ("fastapi kutubxonasini o'rgan", "pypi", "fastapi"),
        ("react kutubxonasini o'rgan", "npm", "react"),
        ("npm axios paketini o'rgan", "npm", "axios"),
        ("javascript dayjs-plus kutubxonasini o'rgan", "npm", "dayjs-plus"),
        ("Learn this library: pydantic", "pypi", "pydantic"),
        ("pallets/flask repozitoriyasini o'rgan", "github", "pallets/flask"),
        (
            "https://github.com/psf/requests va fastapi kutubxonasini o'rgan",
            "github",
            "psf/requests",
        ),
    ],
)
def test_plain_word_targets(text: str, kind: str, identifier: str) -> None:
    from ezo_api.learning.targets import parse_target

    target = parse_target(text)
    assert target is not None and (target.kind, target.identifier) == (kind, identifier)
