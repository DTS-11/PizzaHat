import discord
from discord.ext import commands
from discord.ext.commands import Context
from discord.ui import Button

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

            async def select_image(interaction: discord.Interaction):
                img_no = paginator.current + 1
                await self.bot.db.execute(
                    "INSERT INTO welcome_img (guild_id, welcome_img_no) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET welcome_img_no=$2",
                    ctx.guild.id,
                    img_no,
                ) if self.bot.db and ctx.guild else None
                await interaction.response.send_message(
                    embed=green_embed(
                        description=f"{self.bot.yes} Welcome image set to image number `{img_no}`."
                    )
                )

            select_btn = Button(style=discord.ButtonStyle.green, label="Select Image")
            select_btn.callback = select_image

            embeds: list[discord.Embed] = []
            file_paths: list[str] = []

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

            for i in range(1, 4):
                file_path = f"assets/images/welcome/pic{i}.png"
                file_paths.append(file_path)

                embed = normal_embed(title=f"Welcome Image {i}", timestamp=True)
                embed.set_image(url=f"attachment://welcome_image_{i}.png")
                embed.set_footer(text=f"Page {i}/3")
                embeds.append(embed)

            paginator = Paginator(ctx, embeds, file_paths)
            paginator.add_item(select_btn)
            file = paginator.get_current_file()
            first_embed = embeds[0]
            first_embed.set_image(url="attachment://image_1.png")

            if file:
                return await ctx.send(embed=first_embed, file=file, view=paginator)


async def setup(bot):
    await bot.add_cog(Welcomer(bot))
