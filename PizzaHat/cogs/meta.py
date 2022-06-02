import asyncio
import random
import re
import time
import unicodedata
from typing import Union

import discord
from core.cog import Cog
from discord.ext import commands
from TagScriptEngine import Interpreter, block


def clean_string(string):
    string = re.sub('@', '@\u200b', string)
    string = re.sub('#', '#\u200b', string)
    return string


class Meta(Cog, emoji="😎"):
    """Miscellaneous commands."""
    def __init__(self, bot):
        self.bot = bot
        blocks = [
            block.MathBlock(),
            block.RandomBlock(),
            block.RangeBlock(),
        ]
        self.engine = Interpreter(blocks)

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def charinfo(self, ctx, *, characters: str):
        """Shows you information about a number of characters.
        Only up to 15 characters at a time.
        """

        if len(characters) > 15:
            await ctx.send('Too many characters ({}/15)'.format(len(characters)))
            return

        fmt = '`\\U{0:>08}`: {1} - {2} \N{EM DASH}'

        def to_string(c):
            digit = format(ord(c), 'x')
            name = unicodedata.name(c, 'Name not found.')
            return fmt.format(digit, name, c)

        await ctx.send('\n'.join(map(to_string, characters)))

    @commands.command(name="credits")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def _credits(self, ctx):
        """Shows all the people who have helped make this bot."""

        em = discord.Embed(
            title="Credits",
            color=self.bot.success,
            timestamp=ctx.message.created_at
        )
        em.set_thumbnail(url=self.bot.user.avatar.url)

        em.add_field(
            name="Contributors",
            value="[View on GitHub](https://github.com/DTS-11/PizzaHat/graphs/contributors)",
            inline=False
        )
        em.add_field(name="Bot avatar made by", value="Potato Jesus#1950", inline=False)
        
        await ctx.send(embed=em)

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def echo(self, ctx, destination: discord.TextChannel, *, msg: str):
        """Makes the bot say something in the specified channel"""

        if not destination.permissions_for(ctx.author).send_messages:
            return await ctx.message.add_reaction("⚠")
        msg = clean_string(msg)
        destination = ctx.message.channel if destination is None else destination
        await destination.send(msg)
        return await ctx.message.add_reaction("✅")

    @commands.command(aliases=["ss"])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def screenshot(self, ctx, *, url):
        """Takes a screenshot from a given URL."""

        await ctx.send(f"https://image.thum.io/get/https://{url}")
        
    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def choose(self, ctx, *options):
        """
        Choose between multiple things.
        Max: 10 options.
        """

        if len(options) <= 1:
            await ctx.send('Min no: of options: 2')
            return
        if len(options) > 10:
            await ctx.send('Max no: of options: 10')
            return
        else:
            e = discord.Embed(
                title="Choose",
                description=f"{ctx.author.mention}, I choose `{random.choice(options)}`",
                color=self.bot.color
            )
            await ctx.send(embed=e)

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def emojify(self, ctx, emoji: Union[discord.Emoji, discord.PartialEmoji, str]):
        """Emojify a given emoji."""

        await ctx.send(emoji.url)
        
    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def reverse(self, ctx, *, text):
        """Reverse some text."""

        e = discord.Embed(color=self.bot.color)
        e.add_field(name='Input', value=f'```\n{text}\n```', inline=False)
        e.add_field(name='Output', value=f'```\n{text[::-1]}\n```', inline=False)

        await ctx.send(embed=e)
    
    @commands.command(aliases=["calc"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def calculate(self, ctx, *, query):
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
    
    @commands.command(aliases=['tc', 'taxcalc'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def taxcalculator(self, ctx, value:int):
        """Dank Memer tax-calculator."""

        # values
        calculation = round(value * 1.0869565217391304)
        amtLost = round(calculation - value)
        userGets = round(value - amtLost)

        # comma stuffs  
        number_with_commas = '{:,}'.format(calculation)
        number_with_commas_amt_lost = '{:,}'.format(amtLost)
        to_calculate_with_commas = '{:,}'.format(value)
        user_gets_with_commas = '{:,}'.format(userGets)

        # actual embed
        embed = discord.Embed(
            title='Dank Memer Tax-Calculator',
            color=self.bot.color
        )
        embed.add_field(name='Amount to calculate',value=f'```\n⏣ {to_calculate_with_commas}```\nAmount expected to pay```css\n+ ⏣ {number_with_commas}```\nAmount lost by tax (5%)```diff\n- ⏣ {number_with_commas_amt_lost}```\nUser gets```fix\n⏣ {user_gets_with_commas}```',inline=False)
        
        await ctx.send(embed=embed)

    @commands.command(name='8ball')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def _8ball(self, ctx, *, question):
        """Ask any question, and let the bot respond with the answers."""

        responses = [
            'As I see it, yes.',
            'Ask again later.',
            'Better not tell you now.',
            'Cannot predict now.',
            'Concentrate and ask again.',
            'Dont count on it.',
            'It is certain.',
            'It is decidedly so.',
            'Most likely.',
            'My reply is no.',
            'My sources say no.',
            'Outlook not so good.',
            'Outlook good.',
            'Reply hazy, try again.',
            'Signs point to yes.',
            'Very doubtful.',
            'Without a doubt.',
            'Yes.',
            'Yes - definitely.',
            'You may rely on it.'
        ]

        em = discord.Embed(
            title = 'Magic 8ball',
            description = f"Question: {question}\nAnswer: {random.choice(responses)}",
            color=self.bot.color
        )

        await ctx.send(embed=em)
    
    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def hack(self, ctx, member: discord.Member):
        """Hack someone and get their details."""

        used_words = ['Nerd','Sucker','Noob','Sup','Yo','Wassup','Nab','Nub','fool','stupid']
        mails = ['@gmail.com','@hotmail.com','@yahoo.com']

        if member is ctx.author:
            return await ctx.send("You can't hack yourself.")
        else:
            hacking = await ctx.send(f"Hacking {member.name}....")
            await asyncio.sleep(1.55)
            await hacking.edit(content='Finding info....')
            await asyncio.sleep(1.55)
            await hacking.edit(content=f"Discord email address: {member.name}{random.choice(mails)}")
            await asyncio.sleep(2)
            await hacking.edit(content=f"Password: x2yz{member.name}xxy65{member.discriminator}")
            await asyncio.sleep(2)
            await hacking.edit(content=f'Most used words: {random.choice(used_words)}')
            await asyncio.sleep(1.55)
            await hacking.edit(content='IP address: 127.0.0.1:50')
            await asyncio.sleep(1.55)
            await hacking.edit(content='Selling information to the government....')
            await asyncio.sleep(2)
            await hacking.edit(content=f'Reporting {member.name} to Discord for violating ToS')
            await asyncio.sleep(2)
            await hacking.edit(content='Hacking medical records.....')
            await asyncio.sleep(1.55)
            await hacking.edit(content=f"{ctx.author.mention} successfully hacked {member.mention}")

            await ctx.send("The ultimate, totally real hacking has been completed!")


async def setup(bot):
    await bot.add_cog(Meta(bot))
