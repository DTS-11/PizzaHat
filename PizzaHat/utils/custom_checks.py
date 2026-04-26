from core.bot import Tier
from discord.ext import commands
from discord.ext.commands import Context


class PremiumCheck(commands.CheckFailure):
    pass


_tier_cache = {}


def premium(tier: Tier = Tier.BASIC):
    """
    Check if the guild has the required tier level.
    tier: Minimum Tier required (default: BASIC - accepts BASIC or PRO)
    """
    required_tier = tier

    async def predicate(ctx: Context):
        if not ctx.guild:
            raise commands.CheckFailure(
                f"{ctx.bot.no} This command can only be used in a server."
            )

        if ctx.bot.db is None:
            raise PremiumCheck(
                f"{ctx.bot.no} This is a premium feature, you need {required_tier.name} to use this.\n[Click here to upgrade](https://pizzahat.vercel.app/premium)"
            )

        guild_id = ctx.guild.id

        cached_tier = _tier_cache.get(guild_id)
        if cached_tier is None:
            row = await ctx.bot.db.fetchrow(
                "SELECT tier FROM premium WHERE guild_id=$1", guild_id
            )
            if row:
                cached_tier = Tier(row["tier"])
                _tier_cache[guild_id] = cached_tier
            else:
                cached_tier = Tier.FREE
                _tier_cache[guild_id] = Tier.FREE

        if cached_tier >= required_tier:
            return True

        tier_names = {
            Tier.BASIC: "Basic",
            Tier.PRO: "Pro",
        }
        tier_name = tier_names.get(required_tier, required_tier.name)
        raise PremiumCheck(
            f"{ctx.bot.no} This is a premium feature, you need **{tier_name}** to use this.\n[Click here to upgrade](https://pizzahat.vercel.app/premium)"
        )

    return commands.check(predicate)


def clear_tier_cache(guild_id: int | None = None):
    """Clear the premium tier cache."""
    if guild_id:
        _tier_cache.pop(guild_id, None)
    else:
        _tier_cache.clear()
