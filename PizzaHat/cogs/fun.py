import asyncio
import random
import re
import string
import time
from typing import Optional, Union

import discord
from core.bot import PizzaHat
from core.cog import Cog
from discord.ext import commands
from discord.ext.commands import Context
from discord.ui import Button, View
from TagScriptEngine import Interpreter, block
from utils.config import (
    ADMIN_INVITE,
    DLISTGG_VOTE,
    REG_INVITE,
    SUPPORT_SERVER,
    TOPGG_TOKEN,
    TOPGG_VOTE,
    WUMPUS_VOTE,
)


def clean_string(string):
    string = re.sub("@", "@\u200b", string)
    string = re.sub("#", "#\u200b", string)
    return string


class PressFView(View):
    def __init__(self, user):
        self.users: list = [user]
        super().__init__(timeout=180)

    @discord.ui.button(
        emoji="<:f_key:802611136361005097>", style=discord.ButtonStyle.blurple
    )
    async def pressf(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.users:
            return await interaction.response.send_message(
                content="You have already paid your respects!", ephemeral=True
            )

        if isinstance(interaction.channel, discord.TextChannel):
            self.users.append(interaction.user.id)
            await interaction.channel.send(
                content=f"{interaction.user} has paid their respects."
            )

    async def on_timeout(self) -> None:
        del (
            self.users
        )  # delete the list of users after timeout to prevent excess usage of memory


class Fun(Cog, emoji=802615573556363284):
    """Add a dash of fun to your server with a collection of lively and entertaining commands!"""

    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot
        blocks = [
            block.MathBlock(),
            block.RandomBlock(),
            block.RangeBlock(),
        ]
        self.engine = Interpreter(blocks)
        self.regex = re.compile(r"(\w*)\s*(?:```)(\w*)?([\s\S]*)(?:```$)")

    @property
    def session(self):
        return self.bot.http._HTTPClient__session  # type: ignore

    async def _run_code(self, *, lang: str, code: str):
        res = await self.session.post(
            "https://emkc.org/api/v1/piston/execute",
            json={"language": lang, "source": code},
        )
        return await res.json()

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def afk(self, ctx: Context, *, reason: str):
        """Set an afk status."""

        if not ctx.guild:
            return

        data = (
            await self.bot.db.fetch(
                "SELECT reason FROM afk WHERE guild_id=$1 AND user_id=$2",
                ctx.guild.id,
                ctx.author.id,
            )
            if self.bot.db
            else None
        )

        if data:
            if data[0] == reason:
                return await ctx.send("You are already AFK with the same reason.")

            (
                await self.bot.db.execute(
                    "UPDATE afk SET reason=$1 WHERE guild_id=$2 AND user_id=$3",
                    reason,
                    ctx.guild.id,
                    ctx.author.id,
                )
                if self.bot.db
                else None
            )
            return await ctx.send(f"{self.bot.yes} AFK status updated successfully.")

        else:
            (
                await self.bot.db.execute(
                    "INSERT INTO afk (guild_id, user_id, reason) VALUES ($1, $2, $3)",
                    ctx.guild.id,
                    ctx.author.id,
                    reason,
                )
                if self.bot.db and ctx.guild
                else None
            )
            return await ctx.send(f"{self.bot.yes} AFK status set successfully.")

    @commands.command(name="credits")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def _credits(self, ctx: Context):
        """Shows the people who have contributed to this bot."""

        if self.bot.user and self.bot.user.avatar is not None:
            em = discord.Embed(
                title="Credits",
                color=discord.Color.green(),
                timestamp=ctx.message.created_at,
            )
            em.set_thumbnail(url=self.bot.user.avatar.url)

            em.add_field(
                name="Contributors",
                value="[View on GitHub](https://github.com/DTS-11/PizzaHat/graphs/contributors)",
                inline=False,
            )
            em.add_field(
                name="Bot avatar made by", value="Potato Jesus#1950", inline=False
            )

            await ctx.send(embed=em)

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def echo(self, ctx: Context, channel: discord.TextChannel, *, msg: str):
        """Makes the bot say something in another channel."""

        if not channel.permissions_for(ctx.author).send_messages:  # type: ignore
            return await ctx.message.add_reaction("⚠")

        msg = clean_string(msg)
        destination = ctx.message.channel if channel is None else channel

        await destination.send(msg)
        return await ctx.message.add_reaction("✅")

    @commands.command(aliases=["ss"])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def screenshot(self, ctx: Context, *, url: str):
        """Takes a screenshot."""

        await ctx.send(f"https://image.thum.io/get/https://{url}")

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def choose(self, ctx: Context, *options):
        """
        Choose between multiple things.
        Max: 10 options.
        """

        if len(options) <= 1:
            await ctx.send("Min no: of options: 2")
            return

        if len(options) > 10:
            await ctx.send("Max no: of options: 10")
            return

        else:
            e = discord.Embed(
                title="Choose",
                description=f"{ctx.author.mention}, I choose `{random.choice(options)}`",
                color=self.bot.color,
            )
            await ctx.send(embed=e)

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def reverse(self, ctx: Context, *, text):
        """Reverse some text."""

        e = discord.Embed(color=self.bot.color)
        e.add_field(name="Input", value=f"```\n{text}\n```", inline=False)
        e.add_field(name="Output", value=f"```\n{text[::-1]}\n```", inline=False)

        await ctx.send(embed=e)

    @commands.command(aliases=["calc"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def calculate(self, ctx: Context, *, query):
        """
        Do some simple math calculations.
        Cannot do algebraic expressions.
        """

        query = query.replace(",", "")
        engine_input = "{m:" + query + "}"

        start = time.monotonic()
        output = self.engine.process(engine_input)
        end = time.monotonic()

        output_string = output.body.replace("{m:", "").replace("}", "")

        embed = discord.Embed(
            color=self.bot.color,
            title=f"Input: `{query}`",
            description=f"Output: `{output_string}`",
        )
        embed.set_footer(text=f"Calculated in {round((end - start) * 1000, 3)} ms")

        await ctx.send(embed=embed)

    @commands.command(aliases=["tc", "taxcalc"])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def taxcalculator(self, ctx: Context, value: int):
        """Dank Memer tax-calculator."""

        # values
        calculation = round(value * 1.0869565217391304)
        amtLost = round(calculation - value)
        userGets = round(value - amtLost)

        # comma stuffs
        number_with_commas = "{:,}".format(calculation)
        number_with_commas_amt_lost = "{:,}".format(amtLost)
        to_calculate_with_commas = "{:,}".format(value)
        user_gets_with_commas = "{:,}".format(userGets)

        # actual embed
        embed = discord.Embed(title="Dank Memer Tax-Calculator", color=self.bot.color)
        embed.add_field(
            name="Amount to calculate",
            value=f"```\n⏣ {to_calculate_with_commas}```\nAmount expected to pay```css\n+ ⏣ {number_with_commas}```\nAmount lost by tax (5%)```diff\n- ⏣ {number_with_commas_amt_lost}```\nUser gets```fix\n⏣ {user_gets_with_commas}```",
            inline=False,
        )

        await ctx.send(embed=embed)

    @commands.command(name="8ball")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def _8ball(self, ctx: Context, *, question: str):
        """
        The Magic 8 Ball Oracle has answer to all the questions.
        Just ask!
        """

        responses = [
            "As I see it, yes.",
            "Ask again later.",
            "Better not tell you now.",
            "Cannot predict now.",
            "Concentrate and ask again.",
            "Dont count on it.",
            "It is certain.",
            "It is decidedly so.",
            "Most likely.",
            "My reply is no.",
            "My sources say no.",
            "Outlook not so good.",
            "Outlook good.",
            "Reply hazy, try again.",
            "Signs point to yes.",
            "Very doubtful.",
            "Without a doubt.",
            "Yes.",
            "Yes - definitely.",
            "You may rely on it.",
        ]

        em = discord.Embed(
            title="Magic 8ball",
            description=f"Question: {question}\nAnswer: {random.choice(responses)}",
            color=self.bot.color,
        )

        await ctx.send(embed=em)

    @commands.command()
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def hack(self, ctx: Context, member: discord.Member):
        """Hack someone and get their details."""

        used_words = [
            "Goofball",
            "Nitwit",
            "Dingbat",
            "Nincompoop",
            "Blockhead",
            "Doofus",
            "Buffoon",
            "Knucklehead",
            "Numbskull",
            "Dunderhead",
            "Lamebrain",
            "Bonehead",
            "Dipstick",
            "Dork",
            "Schmuck",
            "Jackass",
            "Muttonhead",
            "Halfwit",
            "Twit",
            "Bozo",
            "Peabrain",
            "Lummox",
            "Sap",
            "Mook",
            "Wally",
        ]

        mails = [
            "@gmail.com",
            "@hotmail.com",
            "@yahoo.com",
            "@icloud.com",
            "@outlook.com",
        ]

        if member is ctx.author:
            ctx.command.reset_cooldown(ctx)  # type: ignore
            return await ctx.send("You can't hack yourself bruh ._.")

        if member.bot:
            ctx.command.reset_cooldown(ctx)  # type: ignore
            return await ctx.send("You can't hack a bot ._.")

        random_things = ""

        for _ in range(3):
            random_things += (
                random.choice(string.ascii_letters)
                + random.choice(string.digits)
                + random.choice(string.punctuation)
                + random.choice(string.octdigits)
                + random.choice(string.hexdigits)
            )

        hacking = await ctx.send(f"Hacking {member.name}...")
        await asyncio.sleep(1.50)
        await hacking.edit(content="Finding exclusive information...")
        await asyncio.sleep(1.50)
        await hacking.edit(
            content=f"Discord email address: {member.name}{random.choice(mails)}"
        )
        await asyncio.sleep(2)
        await hacking.edit(
            content=f"Password: {member.name}{''.join(random.sample(random_things, len(random_things)))}"
        )
        await asyncio.sleep(2)
        await hacking.edit(content=f"Most used word: {random.choice(used_words)}")
        await asyncio.sleep(1.50)
        await hacking.edit(content="IP address: 192.168.255.1")
        await asyncio.sleep(1.50)
        await hacking.edit(content="Selling information to the government...")
        await asyncio.sleep(2)
        await hacking.edit(content="Hacking medical records...")
        await asyncio.sleep(1.50)
        await hacking.edit(
            content=f"Reporting {member.name} to Discord for violating ToS"
        )
        await asyncio.sleep(2)
        await hacking.edit(
            content=f"{ctx.author.mention} successfully hacked {member.mention}"
        )

        await ctx.send(
            "The ultimate, totally real hacking has been completed!",
        )

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def clap(self, ctx: Context, *, text: str):
        """👏 makes 👏 text 👏 look 👏 like 👏 this 👏"""

        text_lst = text.split()
        await ctx.send("👏 " + " ".join([f"{x} 👏" for x in text_lst]))

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def space(self, ctx: Context, char: str, *, text: str):
        """Replaces spaces with specified character."""

        await ctx.send(text.replace(" ", char))

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def coinflip(self, ctx: Context):
        """Flips a coin."""

        em = discord.Embed(
            title=f"{ctx.author.name} flipped a coin and got {random.choice(['heads', 'tails'])}!",
            color=discord.Color.random(),
        )

        await ctx.send(embed=em)

    @commands.command(name="invite")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def invite_cmd(self, ctx: Context):
        """Gives invite of bot."""

        view = View()

        b1 = Button(
            label="Invite (admin)",
            emoji="✉️",
            url=ADMIN_INVITE,
        )
        b2 = Button(
            label="Invite (recommended)",
            emoji="✉️",
            url=REG_INVITE,
        )
        b3 = Button(label="Support", emoji="📨", url=SUPPORT_SERVER)

        view.add_item(b1).add_item(b2).add_item(b3)

        em = discord.Embed(
            title="🔗 Links",
            description=(
                "Click on the links below if you cant see the buttons for some reason.\n"
                f"[Invite (admin)]({ADMIN_INVITE})\n"
                f"[Invite (recommended)]({REG_INVITE})\n"
                f"[Support]({SUPPORT_SERVER})"
            ),
            color=self.bot.color,
        )
        em.set_footer(text="Thank you for inviting me! <3")

        if self.bot.user is not None:
            em.set_author(
                name=self.bot.user.name,
                icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None,
            )

        await ctx.send(embed=em, view=view)

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def support(self, ctx: Context):
        """Gives link to support server"""

        await ctx.send(
            f"Do you want help? Join the support server now!\n{SUPPORT_SERVER}"
        )

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def vote(self, ctx):
        """Vote for the bot."""

        view = View()

        em = discord.Embed(
            title="Vote for me",
            description="Click the buttons below to vote!",
            color=self.bot.color,
        )

        if self.bot.user and self.bot.user.avatar is not None:
            em.set_thumbnail(url=self.bot.user.avatar.url)

        em.set_footer(text="Make sure to leave a nice review too!")

        b1 = Button(label="Top.gg", url=TOPGG_VOTE)
        b2 = Button(label="DList.gg", url=DLISTGG_VOTE)
        b3 = Button(label="Wumpus.store", url=WUMPUS_VOTE)

        view.add_item(b1).add_item(b2).add_item(b3)
        await ctx.send(embed=em, view=view)

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def pressf(self, ctx: Context, *, object: str):
        """Pay respect by pressing the F button."""

        em = discord.Embed(
            description=f"It's time to pay respect for **{object}**",
            color=self.bot.color,
            timestamp=ctx.message.created_at,
        )
        em.set_footer(
            text=ctx.author,
            icon_url=ctx.author.avatar.url if ctx.author.avatar else None,
        )

        await ctx.send(embed=em, view=PressFView(ctx.author))

    @commands.command()
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def checkvote(
        self, ctx: Context, member: Optional[Union[discord.Member, discord.User]] = None
    ):
        """Check if a user has voted or not."""

        member = member or ctx.author

        async with self.session.get(
            f"https://top.gg/api/bots/860889936914677770/check?userId={member.id}",
            headers={"Authorization": TOPGG_TOKEN},
        ) as topgg_resp:
            response = await topgg_resp.json()
            voted = response["voted"] == 1

            if voted:
                em = discord.Embed(
                    title="<a:peepo_pog:1267536669892935712> Voted!",
                    description=f"You have voted in the last **12** hours.\nClick [here]({TOPGG_VOTE}) to vote again.",
                    color=discord.Color.green(),
                    timestamp=ctx.message.created_at,
                )
            else:
                em = discord.Embed(
                    title="<:peepo_cry:1267536683872550922> Not Voted!",
                    description=f"You have not voted in the last **12** hours.\nClick [here]({TOPGG_VOTE}) to vote.",
                    color=discord.Color.red(),
                    timestamp=ctx.message.created_at,
                )
            return await ctx.send(embed=em)

    @commands.command()
    @commands.cooldown(3, 30, commands.BucketType.user)
    async def run(self, ctx: Context, *, codeblock: str):
        """Run code and get results instantly!"""

        matches = self.regex.findall(codeblock)
        if not matches:
            return await ctx.reply(
                embed=discord.Embed(
                    title="Uh-oh",
                    description="Please use codeblocks to run your code!",
                    color=discord.Color.red(),
                )
            )
        lang = matches[0][0] or matches[0][1]
        if not lang:
            return await ctx.reply(
                embed=discord.Embed(
                    title="Uh-oh",
                    description="Couldn't find the language hinted in the codeblock or before it",
                    color=discord.Color.red(),
                )
            )
        code = matches[0][2]
        result = await self._run_code(lang=lang, code=code)
        await self._send_result(ctx, result)

    async def _send_result(self, ctx: Context, result: dict):
        if "message" in result:
            return await ctx.reply(
                embed=discord.Embed(title="Uh-oh", description=result["message"])
            )
        output = result["output"]
        if len(output) > 2000:
            return await ctx.reply("Your output was too long.")
            # url = await create_guest_paste_bin(self.session, output)
            # return await ctx.reply("Your output was too long, so here's the pastebin link " + url)

        embed = discord.Embed(
            title=f"Ran your {result['language']} code",
            color=discord.Color.green(),
            timestamp=ctx.message.created_at,
        )
        output = output[:500].strip()
        shortened = len(output) > 500
        lines = output.splitlines()
        shortened = shortened or (len(lines) > 15)
        output = "\n".join(lines[:15])
        output += shortened * "\n\n**Output shortened**"
        embed.add_field(name="Output", value=f"```{output}```" or "**<No output>**")

        await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(Fun(bot))
