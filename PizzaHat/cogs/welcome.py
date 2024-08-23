import discord
from discord.ext import commands
from discord.ext.commands import Context

from core.bot import PizzaHat
from core.cog import Cog
from utils.embed import green_embed, normal_embed, red_embed
from utils.ui import Paginator


class Welcomer(Cog, emoji=1270391467415703682):
    """
    R users to your server.
    Either use the Welcome Images or the Welcome Embed.
    """

    def __init__(self, bot):
        self.bot: PizzaHat = bot

    @commands.group()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def welcome(self, ctx: Context):
        """Welcome commands."""

        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @welcome.command(name="channel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def welcome_channel(self, ctx: Context, channel: discord.TextChannel):
        """
        Set a welcome channel.
        To replace the welcome channel, simply run this command again.
        """

        if ctx.guild and self.bot.db:
            await self.bot.db.execute(
                "INSERT INTO welcome (guild_id, channel_id) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET channel_id=$2",
                ctx.guild.id,
                channel.id,
            )

            await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} Welcome channel set to {channel.mention}"
                )
            )

    @welcome.command(name="type")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def welcome_type(self, ctx: Context, type: str):
        """Set the welcome type."""

        if ctx.guild and self.bot.db:
            welcome_img_enabled: bool = False
            types: list[str] = ["embed", "image"]

            if type.lower() not in types:
                await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} Invalid welcome type. Valid types are {', '.join(types)}"
                    )
                )
                return

            if type.lower() == "image":
                welcome_img_enabled = True

            await self.bot.db.execute(
                "INSERT INTO welcome (guild_id, welcome_img_enabled) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET welcome_img_enabled=$2",
                ctx.guild.id,
                welcome_img_enabled,
            )

            await ctx.send(
                embed=green_embed(
                    description=f"{self.bot.yes} Welcome type set to `{type.capitalize()}`"
                )
            )

    @welcome.command(name="image")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def welcome_image(self, ctx: Context):
        """Set the welcome image."""

        if ctx.guild and self.bot.db:
            embeds: list[discord.Embed] = []
            files: list[discord.File] = []
            welcome_img_enabled: bool = await self.bot.db.fetchval(
                "SELECT welcome_img_enabled FROM welcome WHERE guild_id=$1",
                ctx.guild.id,
            )

            if not welcome_img_enabled:
                await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} Welcome type of image is not enabled."
                    )
                )
                return

            for i in range(1, 5):
                file = discord.File(
                    f"assets/images/welcome/pic{i}.png",
                    filename=f"welcome_image_{i}.png",
                )
                files.append(file)

                embed = normal_embed(title=f"Welcome Image {i}", timestamp=True)
                embed.set_image(url=f"attachment://welcome_image_{i}.png")
                embed.set_footer(text=f"Page {i}/4")
                embeds.append(embed)

            if len(embeds) == 1:
                return await ctx.send(embed=embeds[0], file=files[0])
            else:
                paginator = Paginator(ctx, embeds, files)
                return await ctx.send(embed=embeds[0], view=paginator, files=files[:1])


async def setup(bot):
    await bot.add_cog(Welcomer(bot))
