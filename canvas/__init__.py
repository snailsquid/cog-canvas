from redbot.core.bot import Red

from .canvas import Canvas


async def setup(bot: Red) -> None:
    await bot.add_cog(Canvas(bot))
