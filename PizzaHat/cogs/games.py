import discord
from discord.ext import commands
import asyncio
import random
import datetime

from core.cog import Cog


class Games(Cog, emoji=819957465160220734):
    """Fun games to play when bored."""
    def __init__(self,bot):
        self.bot = bot

    @commands.command(aliases=['pie'])
    async def catch(self, ctx):
        """Catch the pie, by reacting. Dont't drop it!"""
        try:
            em = discord.Embed(color=self.bot.color)
            pie_title = '🥧  __Catch The Pie Game__  🥧'
            pie_desc = ('To catch the pie you must simply react with the emoji, when it appears.'
                        'Click as fast as you can and see how fast you caught it... \n'
                        '**Good Luck!** \n\n')
            pie_count_down = 'Here we go in {}...'

            em.add_field(name=pie_title, value=pie_desc + pie_count_down.format('3'), inline=False)
            pie1 = await ctx.send(embed=em)

            for i in range(2):
                await asyncio.sleep(1)

                em = discord.Embed(color=self.bot.color)
                em.add_field(
                    name=pie_title,
                    value=pie_desc + pie_count_down.format(str(3 - i - 1)),
                    inline=False
                )
                await pie1.edit(embed=em)

            await asyncio.sleep(1)
            await pie1.add_reaction('🥧')

            def check(reaction, user):
                self.reacted = reaction.emoji
                return user == ctx.author and str(reaction.emoji) and reaction.message == pie1

            before_wait = datetime.datetime.now()
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            after_wait = datetime.datetime.now()
            time_delta = after_wait - before_wait
            time_taken = time_delta.total_seconds()

            em = discord.Embed(color=self.bot.color)
            em.add_field(name=pie_title, value=pie_desc + f'You caught it in **{round(time_taken, 3)} seconds**', inline=False)
            await pie1.edit(embed=em)
        
        except asyncio.TimeoutError:
            await ctx.send("Timed out.")
    
    @commands.command(aliases = ['amongus'])
    async def impostor(self, ctx):
        """Classic among us game. Find the impostor **among us**"""
        embed1 = discord.Embed(
            title="Who's the imposter?",
            description="Find out who the imposter is, before the reactor breaks down!",
            color=self.bot.color
        )

        emojis = {
            'red': '<:red:818047547716796416>',
            'blue': '<:blue:818047575319511061>',
            'lime': '<:lime:818045625467666452>',
            'cyan': '<:cyan:818047548346073088>'
        }
        
        for key, val in emojis:
            embed1.add_field(name=key.capitalize(), value=val, inline=False)
        
        msg = await ctx.send(embed=embed1)
        
        imposter = random.choice(list(emojis.keys()))
        
        for emoji in emojis.values():
            await msg.add_reaction(emoji)
       
        def check(reaction, user):
            self.reacted = reaction.emoji
            return user == ctx.author and str(reaction.emoji) in emojis.values()

        defeat_img = 'https://preview.redd.it/7k5gzsbifco51.jpg?width=960&crop=smart&auto=webp&s=f997bdd801f3225d82de93d04fda906244bbd6a1'

        try: 
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
        except TimeoutError:
            embed = discord.Embed(
                title="Defeat",
                description=f"Reactor Meltdown. {imposter.capitalize()} was the imposter...",
                color = self.bot.failed
            )
            embed.set_image(url=defeat_img)
            await ctx.send(embed=embed)
        else:
            if str(self.reacted) == emojis[imposter]:
                embed = discord.Embed(
                    title="Victory",
                    description=f"**{imposter.capitalize()}** was the imposter, GG!",
                    color=self.bot.success)
                embed.set_image(url='https://i.redd.it/xop0vuu00fr51.png')
                await ctx.send(embed=embed)
            else:
                for key, value in emojis.items(): 
                    if value == str(self.reacted):
                        embed = discord.Embed(
                            title="Defeat",
                            description=f"Your choice was wrong, **{key}** was the imposter...",
                            color = self.bot.failed
                        )
                        embed.set_image(url=defeat_img)
                        await ctx.send(embed=embed)
                        break

    @commands.command()
    async def rps(self, ctx):
        """Rock Paper Scissors game."""
        try:
            rock_emoji = '\U0001faa8'
            paper_emoji = '\U0001f4dc'
            scissors_emoji = '\U00002702'
            rpsEmbed = discord.Embed(color=random.randint(0, 0xffffff))

            rpsEmbed.add_field(name='Rock', value=rock_emoji)
            rpsEmbed.add_field(name='Paper', value=paper_emoji)
            rpsEmbed.add_field(name='Scissors', value=scissors_emoji)
            rpsEmbed.set_footer(text='This message will be deleted after 1 min')
            
            question_choose = await ctx.send(embed=rpsEmbed)
            
            await question_choose.add_reaction(rock_emoji)
            await question_choose.add_reaction(paper_emoji)
            await question_choose.add_reaction(scissors_emoji)
            
            reaction, user = await self.bot.wait_for(
                'reaction_add',
                check=lambda reaction, user: user == ctx.author and str(reaction.emoji),
                timeout=60
            )
            
            selects = [rock_emoji, paper_emoji, scissors_emoji]
            
            bot_select = random.choice(selects)
            user_select = str(reaction.emoji)

            await question_choose.delete()

            res_name = ["Tie", "You Win", "You Lose"]
            res_img = [
                "https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/120/microsoft/209/anticlockwise-downwards-and-upwards-open-circle-arrows_1f504.png",
                "https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/120/twitter/259/check-mark-button_2705.png",
                "https://images.emojiterra.com/mozilla/512px/274c.png"
            ]

            if user_select == bot_select:
                result = 0
            elif ((user_select == rock_emoji and bot_select == scissors_emoji)
                or (user_select == scissors_emoji and bot_select == paper_emoji)
                or (user_select == paper_emoji and bot_select == rock_emoji)):
                result = 1
            else:
                result = 2
        
            choose_embed = discord.Embed(color=0x2ecc71)
            choose_embed.add_field(name='User Chose :bust_in_silhouette:', value=f'**{user_select}**', inline=True)
            choose_embed.add_field(name='Bot Chose :robot:', value=f'**{bot_select}**', inline=True)
            choose_embed.set_author(name=res_name[result], icon_url=res_img[result])
            choose_embed.set_footer(text=ctx.author.name, icon_url=ctx.author.avatar.url)

            await ctx.send(embed=choose_embed)

        except asyncio.TimeoutError:
            await ctx.send('The time is up, try again')

    @commands.command()
    async def flip(self,ctx):
        """Heads or Tails? Let's flip the coin and see!"""
        try:
            cancel = False
            EmbedHead = discord.Embed(title='__Coin Flipping Challenge__',color=self.bot.color)
            EmbedHead.add_field(name='What is your choice?', value='`Heads` or `Tails`', inline=False)
            EmbedHead.set_thumbnail(url='https://media1.tenor.com/images/38bf85bcecdd6aa52300d53e6eea06a1/tenor.gif')
            EmbedHead.set_footer(text='You have 1 minute to choose!')
            headORtail = await ctx.send(embed=EmbedHead)
            message = await self.bot.wait_for(
                'message', check=lambda m: m.author == ctx.author and m.channel == ctx.channel , timeout=60)
            
            heads = ('heads', 'h', 'head')
            tails = ('tails', 't', 'tail')

            lowered = message.content.lower()

            if lowered not in heads and lowered not in tails:
                await message.reply("Ur dumb, invalid option.")

            user_choose = int(lowered in heads)  # heads is 1, tails is 0

            fliping = await ctx.send('Flipping. ')
            await asyncio.sleep(1)
            await fliping.edit(content='Flipping.. ')

            rand = random.randint(0, 1)

            choose_embed = discord.Embed(color=self.bot.color)
            choose_embed.add_field(
                name='Your Choice :bust_in_silhouette:',
                value=f'{(heads[0] if user_choose else tails[0]).capitalize()}',
                inline=False
            )
            choose_embed.add_field(
                name='You Got :coin:',
                value=f'{(heads[0] if rand else tails[0]).capitalize()}',
                inline=False
            )
            choose_embed.set_author(
                name='You ' + ('Win' if user_choose == rand else 'Lose'),
                icon_url=(
                    'https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/120/twitter/259/check-mark-button_2705.png'
                    if user_choose == rand
                    else 'https://images.emojiterra.com/mozilla/512px/274c.png'
                )
            )
            await ctx.send(embed=choose_embed)
        except asyncio.TimeoutError:
            if not cancel:
                await headORtail.delete()
                await ctx.send('The time ended, please try again')


async def setup(bot):
    await bot.add_cog(Games(bot))
