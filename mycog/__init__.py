from redbot.core.bot import Red

from .mycog import MyCog


async def setup(bot: Red) -> None:
    await bot.add_cog(MyCog(bot))
