"""Layout tree -> PNG with Pillow. No Red imports, so it can be run and tested on its own.

A spec is a dict: {"width": 800, "scale": 2, "background": "#1e1f22", "root": <node>}.
Every node is a dict with a "type"; see README.md for the node reference. Sizes are in spec
units and multiplied by `scale` when drawn. Containers stretch children across their width
(columns) or height (rows); heights are measured from content unless set.
"""

import io
import math
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageColor, ImageDraw, ImageFont

Node = Dict[str, Any]
Rect = Tuple[float, float, float, float]  # x, y, w, h in pixels

FONT_FILES = {
    "regular": "NotoSans-Regular.ttf",
    "medium": "NotoSans-Medium.ttf",
    "bold": "NotoSans-Bold.ttf",
}
TYPES = {"row", "column", "box", "text", "progress", "grid", "spacer"}
CONTAINERS = {"row", "column", "box"}
COLOR_KEYS = ("fill", "border", "color", "track", "label_color", "empty")
NUMBER_KEYS = (
    "width", "height", "flex", "gap", "radius", "border_width", "size", "line_height",
    "value", "cell", "cell_radius", "rows", "cols",
)
ALIGNS = {"start", "center", "end"}
TEXT_ALIGNS = {"left", "center", "right"}
VALIGNS = {"top", "middle", "bottom"}

MAX_SIDE = 4096  # output pixels, per side
MAX_NODES = 5000
MAX_CELLS = 10000

DEFAULT_TEXT_SIZE = 16
DEFAULT_PROGRESS_HEIGHT = 32
DEFAULT_CELL = 12
DEFAULT_CELL_GAP = 3


class CanvasError(ValueError):
    """The spec is invalid. The message names the offending node."""


class Renderer:
    """Turns specs into PNG bytes. Holds the font cache; one per cog. Thread-safe."""

    def __init__(self, fonts_dir: Path) -> None:
        self.fonts_dir = fonts_dir
        self._fonts: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}
        self._lock = threading.Lock()  # FreeType faces aren't safe to share across threads

    def font(self, weight: str, size_px: float) -> ImageFont.FreeTypeFont:
        key = (weight, max(1, round(size_px)))
        if key not in self._fonts:
            self._fonts[key] = ImageFont.truetype(str(self.fonts_dir / FONT_FILES[weight]), key[1])
        return self._fonts[key]

    def render(self, spec: Dict[str, Any]) -> bytes:
        """Render `spec` to PNG bytes. Blocking; raises CanvasError for an invalid spec."""
        with self._lock:
            return _Job(self, spec).png()


# ---- validation -------------------------------------------------------------------------------


def _color(value: Any, path: str) -> None:
    try:
        ImageColor.getrgb(value)
    except (ValueError, TypeError, AttributeError):
        raise CanvasError(f"{path}: {value!r} is not a color") from None


def _check(node: Any, path: str, count: List[int]) -> None:
    if not isinstance(node, dict):
        raise CanvasError(f"{path}: expected a node object, got {type(node).__name__}")
    count[0] += 1
    if count[0] > MAX_NODES:
        raise CanvasError(f"more than {MAX_NODES} nodes")
    kind = node.get("type")
    if kind not in TYPES:
        raise CanvasError(f"{path}: unknown type {kind!r} (one of {', '.join(sorted(TYPES))})")
    path = f"{path}<{kind}>"
    for key in NUMBER_KEYS:
        if key in node and (isinstance(node[key], bool) or not isinstance(node[key], (int, float))):
            raise CanvasError(f"{path}.{key}: expected a number")
        if key in node and node[key] < 0:
            raise CanvasError(f"{path}.{key}: must not be negative")
    for key in COLOR_KEYS:
        if node.get(key) is not None:
            _color(node[key], f"{path}.{key}")
    padding = node.get("padding", 0)
    if not (
        isinstance(padding, (int, float))
        or (isinstance(padding, list) and len(padding) in (2, 4)
            and all(isinstance(p, (int, float)) for p in padding))
    ):
        raise CanvasError(f"{path}.padding: a number, [vertical, horizontal] or [t, r, b, l]")
    if node.get("weight", "regular") not in FONT_FILES:
        raise CanvasError(f"{path}.weight: one of {', '.join(FONT_FILES)}")
    for key, allowed in (("align", ALIGNS | TEXT_ALIGNS), ("valign", VALIGNS)):
        if key in node and node[key] not in allowed:
            raise CanvasError(f"{path}.{key}: one of {', '.join(sorted(allowed))}")

    if kind in ("row", "column"):
        children = node.get("children", [])
        if not isinstance(children, list):
            raise CanvasError(f"{path}.children: expected a list")
        for i, child in enumerate(children):
            _check(child, f"{path}.children[{i}]", count)
    elif kind == "box" and node.get("child") is not None:
        _check(node["child"], f"{path}.child", count)
    elif kind in ("text", "progress"):
        key = "text" if kind == "text" else "label"
        if node.get(key) is not None and not isinstance(node[key], str):
            raise CanvasError(f"{path}.{key}: expected a string")
    elif kind == "grid":
        cells = node.get("cells", [])
        if not isinstance(cells, list) or len(cells) > MAX_CELLS:
            raise CanvasError(f"{path}.cells: expected a list of at most {MAX_CELLS} cells")
        for i, cell in enumerate(cells):
            if isinstance(cell, dict):
                for key in ("fill", "border"):
                    if cell.get(key) is not None:
                        _color(cell[key], f"{path}.cells[{i}].{key}")
            elif cell is not None:
                _color(cell, f"{path}.cells[{i}]")


# ---- layout and drawing -----------------------------------------------------------------------


class _Job:
    """One render: validated spec, scale, and the image being drawn."""

    def __init__(self, renderer: Renderer, spec: Any) -> None:
        if not isinstance(spec, dict) or "root" not in spec:
            raise CanvasError("spec: expected an object with a `root` node")
        for key in ("width", "height", "scale"):
            if key in spec and (isinstance(spec[key], bool) or not isinstance(spec[key], (int, float))
                                or spec[key] <= 0):
                raise CanvasError(f"spec.{key}: expected a positive number")
        for key in ("background", "color"):
            if spec.get(key) is not None:
                _color(spec[key], f"spec.{key}")
        _check(spec["root"], "root", [0])
        self.r = renderer
        self.spec = spec
        self.s = min(float(spec.get("scale", 1)), 4.0)
        self.text_color = spec.get("color", "#ffffff")
        self.image: Optional[Image.Image] = None
        self.draw: Optional[ImageDraw.ImageDraw] = None

    def px(self, value: float) -> float:
        return value * self.s

    def png(self) -> bytes:
        root = self.spec["root"]
        width = self.px(self.spec.get("width", 800))
        height = self.px(self.spec["height"]) if "height" in self.spec else self.measure(root, width)
        size = (math.ceil(width), math.ceil(height))
        if not (0 < size[0] <= MAX_SIDE and 0 < size[1] <= MAX_SIDE):
            raise CanvasError(f"output would be {size[0]}x{size[1]} px (max {MAX_SIDE} per side)")
        self.image = Image.new("RGBA", size, self.spec.get("background", (0, 0, 0, 0)))
        self.draw = ImageDraw.Draw(self.image)
        self.paint(root, (0, 0, width, height))
        buffer = io.BytesIO()
        self.image.save(buffer, "PNG")
        return buffer.getvalue()

    # -- box model --

    def insets(self, node: Node) -> Tuple[float, float, float, float]:
        """Padding plus border, as (top, right, bottom, left) pixels."""
        p = node.get("padding", 0)
        if isinstance(p, (int, float)):
            p = [p] * 4
        elif len(p) == 2:
            p = [p[0], p[1], p[0], p[1]]
        border = node.get("border_width", 2) if node.get("border") else 0
        return tuple(self.px(v + border) for v in p)

    def inner(self, node: Node, rect: Rect) -> Rect:
        t, r, b, l = self.insets(node)
        x, y, w, h = rect
        return x + l, y + t, max(0.0, w - l - r), max(0.0, h - t - b)

    # -- measuring --

    def measure(self, node: Node, width: float) -> float:
        """Height in pixels of `node` laid out at `width` pixels."""
        if "height" in node:
            return self.px(node["height"])
        t, r, b, l = self.insets(node)
        inner_w = max(0.0, width - l - r)
        return t + b + self.content_height(node, inner_w)

    def content_height(self, node: Node, width: float) -> float:
        kind = node["type"]
        if kind == "text":
            return len(self.text_lines(node, width)) * self.line_height(node)
        if kind == "progress":
            return self.px(DEFAULT_PROGRESS_HEIGHT)
        if kind == "grid":
            return self.grid_size(node)[1]
        if kind == "box":
            child = node.get("child")
            return self.measure(child, width) if child else 0.0
        if kind == "column":
            children = node.get("children", [])
            gaps = self.px(node.get("gap", 0)) * max(0, len(children) - 1)
            return gaps + sum(self.measure(c, self.child_width(c, width)) for c in children)
        if kind == "row":
            children = node.get("children", [])
            widths = self.row_widths(node, width)
            return max((self.measure(c, w) for c, w in zip(children, widths)), default=0.0)
        return 0.0  # spacer

    def child_width(self, child: Node, available: float) -> float:
        return min(self.px(child["width"]), available) if "width" in child else available

    def row_widths(self, node: Node, width: float) -> List[float]:
        children = node.get("children", [])
        free = width - self.px(node.get("gap", 0)) * max(0, len(children) - 1)
        free -= sum(self.px(c["width"]) for c in children if "width" in c)
        total_flex = sum(c.get("flex", 1) for c in children if "width" not in c)
        return [
            self.px(c["width"]) if "width" in c
            else max(0.0, free) * c.get("flex", 1) / total_flex if total_flex else 0.0
            for c in children
        ]

    # -- text --

    def font_for(self, node: Node, default_size: float = DEFAULT_TEXT_SIZE):
        return self.r.font(node.get("weight", "regular"), self.px(node.get("size", default_size)))

    def line_height(self, node: Node) -> float:
        return self.px(node.get("size", DEFAULT_TEXT_SIZE)) * node.get("line_height", 1.25)

    def text_lines(self, node: Node, width: float) -> List[str]:
        font = self.font_for(node)
        lines: List[str] = []
        for paragraph in node.get("text", "").split("\n"):
            line = ""
            for word in paragraph.split(" "):
                candidate = f"{line} {word}" if line else word
                if line and font.getlength(candidate) > width:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
        return lines

    def draw_text_block(self, node: Node, rect: Rect, color: Any, default_valign: str) -> None:
        x, y, w, h = rect
        font = self.font_for(node)
        lines = self.text_lines(node, w)
        line_h = self.line_height(node)
        ascent, descent = font.getmetrics()
        valign = node.get("valign", default_valign)
        top = y + {"top": 0, "middle": (h - line_h * len(lines)) / 2, "bottom": h - line_h * len(lines)}[valign]
        align = node.get("align", "left")
        for i, line in enumerate(lines):
            length = font.getlength(line)
            lx = x + {"left": 0, "start": 0, "center": (w - length) / 2,
                      "right": w - length, "end": w - length}[align]
            ly = top + i * line_h + (line_h - ascent - descent) / 2
            self.draw.text((lx, ly), line, font=font, fill=color, anchor="la")

    # -- grid --

    def grid_shape(self, node: Node) -> Tuple[int, int]:
        n = len(node.get("cells", []))
        if "rows" in node:
            rows = max(1, int(node["rows"]))
            return rows, math.ceil(n / rows)
        cols = max(1, int(node.get("cols", n or 1)))
        return math.ceil(n / cols), cols

    def grid_size(self, node: Node) -> Tuple[float, float]:
        rows, cols = self.grid_shape(node)
        cell, gap = self.px(node.get("cell", DEFAULT_CELL)), self.px(node.get("gap", DEFAULT_CELL_GAP))
        return cols * cell + max(0, cols - 1) * gap, rows * cell + max(0, rows - 1) * gap

    # -- painting --

    def rect(self, rect: Rect, radius: float, fill: Any = None, outline: Any = None,
             width: float = 0) -> None:
        x, y, w, h = rect
        if w < 1 or h < 1:
            return
        x0, y0, x1, y1 = round(x), round(y), round(x + w) - 1, round(y + h) - 1
        style = dict(
            radius=round(min(radius, w / 2, h / 2)), fill=fill, outline=outline,
            width=max(1, round(width)) if outline else 0,
        )
        if all(c is None or ImageColor.getcolor(c, "RGBA")[3] == 255 for c in (fill, outline)):
            self.draw.rounded_rectangle([x0, y0, x1, y1], **style)
            return
        # Translucent: draw on its own layer and blend it in (drawing directly would replace pixels).
        layer = Image.new("RGBA", (x1 - x0 + 1, y1 - y0 + 1))
        ImageDraw.Draw(layer).rounded_rectangle([0, 0, x1 - x0, y1 - y0], **style)
        self.image.alpha_composite(layer, (max(0, x0), max(0, y0)))

    def paint(self, node: Node, rect: Rect) -> None:
        if node.get("fill") or node.get("border"):
            self.rect(
                rect, self.px(node.get("radius", 0)), fill=node.get("fill"),
                outline=node.get("border"), width=self.px(node.get("border_width", 2)),
            )
        inner = self.inner(node, rect)
        getattr(self, f"paint_{node['type']}")(node, inner)

    def paint_spacer(self, node: Node, rect: Rect) -> None:
        pass

    def paint_text(self, node: Node, rect: Rect) -> None:
        self.draw_text_block(node, rect, node.get("color", self.text_color), "top")

    def paint_box(self, node: Node, rect: Rect) -> None:
        if node.get("child"):
            self.paint(node["child"], rect)

    def aligned(self, size: float, available: float, align: str) -> float:
        if align in ("center", "middle"):
            return (available - size) / 2
        return available - size if align in ("end", "right", "bottom") else 0.0

    def paint_column(self, node: Node, rect: Rect) -> None:
        x, y, w, h = rect
        children = node.get("children", [])
        gap = self.px(node.get("gap", 0))
        widths = [self.child_width(c, w) for c in children]
        heights = [self.measure(c, cw) for c, cw in zip(children, widths)]
        # Leftover height goes to children with `flex` (spacers flex by default).
        extra = h - sum(heights) - gap * max(0, len(children) - 1)
        flexes = [c.get("flex", 1 if c["type"] == "spacer" else 0) if "height" not in c else 0
                  for c in children]
        if extra > 0 and sum(flexes):
            heights = [hh + extra * f / sum(flexes) for hh, f in zip(heights, flexes)]
        align = node.get("align", "start")
        for child, cw, ch in zip(children, widths, heights):
            self.paint(child, (x + self.aligned(cw, w, align), y, cw, ch))
            y += ch + gap

    def paint_row(self, node: Node, rect: Rect) -> None:
        x, y, w, h = rect
        gap = self.px(node.get("gap", 0))
        align = node.get("align", "start")
        for child, cw in zip(node.get("children", []), self.row_widths(node, w)):
            ch = min(self.px(child["height"]), h) if "height" in child else h
            self.paint(child, (x, y + self.aligned(ch, h, align), cw, ch))
            x += cw + gap

    def paint_progress(self, node: Node, rect: Rect) -> None:
        x, y, w, h = rect
        radius = self.px(node.get("radius", 0))
        value = min(1.0, max(0.0, float(node.get("value", 0))))
        self.rect(rect, radius, fill=node.get("track", "#3a3c42"))
        if value > 0:
            self.rect((x, y, max(1.0, w * value), h), radius, fill=node.get("color", "#5865f2"))
        if node.get("label"):
            label = {**node, "text": node["label"], "align": node.get("align", "center")}
            self.draw_text_block(label, rect, node.get("label_color", self.text_color), "middle")

    def paint_grid(self, node: Node, rect: Rect) -> None:
        x, y, w, h = rect
        rows, cols = self.grid_shape(node)
        gw, gh = self.grid_size(node)
        x += self.aligned(gw, w, node.get("align", "center"))
        y += (h - gh) / 2
        cell, gap = self.px(node.get("cell", DEFAULT_CELL)), self.px(node.get("gap", DEFAULT_CELL_GAP))
        radius = self.px(node.get("cell_radius", 2))
        by_column = "rows" in node
        for i, value in enumerate(node.get("cells", [])):
            row, col = (i % rows, i // rows) if by_column else (i // cols, i % cols)
            if isinstance(value, dict):
                fill, outline = value.get("fill"), value.get("border")
            else:
                fill, outline = value, None
            fill = fill if fill is not None or outline else node.get("empty")
            if fill is None and outline is None:
                continue
            self.rect(
                (x + col * (cell + gap), y + row * (cell + gap), cell, cell), radius,
                fill=fill, outline=outline, width=self.px(1),
            )
