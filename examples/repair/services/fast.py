"""repair services — canned replies for routine phrases (as REPAIR_AI_CHAT)."""

from __future__ import annotations

_FAST_ABILITIES = (
    "что ты умеешь",
    "что умеешь",
    "что ты можешь",
    "что можешь",
    "чем можешь помочь",
    "чем можешь",
    "с чем можешь помочь",
    "какие возможности",
    "твои возможности",
    "как ты работаешь",
    "как работаешь",
    "расскажи о себе",
    "кто ты",
)
_FAST_THANKS = ("спасибо", "спасибки", "благодарю", "благодарен", "благодарна")
_FAST_FAREWELL = (
    "до свидания",
    "до встречи",
    "всего доброго",
    "всего хорошего",
    "пока",
    "прощай",
    "bye",
    "goodbye",
)
_FAST_GREETING = (
    "здравствуйте",
    "здравствуй",
    "добрый день",
    "добрый вечер",
    "доброе утро",
    "привет",
    "hello",
    "hi",
    "ку",
)
_FAST_SMALLTALK = (
    "как дела",
    "как у тебя дела",
    "как жизнь",
    "как настроение",
    "как сам",
    "как ты",
    "что нового",
    "как поживаешь",
)
#: Phrases stripped from the message to reveal the remainder (e.g.
#: «привет, сколько стоит плитка?» still reaches the pipeline).
_FAST_STRIP = (
    _FAST_ABILITIES
    + _FAST_THANKS
    + _FAST_FAREWELL
    + _FAST_GREETING
    + (
        "большое",
        "огромное",
        "очень",
    )
)

FAST_ABILITIES_TEXT = (
    "Что я умею:\n"
    "- спланировать ремонт комнаты по этапам;\n"
    "- подобрать материалы из каталога и цены;\n"
    "- рассчитать смету и уложиться в бюджет;\n"
    "- спросить у вас решения по дизайну.\n\n"
    "Например: «Спланируй ремонт ванной 5 м² бюджет 50 000»."
)
FAST_GREETING_TEXT = (
    "Здравствуйте! Я помогу спланировать ремонт, подобрать материалы "
    "и посчитать смету. Опишите комнату: тип, площадь и бюджет."
)
FAST_THANKS_TEXT = "Пожалуйста! Обращайтесь, если понадобится что-то ещё по ремонту."
FAST_FAREWELL_TEXT = "До свидания! Хорошего ремонта."


def fast_reply(text: str) -> str | None:
    """A canned reply for a routine message, or None — let the pipeline run.

    Abilities win immediately; thanks/farewell/greeting — only when no
    content remains after stripping the routine phrases («привет, сколько стоит
    плитка?» → None, it will reach the LLM).
    """
    norm = (" " + text.strip().lower() + " ").replace(",", " ").replace("?", "")
    if any(phrase in norm for phrase in _FAST_ABILITIES):
        return FAST_ABILITIES_TEXT

    rest = norm
    for phrase in _FAST_STRIP:
        rest = rest.replace(phrase, " ")
    rest = " ".join(rest.split())
    if rest and rest not in _FAST_SMALLTALK:
        return None

    if any(phrase in norm for phrase in _FAST_THANKS):
        return FAST_THANKS_TEXT
    if any(phrase in norm for phrase in _FAST_FAREWELL):
        return FAST_FAREWELL_TEXT
    if any(phrase in norm for phrase in _FAST_GREETING):
        return FAST_GREETING_TEXT
    return None


__all__ = [
    "FAST_ABILITIES_TEXT",
    "FAST_FAREWELL_TEXT",
    "FAST_GREETING_TEXT",
    "FAST_THANKS_TEXT",
    "fast_reply",
]
