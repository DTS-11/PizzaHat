import asyncio
import datetime
import time
import unicodedata
from io import BytesIO
from typing import Optional, Union

import discord
import psutil
import pytz
import requests
from colorthief import ColorThief
from discord.ext import commands
from discord.ext.commands import Context
from discord.ui import Modal, Select, TextInput, View

from core.bot import PizzaHat
from core.cog import Cog
from utils.config import (
    BOOSTER_ROLE,
    CONTRIBUTOR_ROLE,
    PARTNER_ROLE,
    STAFF_ROLE,
    SUPPORT_SERVER,
)
from utils.embed import green_embed, normal_embed, orange_embed, red_embed

start_time = time.time()


def format_date(dt: Union[datetime.datetime, None]) -> str:
    if dt is None:
        return "N/A"
    return f"<t:{int(dt.timestamp())}>"


# def to_keycap(c) -> str:
#     return "\N{KEYCAP TEN}" if c == 10 else str(c) + "\u20e3"


class PollOptionsModal(Modal):
    def __init__(
        self,
        ctx: Context,
        cog,
        question: str,
        duration,
        channel,
        message,
        count: int,
        multiple: bool,
    ):
        super().__init__(title="Add Poll Options")
        self.ctx = ctx
        self.cog = cog
        self.question = question
        self.duration = duration
        self.channel = channel
        self.message = message
        self.option_inputs = []

        for i in range(count):
            option_input = TextInput(
                label=f"Option {i + 1}", placeholder=f"Enter option {i + 1}"
            )
            self.option_inputs.append(option_input)
            self.add_item(option_input)

        self.multiple = multiple

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user == self.ctx.author:
            return True

        await interaction.response.send_message(
            content="Not your interaction ._.", ephemeral=True
        )
        return False

    async def on_submit(self, interaction: discord.Interaction):
        options = [input.value for input in self.option_inputs if input.value.strip()]
        if not options:
            await interaction.response.send_message(
                "Please enter at least one option.", ephemeral=True
            )
            return

        poll_obj = discord.Poll(
            question=self.question, duration=self.duration, multiple=self.multiple
        )

        for option in options:
            poll_obj.add_answer(text=option)

        await self.channel.send(poll=poll_obj)
        self.option_inputs.clear()

        async def end_poll_callback(interaction: discord.Interaction):
            if interaction.user != self.ctx.author:
                return await interaction.response.send_message(
                    "Not your interaction ._.", ephemeral=True
                )

            try:
                await poll_obj.end()
                await interaction.response.send_message(
                    content="Poll ended.", ephemeral=True
                )
            except discord.HTTPException:
                await interaction.response.send_message(
                    content="Unable to end the poll. It might have already ended.",
                    ephemeral=True,
                )
            except discord.ClientException:
                await interaction.response.send_message(
                    content="Unable to end the poll because it has no attached message.",
                    ephemeral=True,
                )

        end_poll_view = View()
        end_poll_btn = discord.ui.Button(
            label="End Poll", style=discord.ButtonStyle.red
        )
        end_poll_btn.callback = end_poll_callback
        end_poll_view.add_item(end_poll_btn)

        new_embed = green_embed(
            title="Poll Created",
            description="The poll has been successfully created.",
            timestamp=True,
        )
        await self.message.edit(embed=new_embed, view=end_poll_view)


class Utility(Cog, emoji=1268851252565905449):
    """Utility commands that makes your Discord experience better!"""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot
        self.process = psutil.Process()

    @commands.command(aliases=["latency"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def ping(self, ctx: Context):
        """Shows latency of bot."""

        time1 = time.perf_counter()
        msg = await ctx.send("Pinging...")
        time2 = time.perf_counter()

        await msg.edit(
            content="🏓 Pong!"
            f"\nAPI: `{round(self.bot.latency * 1000)}ms`"
            f"\nBot: `{round(time2 - time1) * 1000}ms`"
        )

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def badges(
        self, ctx: Context, member: Optional[Union[discord.Member, discord.User]] = None
    ):
        """
        Shows different badges of a user.
        If no user is given, returns your badges.

        This command can be only used in the support server.
        """

        # thanks to .ddominik (Dominik#3040) for helping me out with this command.
        if ctx.guild.id != 764049436275114004 if ctx.guild else None:
            return await ctx.send(
                f"This command can be only used in the support server.\n{SUPPORT_SERVER}"
            )

        badges = []
        member = member or ctx.author

        if ctx.guild is not None:
            staff_role = ctx.guild.get_role(STAFF_ROLE)
            partner_role = ctx.guild.get_role(PARTNER_ROLE)
            booster_role = ctx.guild.get_role(BOOSTER_ROLE)
            contrib_role = ctx.guild.get_role(CONTRIBUTOR_ROLE)

            if member.id in self.bot.owner_ids:  # type: ignore
                badges.append("<:developer:1268856867585658981> Developer of PizzaHat")

            if isinstance(member, discord.Member):
                for roles in member.roles:
                    if roles == staff_role:
                        badges.append(
                            "<:squaredstaff:1268863165542961172> Staff Member in the support server"
                        )

                    elif roles == booster_role:
                        badges.append(
                            "<:booster:1268853959863570463> Booster in the support server"
                        )

                    elif roles == contrib_role:
                        badges.append(
                            "<:github:1267380265068789850> Contributor of PizzaHat"
                        )

                    elif roles == partner_role:
                        badges.append(
                            "<:partner:1268852831851642880> PizzaHat's Partner"
                        )

            em = normal_embed(title=f"{member} Badges")
            em.set_thumbnail(url=member.avatar.url if member.avatar else None)
            em.description = (
                "\n".join(badges)
                if len(badges) != 0
                else "This user has no special badges."
            )

            await ctx.send(embed=em)

    # @commands.command()
    # @commands.guild_only()
    # @commands.cooldown(1, 5, commands.BucketType.user)
    # @commands.has_permissions(manage_messages=True)
    # async def poll(self, ctx: Context, *, questions_and_choices: str):
    #     """
    #     Separate questions and answers by either `|` or `,`
    #     Supports up to 10 choices.
    #     """

    #     if "|" in questions_and_choices:
    #         delimiter = "|"

    #     elif "," in questions_and_choices:
    #         delimiter = ","

    #     else:
    #         delimiter = None

    #     if delimiter is not None:
    #         questions_and_choices = questions_and_choices.split(delimiter)  # type: ignore

    #     else:
    #         questions_and_choices = shlex.split(questions_and_choices)  # type: ignore

    #     if len(questions_and_choices) < 3:
    #         return await ctx.send("Need at least 1 question with 2 choices.")

    #     elif len(questions_and_choices) > 11:
    #         return await ctx.send("You can only have up to 10 choices.")

    #     perms = ctx.channel.permissions_for(ctx.guild.me)  # type: ignore
    #     if not (perms.read_message_history or perms.add_reactions):
    #         return await ctx.send(
    #             "I need `Read Message History` and `Add Reactions` permissions."
    #         )

    #     question = questions_and_choices[0]
    #     choices = [
    #         (to_keycap(e), v) for e, v in enumerate(questions_and_choices[1:], 1)
    #     ]

    #     try:
    #         await ctx.message.delete()

    #     except:
    #         pass

    #     fmt = "{0} asks: {1}\n\n{2}"
    #     answer = "\n".join("%s: %s" % t for t in choices)

    #     e = discord.Embed(
    #         description=fmt.format(
    #             ctx.message.author,
    #             question.replace("@", "@\u200b"),
    #             answer.replace("@", "@\u200b"),
    #         ),
    #         color=discord.Color.green(),
    #     )

    #     poll = await ctx.send(embed=e)
    #     for emoji, _ in choices:
    #         await poll.add_reaction(emoji)

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.has_permissions(create_polls=True)
    @commands.bot_has_permissions(create_polls=True)
    async def poll(
        self,
        ctx: commands.Context,
        duration: int,
        *,
        question: str,
        channel: Optional[discord.abc.Messageable] = None,
    ):
        """
        Create a poll using the new Polls feature.
        Supports up to 10 choices and duration must be in hours (API limitation)
        """

        if not ctx.guild:
            return

        if channel is None:
            channel = ctx.channel

        try:
            duration_timedelta = datetime.timedelta(hours=duration)
            if duration < 1:
                return await ctx.send(
                    embed=red_embed(f"{self.bot.no} Duration must be at least 1 hour.")
                )

        except ValueError as e:
            return await ctx.send(
                embed=red_embed(
                    f"{self.bot.no} Something went wrong while parsing the duration, please report this to the developers.\n{e}"
                )
            )

        add_options_view = View()

        async def select_callback(interaction: discord.Interaction):
            selected_value = int(select_menu.values[0])
            modal = PollOptionsModal(
                ctx,
                self,
                question,
                duration_timedelta,
                channel,
                msg,
                count=selected_value,
                multiple=(selected_value > 1),
            )
            await interaction.response.send_modal(modal)
            add_options_view.clear_items()

        select_menu = Select(
            placeholder="Select the number of options",
            options=[
                discord.SelectOption(label=str(i), value=str(i)) for i in range(1, 11)
            ],
            custom_id="poll_options_select",
        )
        select_menu.callback = select_callback
        add_options_view.add_item(select_menu)

        em = orange_embed(
            title="Configure Choices",
            description="Please select whether members can choose multiple options or just one.",
            timestamp=True,
        )
        em.set_author(
            name=ctx.author,
            icon_url=ctx.author.avatar.url if ctx.author.avatar else None,
        )
        msg = await ctx.send(embed=em, view=add_options_view)

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_messages=True)
    async def quickpoll(self, ctx: Context, *, question: str):
        """
        Quick and easy yes/no poll.
        For advanced poll, see `poll` command.
        """

        msg = await ctx.send(
            "**{}** asks: {}".format(
                ctx.message.author, question.replace("@", "@\u200b")
            )
        )

        await ctx.message.delete()

        yes_thumb = "👍"
        no_thumb = "👎"

        await msg.add_reaction(yes_thumb)
        await msg.add_reaction(no_thumb)

    @commands.command(aliases=["tzset", "timeset"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def timezoneset(self, ctx: Context):
        """Set your timezone."""

        await ctx.send(
            "Please enter your timezone. For a list of valid timezones, visit: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones\nYou have `2 minutes` to respond."
        )

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120.0)
        except asyncio.TimeoutError:
            await ctx.send("You didn't respond in time. Please try again.")
            return

        timezone = msg.content.strip()

        if timezone not in pytz.all_timezones:
            await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} That is not a valid timezone."
                )
            )
            return

        await self.bot.db.execute(
            "INSERT INTO user_timezone (user_id, timezone) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET timezone = $2",
            ctx.author.id,
            timezone,
        ) if self.bot.db else None

        await ctx.send(
            embed=green_embed(description=f"{self.bot.yes} Timezone set successfully.")
        )

    @commands.command(aliases=["tz", "time"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def timezone(
        self, ctx: Context, user: Optional[Union[discord.Member, discord.User]] = None
    ):
        """Shows the timezone and other info of a user or yourself."""

        user = user or ctx.author
        tz = (
            await self.bot.db.fetchval(
                "SELECT timezone FROM user_timezone WHERE user_id=$1", user.id
            )
            if self.bot.db
            else None
        )

        if tz:
            try:
                tz_time = datetime.datetime.now(pytz.timezone(tz))
                formatted_time = tz_time.strftime("%d-%m-%Y %H:%M:%S %Z")
                if user == ctx.author:
                    await ctx.send(
                        embed=normal_embed(
                            description=f"<:timer:1268872526549745736> Your timezone is `{tz}`.\nCurrent time: `{formatted_time}`"
                        )
                    )
                else:
                    await ctx.send(
                        embed=normal_embed(
                            description=f"<:timer:1268872526549745736> {user.mention}'s timezone is `{tz}`.\nCurrent time: `{formatted_time}`"
                        )
                    )

            except pytz.exceptions.UnknownTimeZoneError:
                await ctx.send(
                    embed=red_embed(
                        description=f"{self.bot.no} The timezone `{tz}` for {user.mention} is invalid. They may need to reset it."
                    )
                )

        else:
            await ctx.send(
                embed=red_embed(
                    description=f"{self.bot.no} I could not find the timezone for {user.mention}."
                )
            )

    @commands.command(aliases=["ui"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.guild_only()
    async def userinfo(
        self, ctx: Context, member: Optional[Union[discord.Member, discord.User]] = None
    ):
        """
        Shows info about a user.
        If no user is given, returns info about yourself.
        """

        member = member or ctx.author
        avatar_url = (
            member.avatar.url
            if member.avatar
            else "https://logos-world.net/wp-content/uploads/2020/12/Discord-Logo.png"
        )
        response = requests.get(avatar_url)
        image = BytesIO(response.content)
        color_thief = ColorThief(image)
        dominant_color = color_thief.get_color(quality=1)
        hex_color = "#{:02x}{:02x}{:02x}".format(*dominant_color)

        user_badges_flags = {
            "hypesquad_bravery": "<:bravery:876078067548835850>",
            "hypesquad_balance": "<:balance:876078067297173534>",
            "hypesquad_brilliance": "<:brilliance:876078066848366662>",
            "hypesquad": "<:hypesquad:1268857976655974413>",
            "partner": "<:partner:1268852831851642880>",
            "verified_bot_developer": "<:developer:1268856867585658981>",
            "active_developer": "<:activedev:1268867341886947462>",
            "bug_hunter_lvl_1": "<:bug_hunter_lvl1:876079074693480508> ",
            "bug_hunter_lvl_2": "<:bug_hunter_lvl2:876079074647371796>",
            "early_supporter": "<:earlysupporter:1268857611285958667>",
            "staff": "<:squaredstaff:1268863165542961172>",
            "discord_certified_moderator": "<:certified_mod_badge:1268876753883889706>",
        }
        misc_flags_descriptions = {
            "team_user": "Application Team User",
            "system": "System User",
            "verified_bot": "Verified Bot",
            "bot_http_interactions": "HTTP Interactions Bot",
        }

        set_flags = {flag for flag, value in member.public_flags if value}
        subset_flags = set_flags & user_badges_flags.keys()
        badges = [user_badges_flags[flag] for flag in subset_flags]

        em = discord.Embed(
            title="User Information",
            color=int(hex_color[1:], 16),
            timestamp=ctx.message.created_at,
        )
        em.description = f"""
<:newmember:1268853457855709255> **Username:** {member.display_name} `[{member}]`
<:id:1268872547915792487> **ID:** {member.id}
<:timer:1268872526549745736> **Created:** {format_date(member.created_at)}
{f"<:image:1268878284775755841> **[User Icon]({member.avatar.url})**" if member.avatar else ""}
        """

        em.set_thumbnail(url=avatar_url)
        em.set_footer(
            text=f"Requested by {ctx.author}",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else None,
        )

        if isinstance(member, discord.Member):
            uroles = [role.mention for role in member.roles if not role.is_default()]
            uroles.reverse()

            if len(uroles) > 15:
                uroles = [f"{', '.join(uroles[:10])} (+{len(member.roles) - 11})"]

            user_roles = (
                (" **({} Total)**").format(len(member.roles) - 1)
                if uroles != []
                else ("No roles")
            )

            em.add_field(
                name="Joined",
                value=format_date(member.joined_at),
                inline=False,
            )

            em.add_field(
                name="Roles", value=", ".join(uroles) + user_roles, inline=False
            )
            em.add_field(
                name="Member Bot",
                value=f"{self.bot.yes} Yes" if member.bot else f"{self.bot.no} No",
                inline=False,
            )

            if ctx.guild is not None:
                if ctx.guild.owner_id == member.id:
                    badges.append("<:owner:1268852819448823839>")

                elif (
                    isinstance(member, discord.Member)
                    and member.premium_since is not None
                ):
                    em.add_field(
                        name="Boosted",
                        value=format_date(member.premium_since),
                        inline=False,
                    )
                    badges.append("<:booster:1268853959863570463>")

            if badges:
                em.add_field(name="Badges", value=" ".join(badges), inline=False)

            await ctx.send(embed=em)

    @commands.command(aliases=["si"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.guild_only()
    async def serverinfo(self, ctx: Context):
        """Shows various info about the server."""

        def formatted_date(date):
            if date is None:
                return "N/A"
            return f"{date:%m-%d-%Y | %H:%M} UTC"

        if ctx.guild is not None:
            features = [f.lower().title().replace("_", " ") for f in ctx.guild.features]
            all_features = f"{self.bot.yes} " + f"\n{self.bot.yes} ".join(features)

            boost_level = (
                f"{ctx.guild.premium_tier} Level"
                if {ctx.guild.premium_tier} == 2
                else "No Level"
            )
            boosts = f"<:booster:1268853959863570463> {ctx.guild.premium_subscription_count} Boosts ({boost_level})"

            em = normal_embed(title=ctx.guild.name)
            em.set_thumbnail(
                url=(
                    ctx.guild.icon.url
                    if ctx.guild.icon
                    else "https://logos-world.net/wp-content/uploads/2020/12/Discord-Logo.png"
                )
            )
            em.set_footer(text=f"Created at: {formatted_date(ctx.guild.created_at)}")

            if ctx.guild.owner is not None:
                em.description = f"""
<:owner:1268852819448823839> **Owner:** {ctx.guild.owner.mention} `[{ctx.guild.owner}]`
<:description:1268877993862893618> **Description:** {ctx.guild.description if ctx.guild.description else "N/A"}
<:id:1268872547915792487> **ID:** {ctx.guild.id}
{f"<:image:1268878284775755841> **[Guild Icon]({ctx.guild.icon.url})**" if ctx.guild.icon else ""}
    """

            em.add_field(
                name="Members",
                value=(
                    f"<:member:1268853618887622717> Total: {ctx.guild.member_count}\n"
                    f"<:members:1268853443968106547> Humans: {len([m for m in ctx.guild.members if not m.bot])}\n"
                    f"<:bot:1268861825068564520> Bots: {sum(member.bot for member in ctx.guild.members)}"
                ),
                inline=False,
            )

            em.add_field(
                name="Channels",
                value=(
                    f"<:textchannel:1268867364183605248> Text: {len(ctx.guild.text_channels)}\n"
                    f"<:voicechannel:1268867352972234834> Voice: {len(ctx.guild.voice_channels)}\n"
                    f"<:file:1268857634790838272> Categories: {len(ctx.guild.categories)}"
                ),
                inline=False,
            )

            em.add_field(
                name="<:member:1268853618887622717> Role Count",
                value=len(ctx.guild.roles),
                inline=False,
            )
            em.add_field(
                name="<:emoji:1268867324195246133> Emoji Count",
                value=len(ctx.guild.emojis),
                inline=False,
            )

            em.add_field(
                name="<:verified:985139472813412362> Verification level",
                value=str(ctx.guild.verification_level).capitalize(),
                inline=False,
            )

            em.add_field(
                name="<:sparkle:1268870549879259210> Server Features",
                value=(
                    f"{boosts}\n" + all_features
                    if boosts and features
                    else f"{self.bot.no} None"
                ),
                inline=False,
            )

            await ctx.send(embed=em)

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.guild_only()
    async def channelinfo(
        self,
        ctx: Context,
        *,
        channel: Optional[Union[discord.TextChannel, discord.abc.Messageable]] = None,
    ):
        """
        Shows info about a channel.
        If no channel is given, returns info for the current channel.
        """

        if not ctx.guild:
            return

        channel = channel or ctx.channel

        if isinstance(channel, discord.TextChannel):
            em = normal_embed(title="Channel Information", timestamp=True)
            em.set_footer(text=ctx.guild.name)
            em.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)

            em.description = f"""
<:textchannel:1268867364183605248> **Channel:** {channel.mention} `[{channel.name}]`
<:id:1268872547915792487> **ID:** {channel.id}
<:file:1268857634790838272> **Category:** {f"{channel.category.name}" if channel.category else "N/A"}

<:timer:1268872526549745736> **Created:** {format_date(channel.created_at)}

<:danger:1268855303768903733> **NSFW:** {f"{self.bot.yes} Yes" if channel.nsfw else f"{self.bot.no} No"}
"""
            await ctx.send(embed=em)

        else:
            await ctx.send(f"{self.bot.no} That is not a text channel.")

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.guild_only()
    async def vcinfo(self, ctx: Context, vc: discord.VoiceChannel):
        """Shows info about a voice channel."""

        if not ctx.guild:
            return

        em = normal_embed(title="VC Information", timestamp=True)
        em.set_footer(text=ctx.guild.name)
        em.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)

        em.description = f"""
<:voicechannel:1268867352972234834> **Voice Channel:** {vc.mention} `[{vc.name}]`
<:id:1268872547915792487> **ID:** {vc.id}

<:timer:1268872526549745736> **Created:** {format_date(vc.created_at)}

<:megaphone:1268856128503152691> **Bitrate:** {vc.bitrate}
<:file:1268857634790838272> **Category:** {f"{vc.category.name}" if vc.category else "N/A"}
"""
        await ctx.send(embed=em)

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.guild_only()
    async def roleinfo(self, ctx: Context, role: discord.Role):
        """
        Gives some info about the specified role.
        You can mention the role or give the name of it.
        """

        major_perms = {
            "administrator": "Administrator",
            "manage_channels": "Manage Channels",
            "manage_roles": "Manage Roles",
            "manage_guild": "Manage Server",
            "manage_messages": "Manage Messages",
            "kick_members": "Kick Members",
            "ban_members": "Ban Members",
            "mention_everyone": "Mention Everyone",
            "manage_nicknames": "Manage Nicknames",
            "manage_emojis": "Manage Emojis",
            "manage_webhooks": "Manage Webhooks",
            "view_audit_log": "View Audit Log",
        }
        permissions: discord.Permissions = role.permissions
        active_major_perms = [
            name for perm, name in major_perms.items() if getattr(permissions, perm)
        ]

        em = discord.Embed(
            title="Role Information", color=role.color, timestamp=ctx.message.created_at
        )
        em.set_footer(text=role.guild.name)
        em.set_thumbnail(url=role.display_icon)

        em.description = f"""
**Role:** {role.mention} `({role.id})`
**Role Created:** {format_date(role.created_at)}

**Role Position:** {role.position}/{len(role.guild.roles)}
**Member Count:** {len(role.members)}/{role.guild.member_count}

**Hoisted:** {f"{self.bot.yes} Yes" if role.hoist else f"{self.bot.no} No"}
**Mentionable:** {f"{self.bot.yes} Yes" if role.mentionable else f"{self.bot.no} No"}

**Major Permissions:** {", ".join(active_major_perms) if active_major_perms else f"{self.bot.no} None"}
"""
        await ctx.send(embed=em)

    def get_bot_uptime(self, *, brief=False):
        now = datetime.datetime.now(datetime.timezone.utc)
        delta = now - self.bot.uptime
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)

        if not brief:
            if days:
                fmt = "{d} days, {h} hours, {m} minutes, and {s} seconds"
            else:
                fmt = "{h} hours, {m} minutes, and {s} seconds"

        else:
            fmt = "{h}h {m}m {s}s"
            if days:
                fmt = "{d}d " + fmt

        return fmt.format(d=days, h=hours, m=minutes, s=seconds)

    @commands.command(aliases=["stats"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def about(self, ctx: Context):
        """View bot statistics."""

        total_members = 0
        total_unique = len(self.bot.users)
        my_commands = [command for command in self.bot.walk_commands()]

        text = 0
        voice = 0
        guilds = 0

        for guild in self.bot.guilds:
            guilds += 1
            if guild.unavailable:
                continue

            total_members += guild.member_count or 0
            for channel in guild.channels:
                if isinstance(channel, discord.TextChannel):
                    text += 1

                elif isinstance(channel, discord.VoiceChannel):
                    voice += 1

        memory_usage = self.process.memory_full_info().uss / 1024**2
        cpu_count = psutil.cpu_count() or 1  # Ensure cpu_count is not None or zero
        cpu_usage = self.process.cpu_percent() / cpu_count

        dpy_version = discord.__version__
        dev = self.bot.get_user(710247495334232164)

        em = normal_embed()
        if dev and dev.avatar is not None:
            em.set_author(name=dev, icon_url=dev.avatar.url)

        em.title = "About"
        em.description = self.bot.description

        em.add_field(
            name="Users", value=f"{total_members} total\n{total_unique} unique"
        )

        em.add_field(
            name="Channels", value=f"{text + voice} total\n{text} text\n{voice} voice"
        )

        em.add_field(
            name="Process", value=f"{memory_usage:.2f} MiB\n{cpu_usage:.2f}% CPU"
        )

        em.add_field(name="Guilds", value=guilds)

        em.add_field(name="Commands", value=len(my_commands))

        em.add_field(name="Uptime", value=self.get_bot_uptime(brief=True))

        if self.bot.user and self.bot.user.avatar is not None:
            em.set_thumbnail(url=self.bot.user.avatar.url)
        em.set_footer(
            text=f"Made with 💖 with discord.py v{dpy_version}",
            icon_url="http://i.imgur.com/5BFecvA.png",
        )

        await ctx.send(embed=em)

    @commands.command()
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def suggest(self, ctx: Context, *, suggestion):
        """Suggest some cool features."""

        await ctx.send(
            embed=green_embed(
                f"{self.bot.yes} {ctx.author.mention}, your suggestion has been recorded!"
            )
        )
        channel = self.bot.get_channel(798259756803817545)

        em = green_embed(
            title="New Suggestion",
            description=f"> {suggestion}",
            timestamp=True,
        )

        if ctx.author.avatar is not None:
            em.set_author(
                name=ctx.author,
                icon_url=ctx.author.avatar.url if ctx.author.avatar else None,
            )

        await channel.send(embed=em)  # type: ignore

    # show perms
    async def say_permissions(self, ctx: Context, member, channel):
        permissions = channel.permissions_for(member)
        e = discord.Embed()
        allowed, denied = [], []
        for name, value in permissions:
            name = name.replace("_", " ").title()
            if value:
                allowed.append(name)
            else:
                denied.append(name)

        e.add_field(name="Allowed", value="\n".join(allowed))
        e.add_field(name="Denied", value="\n".join(denied))
        await ctx.send(embed=e)

    @commands.command(aliases=["perms"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def permissions(
        self,
        ctx: Context,
        *,
        member: Optional[Union[discord.Member, discord.User]] = None,
    ):
        """Shows a member's permissions.
        If used in DM's, shows your permissions in a DM channel."""

        member = member or ctx.author
        channel = ctx.message.channel

        await self.say_permissions(ctx, member, channel)

    @commands.command(aliases=["botperms"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def botpermissions(self, ctx: Context):
        """Shows the bot's permissions."""

        channel = ctx.channel
        if ctx.message.guild is not None:
            member = ctx.message.guild.me

            await self.say_permissions(ctx, member, channel)

    @commands.command(aliases=["av"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def avatar(
        self, ctx: Context, member: Optional[Union[discord.Member, discord.User]] = None
    ):
        """
        Displays a user's avatar
        If no member is provided, returns your avatar.
        """

        member = member or ctx.author
        em = discord.Embed(title=f"Avatar of {member.name}", color=member.color)

        if member.avatar is not None:
            em.set_image(url=member.avatar.url)

        em.set_footer(text=f"Requested by {ctx.author.name}")

        await ctx.send(embed=em)

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def charinfo(self, ctx: Context, *, characters: str):
        """
        Shows you information about some characters.
        Only up to 25 characters at a time.
        """

        if len(characters) > 25:
            await ctx.send(
                embed=red_embed(
                    f"{self.bot.no} Too many characters ({len(characters)}/25)"
                )
            )
            return

        fmt = "`\\U{0:>08}`: {1} - {2} \N{EM DASH}"

        def to_string(c):
            digit = format(ord(c), "x")
            name = unicodedata.name(c, "Name not found.")
            return fmt.format(digit, name, c)

        await ctx.send("\n".join(map(to_string, characters)))


async def setup(bot):
    await bot.add_cog(Utility(bot))
