from typing import Optional, Union

import discord
from async_lru import alru_cache
from core.bot import PizzaHat
from core.cog import Cog
from discord.ext import commands
from discord.ext.commands import Context
from utils.message import wait_for_msg


class AntiAltsSelectionView(discord.ui.View):
    def __init__(self, context: Context):
        super().__init__(timeout=180)
        self.level = 0
        self.context: Context = context
        self.cancelled = False

    @discord.ui.select(
        placeholder="Please select a level.",
        options=[
            discord.SelectOption(
                label="Level 01",
                description="Restrict the suspect from sending messages.",
                value="1",
                emoji="🚫",
            ),
            discord.SelectOption(
                label="Level 02",
                description="Kick the suspect from the server.",
                value="2",
                emoji="👞",
            ),
            discord.SelectOption(
                label="Level 03",
                description="Ban the suspect from the server.",
                value="3",
                emoji="<:ban:1268874381648465920>",
            ),
        ],
    )
    async def callback(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        if interaction.user != self.context.author:
            return await interaction.response.send_message(
                "Not your interaction ._.", ephemeral=True
            )

        self.level = int(select.values[0])

        await interaction.response.send_message(
            f"Anti-alt Level **{select.values[0]}** has been selected. Please click the `Next` button to continue.",
            ephemeral=True,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.context.author:
            return await interaction.response.send_message(
                "Not your interaction ._.", ephemeral=True
            )

        self.cancelled = True
        self.stop()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.green)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.context.author:
            return await interaction.response.send_message(
                "Not your interaction ._.", ephemeral=True
            )
        if self.level == 0:
            return await interaction.response.send_message(
                "Please select a level first!", ephemeral=True
            )

        self.stop()


class AntiAlts(Cog, emoji=1268851128548724756):
    """Configure Anti-Alt system in your server."""

    def __init__(self, bot):
        self.bot: PizzaHat = bot

    @alru_cache()
    async def get_aa_details(self, guild_id: int) -> Union[dict, None]:
        if self.bot.db is not None:
            data = await self.bot.db.fetchrow(
                "SELECT enabled, min_age, restricted_role, level FROM antialt WHERE guild_id=$1",
                guild_id,
            )

            return (
                {
                    "enabled": data["enabled"],
                    "min_age": data["min_age"],
                    "restricted_role": data["restricted_role"],
                    "level": data["level"],
                }
                if data
                else None
            )

    @commands.command(aliases=["antiraid"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def antialt(
        self,
        ctx: Context,
        config: str | None,
        setting: Optional[Union[discord.Role, str, int]] = None,
    ):
        """Setup anti-alt in your server."""

        if ctx.guild:
            data = await self.get_aa_details(ctx.guild.id)
            enabled = False
            if data is not None:
                enabled = data["enabled"]

            em = discord.Embed(
                title="Anti Alt Setup",
                description=f"""
Anti-alt system is currently **{"enabled" if enabled else "disabled"}**.

**Level:** {data["level"] if data else "0"}
**Minimum account age:** {data["min_age"] if data else "None"}
**Restricted role:** {data["restricted_role"] if data else "None"}
                """,
                color=self.bot.color,
                timestamp=ctx.message.created_at,
            )

            em.add_field(
                name="🚫  Level 01",
                value="The bot will restrict the suspect from sending messages in the server and log their info.",
                inline=True,
            )
            em.add_field(
                name="👞  Level 02",
                value="The bot will kick the suspect and log their info, they will be banned if they try to join again.",
                inline=True,
            )
            em.add_field(
                name="<:ban:1268874381648465920>  Level 03",
                value="The bot will ban the suspect and log their info.",
                inline=True,
            )
            em.add_field(
                name="Usage",
                value="""
<:certified_mod:1268851128548724756> Anti-alt configuration commands.
- **enable:** Enable anti-alt system.
- **disable:** Disable anti-alt system.
- **minage <time>:** Set minimum account age for newly joined accounts.
- **level <lvl>:** Set anti-alts protection level.
- **role <@role>:** Set restricted role to be given to restricted user.
            """,
                inline=False,
            )

            if config is None:
                return await ctx.send(embed=em)

            if config.lower() == "enable":
                if enabled:
                    return await ctx.send(
                        f"{self.bot.no} Anti-alt system is already enabled."
                    )

                min_account_age = None
                restricted_role = None

                view = AntiAltsSelectionView(context=ctx)
                msg = await ctx.reply(
                    f"""
**Anti-alt setup**

- Level.
- Minimum account age.
- Restricted role.

Please select a protection level.""",
                    view=view,
                )

                await view.wait()

                if view.cancelled:
                    return await msg.edit(content="Cancelled")

                await msg.edit(
                    content=f"""
**Anti-alt setup**

- Level: {view.level}
- Minimum account age.
- Restricted role.

Please enter the minimum account age requirement (in days).
Type `none` to have the default value (7 days).
Type `cancel` to cancel the setup.""",
                    view=None,
                )

                m = await wait_for_msg(ctx, 60, msg)
                if m == "pain":
                    return
                try:
                    if m.content.lower() != "none":  # type: ignore
                        temp_acc_age = int(m.content)  # type: ignore
                        if temp_acc_age <= 0:
                            return await msg.edit(
                                content=f"{self.bot.no} Account age can not be negative!"
                            )
                        min_account_age = temp_acc_age
                    else:
                        min_account_age = 7
                except Exception:
                    return await msg.edit(content=f"{self.bot.no} Integer values only!")

                await msg.edit(
                    content=f"""
**Anti-alt setup**

- Level: `{view.level}`
- Minimum account age: {min_account_age} days.
- Restricted role.

Please enter a restricted role.
Type `create` to create one automatically.
Type `cancel` to cancel the setup.
            """
                )

                m = await wait_for_msg(ctx, 60, msg)
                if m == "pain":
                    return
                if m.content.lower() != "create":  # type: ignore
                    try:
                        r_role = await commands.RoleConverter().convert(
                            ctx=ctx, argument=m.content  # type: ignore
                        )
                    except Exception:
                        return await msg.edit(
                            content="Unable to find that role. Please try again."
                        )
                    restricted_role = r_role.id
                else:
                    await msg.edit(
                        content="Creating the role, this may take a while..."
                    )
                    r_role = await ctx.guild.create_role(
                        name="Restricted", color=0x818386
                    )

                    for channel in ctx.guild.channels:
                        try:
                            await channel.set_permissions(
                                r_role,
                                speak=False,
                                send_messages=False,
                                add_reactions=False,
                            )
                        except Exception as e:
                            print(e)

                    restricted_role = r_role.id

                (
                    await self.bot.db.execute(
                        "INSERT INTO antialt VALUES ($1, $2, $3, $4, $5)",
                        ctx.guild.id,
                        True,
                        min_account_age,
                        restricted_role,
                        int(view.level),
                    )
                    if self.bot.db
                    else None
                )

                await msg.edit(
                    content=f"""
**Setup complete**

Here are your settings:

- Level: `{view.level}`
- Minimum account age: {min_account_age} days.
- Restricted role: <@&{restricted_role}>
                        """
                )
                return

            if config.lower() == "disable":
                if not enabled:
                    return await ctx.send(
                        f"{self.bot.no} Anti-alt system is already disabled."
                    )

                (
                    await self.bot.db.execute(
                        "INSERT INTO antialt (enabled) VALUES (false) WHERE guild_id=$1",
                        ctx.guild.id,
                    )
                    if self.bot.db
                    else None
                )
                return await ctx.send(
                    f"{self.bot.yes} Anti-alt system has been disabled."
                )

            if config.lower() == "minage":
                if not enabled:
                    return await ctx.send(
                        f"{self.bot.no} Anti-alt system is not enabled."
                    )
                if config is None:
                    return await ctx.send(
                        "Invalid usage.\nPlease use `p!antialt minage <number>`"
                    )
                if not isinstance(setting, int):
                    return await ctx.send("Minimum account age should be an integer!")
                if setting <= 0:
                    return await ctx.send("Minimum account age can not be negative!")

                (
                    await self.bot.db.execute(
                        "INSERT INTO antialt (min_age) VALUES ($1) WHERE guild_id=$2",
                        setting,
                        ctx.guild.id,
                    )
                    if self.bot.db
                    else None
                )
                return await ctx.send(
                    f"{self.bot.yes} Minimum account age has been updated to `{setting}` day(s)."
                )

            if config.lower() == "level":
                if not enabled:
                    return await ctx.send(
                        f"{self.bot.no} Anti-alt system is not enabled."
                    )
                if config is None:
                    return await ctx.send(
                        "Invalid usage.\nPlease use `p!antialt level <number>`"
                    )
                if not isinstance(setting, int) or not 1 <= setting <= 3:
                    return await ctx.send(
                        "Level number should be an integer between 1 and 3."
                    )

                (
                    await self.bot.db.execute(
                        "INSERT INTO antialt (level) VALUES ($1) WHERE guild_id=$2",
                        setting,
                        ctx.guild.id,
                    )
                    if self.bot.db
                    else None
                )
                return await ctx.send(
                    f"{self.bot.yes} Anti-alt protection level has been updated to `{setting}`."
                )

            if config.lower() == "role":
                if not enabled:
                    return await ctx.send(
                        f"{self.bot.no} Anti-alt system has is not enabled."
                    )
                if config is None:
                    return await ctx.send(
                        "Invalid usage.\nPlease use `p!antialt role @role`"
                    )
                if not isinstance(setting, discord.Role):
                    return await ctx.send(
                        "I could not find that role. Please try again."
                    )

                (
                    await self.bot.db.execute(
                        "INSERT INTO antialt (restricted_role) VALUES ($1) WHERE guild_id=$2",
                        setting,
                        ctx.guild.id,
                    )
                    if self.bot.db
                    else None
                )
                return await ctx.send(
                    f"{self.bot.yes} Restricted role has been updated to `{setting.name}`."
                )

            else:
                return await ctx.reply(embed=em)


async def setup(bot):
    await bot.add_cog(AntiAlts(bot))
