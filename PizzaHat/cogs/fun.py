import discord
from discord.ext import commands
import asyncio
import random
import time
from TagScriptEngine import Interpreter, block
from typing import Union
from aiohttp import ClientSession
import requests
import json

class Fun(commands.Cog):
    """🥳 Fun Commands."""
    def __init__(self, bot):
        self.bot = bot
        blocks = [
            block.MathBlock(),
            block.RandomBlock(),
            block.RangeBlock(),
        ]
        self.engine = Interpreter(blocks)

    @commands.command()
    async def pressf(self, ctx, *, object):
        """Pay respect to something/someone by pressing the reaction."""
        try:
            message = await ctx.send(f'Press F to pay respect to `{object}`')
            await message.add_reaction('<:f_key:802611136361005097>')
            while True:
                def check(r, u):
                    return str(r.emoji) == '<:f_key:802611136361005097>' and r.message == message and u.id != self.bot.user.id
                reaction, user = await self.bot.wait_for('reaction_add', check=check, timeout=15.0)
                if reaction:
                    await ctx.send(f'**{user.name}** has paid their respects.')
        except asyncio.TimeoutError:
            await ctx.send('Timed out.')
            
    @commands.command()
    async def quote(self, ctx):
        try:
            res = requests.get('https://zenquotes.io/api/random/quote')
            data = json.load(res.text)
            quote = data[0]['q']
            author = data[0]['a']
            await ctx.reply(quote + " -" + author)
            return
        except:
            await ctx.send('Sorry, Something went wrong while trying to execute this command.')
            return 
        
    @commands.command()
    async def choose(self, ctx, *options):
        """Choose between multiple things.
        Max: 10 options."""
        if len(options) <= 1:
            await ctx.send('Min no: of options: 2')
            return
        if len(options) > 10:
            await ctx.send('Max no: of options: 10')
            return
        else:
            await ctx.send(f"{ctx.author.mention}, I choose `{random.choice(options)}`")

    @commands.command()
    async def enlarge(self, ctx, emoji: Union[discord.Emoji, discord.PartialEmoji, str]):
        """Enlarges a given emoji."""
        await ctx.send(emoji.url)
        
    @commands.command()
    async def reverse(self, ctx, *, text):
        """Reverse some text."""
        e = discord.Embed(color=self.bot.color)
        e.add_field(name='Input', value=f'```\n{text}\n```', inline=False)
        e.add_field(name='Output', value=f'```\n{text[::-1]}\n```', inline=False)
        await ctx.send(embed=e)
    
    @commands.command(aliases=["calc"])
    async def calculate(self, ctx, *, query):
        """Do some math calculations. Can't do algebraic expressions."""
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

    @commands.command(name='8ball', aliases=['8-ball'])
    async def _8ball(self, ctx, *, question):
        """Ask any question, and let the bot respond with the answers."""
        responses =['As I see it, yes.',
                'Ask again later.',
                'Better not tell you now.',
                'Cannot predict now.',
                'Concentrate and ask again.',
                'Don’t count on it.',
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
                'Yes – definitely.',
                'You may rely on it.']
        em = discord.Embed(
            title = 'Magic 8ball',
            description = f"Question: {question}\nAnswer: {random.choice(responses)}",
            color=self.bot.color
        )
        await ctx.send(embed=em)
    
    @commands.command()
    async def hack(self, ctx, member: discord.Member):
        """Hack someone and get their details."""
        used_words = ['Nerd','Sucker','Noob','Sup','Yo','Wassup','Nab','Nub','fool','stupid','b1tch','fvck','idiot']
        mails = ['@gmail.com','@hotmail.com','@yahoo.com']

        hacking = await ctx.send(f"Hacking {member.name}....")
        await asyncio.sleep(1.55)
        await hacking.edit(content='Finding info....')
        await asyncio.sleep(1.55)
        await hacking.edit(content=f"Discord email address: {member.name}{random.choice(mails)}")
        await asyncio.sleep(2)
        await hacking.edit(content=f"Password: x2yz{member.name}xxy65")
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

def setup(bot):
    bot.add_cog(Fun(bot))
