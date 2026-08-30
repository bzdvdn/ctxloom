"""repair services — geometry math and the `ensure_geometry` projection."""

from __future__ import annotations

import math

from ..models import ProjectInfo


class Geometry:
    def wall_area(self, length: float, width: float, height: float) -> float:
        return round(2 * (length + width) * height, 2)

    def floor_area(self, length: float, width: float) -> float:
        return round(length * width, 2)

    def perimeter(self, length: float, width: float) -> float:
        return round(2 * (length + width), 2)


def ensure_geometry(info: ProjectInfo) -> ProjectInfo:
    """Fills in geometry from area/length/width/ceiling_height (square of the area)."""
    g = Geometry()
    data = info.model_dump(exclude_none=True)
    if data.get("area") is None:
        if data.get("length") is not None and data.get("width") is not None:
            data["area"] = round(data["length"] * data["width"], 2)
    else:
        length = data.get("length")
        width = data.get("width")
        if length is None and width is None:
            side = math.sqrt(data["area"])
            data["length"] = round(side, 2)
            data["width"] = round(side, 2)
    data.setdefault("ceiling_height", 2.7)
    length = float(data.get("length") or 0.0)
    width = float(data.get("width") or 0.0)
    height = float(data.get("ceiling_height") or 2.7)
    data["floor_area"] = g.floor_area(length, width) if length and width else None
    data["walls_area"] = (
        g.wall_area(length, width, height) if length and width else None
    )
    data["ceiling_area"] = data["floor_area"]
    data["perimeter"] = g.perimeter(length, width) if length and width else None
    return ProjectInfo.model_validate(data)


def geometry_text(info: ProjectInfo) -> str:
    length = (info.length or 1.0) if (info.length or 0) else 1.0
    width = (info.width or 1.0) if (info.width or 0) else 1.0
    height = info.ceiling_height or 2.7
    g = Geometry()
    return (
        f"Комната: {info.room_type}, площадь пола {info.floor_area or g.floor_area(length, width)} м², "
        f"периметр {info.perimeter or g.perimeter(length, width)} м, "
        f"площадь стен {info.walls_area or g.wall_area(length, width, height)} м², "
        f"высота потолков {height} м"
    )


__all__ = ["Geometry", "ensure_geometry", "geometry_text"]
