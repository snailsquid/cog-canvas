import asyncio
import io
import json
import re
from typing import Any, Dict

import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.data_manager import bundled_data_path

from .layout import CanvasError, Renderer

CODE_BLOCK_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)

DEMO: Dict[str, Any] = {
    "width": 480,
    "scale": 2,
    "background": "#1e1f22",
    "root": {
        "type": "column", "padding": 12, "gap": 10,
        "children": [
            {"type": "row", "gap": 10, "children": [
                {"type": "box", "flex": 1, "fill": "#2b2d31", "radius": 8, "padding": 10,
                 "child": {"type": "text", "text": "row / box", "weight": "bold",
                           "align": "center", "valign": "middle"}},
                {"type": "box", "flex": 2, "border": "#5865f2", "radius": 8, "padding": 10,
                 "child": {"type": "text", "text": "Text wraps to the width its parent gives it.",
                           "color": "#b5bac1"}},
            ]},
            {"type": "progress", "value": 0.62, "label": "progress 62%", "radius": 6,
             "height": 28, "weight": "medium"},
            {"type": "grid", "rows": 7, "empty": "#2b2d31",
             "cells": ["#0e4429", "#006d32", "#26a641", "#39d353", None] * 14},
        ],
    },
}


class Canvas(commands.Cog):
    """Renders JSON layout trees to PNG. Other cogs call `render(spec)`; see README.md."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.renderer = Renderer(bundled_data_path(self) / "fonts")

    async def red_delete_data_for_user(self, **kwargs) -> None:
        return

    # ---- public API ---------------------------------------------------------------------------

    async def render(self, spec: Dict[str, Any]) -> bytes:
        """Render a layout spec to PNG bytes. Raises ValueError if the spec is invalid."""
        return await asyncio.to_thread(self.renderer.render, spec)

    async def render_file(self, spec: Dict[str, Any], filename: str = "canvas.png") -> discord.File:
        """`render`, wrapped as a discord.File ready to send."""
        return discord.File(io.BytesIO(await self.render(spec)), filename=filename)

    # ---- commands -----------------------------------------------------------------------------

    @commands.group(name="canvas", invoke_without_command=True)
    async def canvas(self, ctx: commands.Context) -> None:
        """Render layout specs to images."""
        p = ctx.clean_prefix
        await ctx.send(
            f"`{p}canvas demo` · `{p}canvas render <json or .json attachment>`\n"
            "Node reference: <https://github.com/snailsquid/cog-canvas#spec>"
        )

    @canvas.command(name="demo")
    async def canvas_demo(self, ctx: commands.Context) -> None:
        """Render a sample showing every node type."""
        async with ctx.typing():
            await ctx.send(file=await self.render_file(DEMO, "demo.png"))

    @canvas.command(name="render")
    @commands.is_owner()
    async def canvas_render(self, ctx: commands.Context, *, spec: str = "") -> None:
        """Render a spec given as JSON (inline, in a code block, or as a .json attachment)."""
        if not spec and ctx.message.attachments:
            spec = (await ctx.message.attachments[0].read()).decode("utf-8", "replace")
        match = CODE_BLOCK_RE.match(spec.strip())
        if match:
            spec = match[1]
        try:
            data = json.loads(spec)
        except json.JSONDecodeError as e:
            await ctx.send(f"Invalid JSON: {e}")
            return
        async with ctx.typing():
            try:
                file = await self.render_file(data)
            except CanvasError as e:
                await ctx.send(f"Invalid spec: {e}")
                return
        await ctx.send(file=file)
