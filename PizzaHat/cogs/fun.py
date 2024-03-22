import asyncio
import random
import re
import time

import discord
from core.bot import PizzaHat
from core.cog import Cog
from discord.ext import commands
from discord.ext.commands import Context
from discord.ui import Button, View
from TagScriptEngine import Interpreter, block


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
        """Shows all the people who have helped make this bot."""

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
        """Makes the bot say something in the specified channel"""

        if not channel.permissions_for(ctx.author).send_messages:  # type: ignore
            return await ctx.message.add_reaction("⚠")

        msg = clean_string(msg)
        destination = ctx.message.channel if channel is None else channel

        await destination.send(msg)
        return await ctx.message.add_reaction("✅")

    @commands.command(aliases=["ss"])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def screenshot(self, ctx: Context, *, url: str):
        """Takes a screenshot from a given URL."""

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
        """Do some math calculations. Cannot do algebraic expressions."""

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
        """Ask any question, and let the bot respond with the answers."""

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
    @commands.cooldown(1, 25, commands.BucketType.user)
    async def hack(self, ctx: Context, member: discord.Member):
        """Hack someone and get their details."""

        used_words = [
            "Nerd",
            "Sucker",
            "Noob",
            "Sup",
            "Yo",
            "Wassup",
            "Nab",
            "Nub",
            "fool",
            "stupid",
        ]
        mails = ["@gmail.com", "@hotmail.com", "@yahoo.com"]

        if member is ctx.author:
            return await ctx.send("You can't hack yourself.")

        hacking = await ctx.send(f"Hacking {member.name}....")
        await asyncio.sleep(1.55)
        await hacking.edit(content="Finding info....")
        await asyncio.sleep(1.55)
        await hacking.edit(
            content=f"Discord email address: {member.name}{random.choice(mails)}"
        )
        await asyncio.sleep(2)
        await hacking.edit(
            content=f"Password: x2yz{member.name}xxy65{member.discriminator}"
        )
        await asyncio.sleep(2)
        await hacking.edit(content=f"Most used words: {random.choice(used_words)}")
        await asyncio.sleep(1.55)
        await hacking.edit(content="IP address: 127.0.0.1:50")
        await asyncio.sleep(1.55)
        await hacking.edit(content="Selling information to the government....")
        await asyncio.sleep(2)
        await hacking.edit(
            content=f"Reporting {member.name} to Discord for violating ToS"
        )
        await asyncio.sleep(2)
        await hacking.edit(content="Hacking medical records.....")
        await asyncio.sleep(1.55)
        await hacking.edit(
            content=f"{ctx.author.mention} successfully hacked {member.mention}"
        )

        await ctx.send("The ultimate, totally real hacking has been completed!")

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
            url="https://discord.com/oauth2/authorize?client_id=860889936914677770&permissions=8&scope=bot",
        )
        b2 = Button(
            label="Invite (recommended)",
            emoji="✉️",
            url="https://discord.com/oauth2/authorize?client_id=860889936914677770&permissions=10432416312438&scope=bot",
        )
        b3 = Button(label="Support", emoji="📨", url="https://discord.gg/WhNVDTF")

        view.add_item(b1).add_item(b2).add_item(b3)

        em = discord.Embed(
            title="🔗 Links",
            description=(
                "Click on the links below if you cant see the buttons for some reason.\n"
                "[Invite (admin)](https://discord.com/oauth2/authorize?client_id=860889936914677770&permissions=8&scope=bot)\n"
                "[Invite (recommended)](https://discord.com/oauth2/authorize?client_id=860889936914677770&permissions=10432416312438&scope=bot)\n"
                "[Support](https://discord.gg/WhNVDTF)"
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
            "Do you want help? Join the support server now!\nhttps://discord.gg/WhNVDTF"
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

        b1 = Button(label="Top.gg", url="https://top.gg/bot/860889936914677770/vote")
        b2 = Button(
            label="DList.gg", url="https://discordlist.gg/bot/860889936914677770/vote"
        )
        b3 = Button(
            label="Wumpus.store", url="https://wumpus.store/bot/860889936914677770/vote"
        )

        view.add_item(b1).add_item(b2).add_item(b3)
        await ctx.send(embed=em, view=view)

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def pressf(self, ctx: Context, *, obj: str):
        """Pay respect to something by pressing the F button."""

        em = discord.Embed(
            description=f"It's time to pay respect for **{obj}**",
            color=self.bot.color,
            timestamp=ctx.message.created_at,
        )
        em.set_footer(
            text=ctx.author,
            icon_url=ctx.author.avatar.url if ctx.author.avatar else None,
        )

        await ctx.send(embed=em, view=PressFView(ctx.author))


async def setup(bot):
    await bot.add_cog(Fun(bot))
