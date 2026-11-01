from redbot.core import Config, commands
from redbot.core.bot import Red


class Canvas(commands.Cog):
    """Example cog. Replace this docstring with what the cog does."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=798301836560, force_registration=True)
        self.config.register_global(counter=0)

    async def cog_unload(self) -> None:
        # Cancel background tasks here.
        pass

    async def red_delete_data_for_user(self, **kwargs) -> None:
        return

    @commands.group(name="canvas", invoke_without_command=True)
    async def canvas(self, ctx: commands.Context) -> None:
        """Say hello and count how many times this ran."""
        count = await self.config.counter() + 1
        await self.config.counter.set(count)
        await ctx.send(f"Hello from canvas! (run #{count})")
        self.bot.dispatch("canvas_hello", ctx.author, count)

    @canvas.command(name="reset")
    @commands.is_owner()
    async def canvas_reset(self, ctx: commands.Context) -> None:
        """Reset the counter."""
        await self.config.counter.set(0)
        await ctx.send("Counter reset.")
