import shlex

import discord
from core.bot import PizzaHat
from core.cog import Cog
from discord.ext import commands
from discord.ext.commands import Context


def to_keycap(c):
    return "\N{KEYCAP TEN}" if c == 10 else str(c) + "\u20e3"


class Polls(Cog, emoji="🗳"):
    """Poll voting system."""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_messages=True)
    async def poll(self, ctx: Context, *, questions_and_choices: str):
        """
        Separate questions and answers by either `|` or `,`
        Supports up to 10 choices.

        To use this command, you must have Manage Messages permission.
        """

        if "|" in questions_and_choices:
            delimiter = "|"

        elif "," in questions_and_choices:
            delimiter = ","

        else:
            delimiter = None

        if delimiter is not None:
            questions_and_choices = questions_and_choices.split(delimiter)  # type: ignore

        else:
            questions_and_choices = shlex.split(questions_and_choices)  # type: ignore

        if len(questions_and_choices) < 3:
            return await ctx.send("Need at least 1 question with 2 choices.")

        elif len(questions_and_choices) > 11:
            return await ctx.send("You can only have up to 10 choices.")

        perms = ctx.channel.permissions_for(ctx.guild.me)  # type: ignore
        if not (perms.read_message_history or perms.add_reactions):
            return await ctx.send(
                "I need `Read Message History` and `Add Reactions` permissions."
            )

        question = questions_and_choices[0]
        choices = [
            (to_keycap(e), v) for e, v in enumerate(questions_and_choices[1:], 1)
        ]

        try:
            await ctx.message.delete()

        except:
            pass

        fmt = "{0} asks: {1}\n\n{2}"
        answer = "\n".join("%s: %s" % t for t in choices)

        e = discord.Embed(
            description=fmt.format(
                ctx.message.author,
                question.replace("@", "@\u200b"),
                answer.replace("@", "@\u200b"),
            ),
            color=discord.Color.green(),
        )

        poll = await ctx.send(embed=e)
        for emoji, _ in choices:
            await poll.add_reaction(emoji)

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_messages=True)
    async def quickpoll(self, ctx: Context, *, question: str):
        """
        Quick and easy yes/no poll
        For advanced poll, see `poll` command.

        To use this command, you must have Manage Messages permission.
        """

        msg = await ctx.send(
            "**{}** asks: {}".format(
                ctx.message.author, question.replace("@", "@\u200b")
            )
        )

        try:
            await ctx.message.delete()

        except:
            pass

        yes_thumb = "👍"
        no_thumb = "👎"

        await msg.add_reaction(yes_thumb)
        await msg.add_reaction(no_thumb)

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_permissions(manage_messages=True)
    async def strawpoll(self, ctx: Context, *, question_and_choices: str):
        """
        Separate questions and answers by `|` or `,`
        At least two answers required.

        To use this command, you must have Manage Messages permission.
        """

        if "|" in question_and_choices:
            delimiter = "|"

        else:
            delimiter = ","

        question_and_choices = question_and_choices.split(delimiter)  # type: ignore

        if len(question_and_choices) == 1:
            return await ctx.send("Not enough choices supplied")

        elif len(question_and_choices) >= 31:
            return await ctx.send("Too many choices")

        question, *choices = question_and_choices
        choices = [x.lstrip() for x in choices]
        header = {"Content-Type": "application/json"}
        payload = {"title": question, "options": choices, "multi": False}

        async with self.bot.session.post(
            "https://www.strawpoll.me/api/v2/polls", headers=header, json=payload
        ) as r:
            data = await r.json()
        id = data["id"]

        await ctx.send(f"http://www.strawpoll.me/{id}")


async def setup(bot):
    await bot.add_cog(Polls(bot))
