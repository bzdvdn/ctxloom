"""Deterministic English prompt for interior generation (Krea understands EN
better). Built from the project facts and a design option (as in REPAIR).

Domain module: normalization of room/style/palette — Russian morphology.
"""

from __future__ import annotations

import re

from .models import DesignOption, ProjectInfo

_STYLE_WORDS: dict[str, str] = {
    "скандинавский": "scandinavian",
    "сканди": "scandinavian",
    "современный": "modern",
    "минимализм": "minimalist",
    "минималистичный": "minimalist",
    "лофт": "loft",
    "индастриал": "industrial",
    "классический": "classic",
    "классика": "classic",
    "неоклассика": "neoclassical",
    "прованс": "provence",
    "кантри": "country",
    "средиземноморский": "mediterranean",
    "морской": "nautical seaside",
    "эко": "eco natural",
    "японский": "japanese",
    "модерн": "art nouveau modern",
    "космический": "space themed",
    "космос": "space themed",
    "футуристический": "futuristic",
    "звёздный": "starry",
    "техно": "techno",
    "научная фантастика": "sci-fi",
}

#: Styles for which themed detail is added to the prompt.
_SPACE_STYLES = ("space", "starry", "futuristic", "techno", "sci-fi")

_SPACE_FLAVOR = (
    "space-themed details: a dark navy accent wall with a glowing galaxy or "
    "planet mural, a starry ceiling with tiny LED stars, rocket and astronaut "
    "wall decals, soft nebula lighting"
)

_COLOR_WORDS: dict[str, str] = {
    "тёплый белый": "warm white",
    "тёплая белая": "warm white",
    "светло-бежевый": "light beige",
    "светло-серый": "light gray",
    "тёмно-серый": "dark gray",
    "тёмно-синий": "navy",
    "светло-голубой": "baby blue",
    "светло-розовый": "blush pink",
    "светло-зелёный": "light green",
    "белый": "white",
    "белая": "white",
    "белое": "white",
    "серый": "gray",
    "серая": "gray",
    "бежевый": "beige",
    "бежевая": "beige",
    "кремовый": "cream",
    "кремовая": "cream",
    "молочный": "milky white",
    "голубой": "light blue",
    "голубая": "light blue",
    "розовый": "pink",
    "розовая": "pink",
    "зелёный": "green",
    "зелёная": "green",
    "мятный": "mint",
    "мятная": "mint",
    "салатовый": "sage green",
    "бирюзовый": "turquoise",
    "бирюзово": "turquoise",
    "жёлтый": "yellow",
    "жёлтая": "yellow",
    "оранжевый": "orange",
    "оранжевая": "orange",
    "терракотовый": "terracotta",
    "синий": "blue",
    "синяя": "blue",
    "фиолетовый": "purple",
    "лавандовый": "lavender",
    "бордовый": "burgundy",
    "коричневый": "brown",
    "коричневая": "brown",
    "песочный": "sand",
    "чёрный": "black",
    "чёрная": "black",
    "оливковый": "olive",
    "акцентный": "accent",
    "акцентная": "accent",
    "обои": "wallpaper",
    "обоями": "wallpaper",
    "с узором": "with a pattern",
    "узор": "pattern",
    "в полоску": "striped",
    "полосатая": "striped",
    "морская": "nautical",
    "морской": "nautical",
}

_FLOOR_WORDS: dict[str, str] = {
    "керамическая плитка": "ceramic tile flooring",
    "пробковое покрытие": "cork flooring",
    "натуральный дуб": "natural oak flooring",
    "ламинат": "laminate flooring",
    "паркет": "parquet flooring",
    "плитка": "ceramic tile flooring",
    "линолеум": "vinyl flooring",
    "кварцвинил": "luxury vinyl flooring",
    "дуб": "oak look",
}

_CODE_ROOMS: list[tuple[str, str, str]] = [
    (
        "детск",
        "kids room",
        "designed for a child: a cheerful accent wall with a colorful "
        "mural or themed wallpaper, playful pops of color, a cozy kids bed with soft colorful "
        "bedding, a small study desk with a reading lamp, a low open toy shelf with soft toys, "
        "a soft round rug, string lights or a cute pendant lamp, framed posters and wall decals",
    ),
    (
        "кух",
        "kitchen",
        "designed for a kitchen: a ceramic tile backsplash behind the worktop, "
        "modern cabinets with a countertop, built-in appliances, a dining set, task lighting",
    ),
    (
        "ван",
        "bathroom",
        "designed for a bathroom: large-format ceramic tiling, a bathtub or a "
        "glass-screened shower, a vanity sink with a mirror, water-resistant wall finish, "
        "a heated towel rail, soft waterproof ceiling lighting",
    ),
    (
        "спал",
        "bedroom",
        "designed for a bedroom: a cozy bed with a headboard against an accent "
        "wall, warm calm tones, bedside tables, a wardrobe, soft ambient lighting, storage niches",
    ),
    (
        "гост",
        "living room",
        "designed for a living room: a sofa facing a media accent wall "
        "with a TV, a coffee table, shelving, warm ambient and accent lighting",
    ),
    (
        "прихож",
        "hallway",
        "designed for a hallway: durable washable wall finish, an entrance "
        "wardrobe with a shoe bench, a hall mirror, bright functional entrance lighting",
    ),
    (
        "корид",
        "hallway",
        "designed for a hallway: durable washable wall finish, an entrance "
        "wardrobe, a hall mirror, bright functional entrance lighting",
    ),
]


def budget_tier(budget: float | None, area: float | None) -> str:
    """Finish tier (₽/m²): эконом / средний / премиум."""
    if not budget or not area or area <= 0:
        return "средний"
    per_m2 = budget / area
    if per_m2 < 15_000:
        return "эконом"
    if per_m2 < 35_000:
        return "средний"
    return "премиум"


_TIER_PHRASES: dict[str, str] = {
    "эконом": (
        "tasteful affordable renovation, neat finishes and smart budget materials "
        "styled with care — an inexpensive but beautiful patterned wallpaper or paint, "
        "cozy and warm, nothing bare or empty"
    ),
    "средний": (
        "quality mid-range renovation, durable nice materials, neat and well-finished, "
        "stylishly decorated, warm and inviting"
    ),
    "премиум": (
        "premium designer renovation, expensive refined materials, high-end fixtures "
        "and fittings, flawless finish, sophisticated and luxurious"
    ),
}


def _room_en(info: ProjectInfo) -> tuple[str, str]:
    room = (info.room_type or "").lower()
    for code, label, flavor in _CODE_ROOMS:
        if code in room:
            return label, flavor
    return "room", "designed as a well-planned, comfortable and organized space"


def _translate(text: str, words: dict[str, str]) -> str:
    """Russian words/phrases → English (starting with the longest ones)."""
    value = (text or "").strip()
    if not value:
        return ""
    for key in sorted(words, key=len, reverse=True):
        value = re.sub(re.escape(key), words[key], value, flags=re.IGNORECASE)
    return value.strip()


def build_image_prompt(info: ProjectInfo, option: DesignOption) -> str:
    """English prompt for rendering a single design option."""
    room, flavor = _room_en(info)
    area = info.area
    area_text = f"{area} m² floor area" if area else "a small room"
    height = info.ceiling_height or 2.7
    style_value = (option.palette.get("style") or "").strip()
    style = _translate(style_value, _STYLE_WORDS) or "contemporary scandinavian"
    style_flavor = _SPACE_FLAVOR if any(k in style for k in _SPACE_STYLES) else ""
    tier = _TIER_PHRASES.get(
        budget_tier(info.budget, info.area), _TIER_PHRASES["средний"]
    )

    palette: list[str] = []
    wall = _translate(option.palette.get("wall_color", ""), _COLOR_WORDS)
    if wall:
        palette.append(f"wall color {wall}")
    ceiling = _translate(option.palette.get("ceiling_color", ""), _COLOR_WORDS)
    if ceiling:
        palette.append(f"ceiling color {ceiling}")
    floor_raw = option.palette.get("floor_material", "")
    floor = _translate(floor_raw, {**_FLOOR_WORDS, **_COLOR_WORDS})
    if floor:
        palette.append(f"flooring {floor}")
    palette_text = "Featured palette: " + ", ".join(palette) + ". " if palette else ""

    return (
        f"Professional photorealistic interior photograph of a freshly renovated "
        f"{room}, {area_text}, ceiling height {height} m. "
        f"Interior style — {style}. Finish quality: {tier}. {palette_text}"
        f"Room specifics: {flavor}. "
        f"{style_flavor + '. ' if style_flavor else ''}"
        "Walls finished beautifully — affordable but pretty wallpaper with an elegant "
        "pattern or a rich painted color, well-leveled and clean, crisp trim and "
        "baseboards, neat plastered ceiling with recessed spotlights and a tasteful "
        "pendant fixture. The room is fully decorated and furnished — perfectly "
        "styled, lived-in and cozy, decorative objects, textiles, plants and artwork "
        "on the walls, not an empty bare room. Bright natural daylight, soft realistic "
        "materials, wide-angle architectural interior photography, high detail, "
        "no people, no text and no watermarks."
    )
