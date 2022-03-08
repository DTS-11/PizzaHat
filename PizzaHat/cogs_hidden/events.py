import discord
from discord.ext import commands

from core.cog import Cog


class Events(Cog):
    """Events cog"""
    def __init__(self, bot):
        self.bot = bot

    @Cog.listener()
    async def on_ready(self):
        await self.bot.db.execute("""CREATE TABLE IF NOT EXISTS warnlogs 
                    (guild_id BIGINT, user_id BIGINT, warns TEXT[], time NUMERIC[])""")
    
    @commands.Cog.listener()
    async def on_message(self, msg):
        if msg.author.bot:
            return

        if self.bot.user == msg.author:
            return
        
        if msg.content in {"<@860889936914677770>", "<@!860889936914677770>"}:
            em = discord.Embed(color=self.bot.color)
            em.add_field(
                name='<a:wave_animated:783393435242463324>  Hello!  <a:wave_animated:783393435242463324>',
                value=f'Im {self.bot.user.name}, to get started, my prefix is `p!` or `P!` or <@860889936914677770>')
            await msg.channel.send(embed=em)
    
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        # if more than half of the members are bots
        if len([m for m in guild.members if m.bot]) > len(guild.members) / 2:
            try:
                await guild.text_channels[0].send(
                    '👋 I have automatically left this server since it has a high bot to member ratio.')
                await guild.leave()
            except Exception as e:
                print(e)
        
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            pass
        elif isinstance(error, commands.NotOwner):
            pass
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send(f'You are missing some required permissions: ```diff\n- {error.missing_perms}```')
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send(f"I'm missing some required permissions:\n```diff\n- {error.missing_perms}```")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f'The command you tried is on cooldown. Try again in {round(error.retry_after)} seconds.'
                f'\n\n**Command name:**  {ctx.command}\n'
                f'**Cooldown time:**  {round(error.cooldown.per)} seconds'
                f'\n**Command uses:**  {error.cooldown.rate}'
            )
        elif isinstance(error, commands.RoleNotFound):
            await ctx.send('Please provide a role or the role could not be found.')
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send('Please specify a member or the member could not be found.')
        elif isinstance(error, commands.DisabledCommand):
            await ctx.send(f'**{ctx.command}**, is a disabled command in **{ctx.guild.name}**')
        elif isinstance(error, commands.ChannelNotFound):
            await ctx.send('The channel you have specified could not be found.')
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.author.send('This command cannot be used in DM\'s')
        elif isinstance(error, commands.EmojiNotFound):
            await ctx.send('Please provide an emoji or the emoji could not be found.')
        elif isinstance(error, commands.MissingRequiredArgument):
            em = discord.Embed(
                title=f'{ctx.command.qualified_name} command',
                description=f'```{ctx.prefix}{ctx.command.name} {ctx.command.signature}```\n',
                color=self.bot.color
            )
            em.add_field(name='Description', value=ctx.command.help, inline=False)
            em.set_footer(text="<> Required | [] Optional")
            await ctx.send(embed=em)

        else:
            # raise error  # for debugging
            em = discord.Embed(
                description=f'A weird error occured:\n```py\n{error}\n```',
                color=self.bot.color
            )
            await ctx.send(embed=em)

def setup(bot):
    bot.add_cog(Events(bot))
