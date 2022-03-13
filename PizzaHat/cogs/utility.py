import discord
from discord.ext import commands
from discord.ui import Button, View
import time
import datetime
import shlex
import requests

from core.cog import Cog

start_time = time.time()

def to_keycap(c):
    return '\N{KEYCAP TEN}' if c == 10 else str(c) + '\u20e3'


class Utility(Cog, emoji="🛠️"):
    """Utility Commands"""
    def __init__(self,bot):
        self.bot = bot

    @commands.command(aliases=['latency'])
    async def ping(self,ctx):
        """Shows latency of bot."""
        await ctx.send(f":ping_pong: Pong!\nBot latency: `{round(self.bot.latency*1000)}ms`")

    @commands.command(aliases=['whois','ui'])
    @commands.guild_only()
    async def userinfo(self, ctx,  member:discord.Member=None):
        """
        Shows info about a user.
        
        If no user is given, returns value of yourself.
        """
        if member is None:
            member = ctx.author

        rolelist = [role.mention for role in list(member.roles[::-1]) if not role is ctx.guild.default_role] 
        roles = ", ".join(rolelist)

        def format_date(dt:datetime.datetime):
            if dt is None:
                return 'N/A'
            return f'<t:{int(dt.timestamp())}>'

        em = discord.Embed(
            color=member.color,
            timestamp=ctx.message.created_at
        )
        em.set_author(name=member, icon_url=member.avatar.url)
        em.add_field(name="User ID", value=member.id, inline=False)
        em.add_field(name="Display Name", value=member.display_name, inline=False)
        em.add_field(name="Account Creation", value=format_date(member.created_at), inline=False)
        em.add_field(name="Joined Server", value=format_date(member.joined_at), inline=False)
        em.add_field(name="", value=, inline=False)
        em.add_field(name=f'Roles [{len(rolelist)}]', value=roles or f'{self.bot.no} N/A', inline=False)
        if member.bot:
            em.add_field(name='Member Bot', value=f'{self.bot.yes} Yes', inline=False)
        else:
            em.add_field(name='Member bot', value=f'{self.bot.no} No', inline=False)
        em.set_footer(text=f"Requested by {ctx.author}", icon_url = ctx.author.avatar.url)
        em.set_thumbnail(url = member.avatar.url)
        await ctx.send(embed=em)
        
    @commands.command(aliases=['si'])
    @commands.guild_only()
    async def serverinfo(self, ctx):
        """Shows various info about the server."""
        def formatted_date(date):
            if date is None:
                return 'N/A'
            return f'{date:%m-%d-%Y | %H:%M} UTC'

        features = [f.lower().title().replace("_", " ") for f in ctx.guild.features]

        em = discord.Embed(title=f'{ctx.guild.name}', color=self.bot.color)
        em.add_field(name='<:owner:811749694744297502> Owner', value=ctx.guild.owner, inline=False)
        em.add_field(name='Description', value=ctx.guild.description, inline=False)
        em.add_field(name='Guild ID', value=ctx.guild.id, inline=False)
        em.add_field(name=f'Roles', value=len(ctx.guild.roles), inline=False)
        em.add_field(
            name=f'Members ({ctx.guild.member_count})',
            value=(
                f'<:memberlist:811747305543434260> Humans: {len([m for m in ctx.guild.members if not m.bot])}\n'
                f'<:botlist:811747723434786859> Bots: {sum(member.bot for member in ctx.guild.members)}'
            ),
            inline=False
        )
        em.add_field(
            name='Channels',
            value=(
                f'<:textchannel:811747767763992586> Text: {len(ctx.guild.text_channels)}\n'
                f'<:voicechannel:811748732906635295> Voice: {len(ctx.guild.voice_channels)}'
            ),
            inline=False
        )
        em.add_field(name='📁 Categories', value=len(ctx.guild.categories), inline=False)
        em.add_field(name='Emojis', value=len(ctx.guild.emojis), inline=False)
        em.add_field(
            name='Boost Info',
            value=(
                f'<:boosts:811749808133373996> Boosts: {ctx.guild.premium_subscription_count}\n'
                f'<:boostlevel:811749895143948288> Server level: {ctx.guild.premium_tier}'
            ),
            inline=False
        )
        em.add_field(
            name="Server Features",
            value=f'{self.bot.yes}' + f'\n{self.bot.yes}'.join(features) if features else f'{self.bot.no} None',
            inline=False
        )
        em.add_field(name='Verification level', value=str(ctx.guild.verification_level).capitalize(), inline=False)

        em.set_thumbnail(url=ctx.guild.icon.url)
        em.set_footer(text=f'Created at: {formatted_date(ctx.guild.created_at)}')
        
        await ctx.send(embed=em)

    @commands.command(aliases=['ci'])
    @commands.guild_only()
    async def channelinfo(self, ctx, channel:discord.TextChannel=None):
        """
        Shows info about a channel.
        If no channel is given, returns value for the current channel.
        """
        if channel is None:
            channel  = ctx.channel

        def format_date(dt:datetime.datetime):
            if dt is None:
                return 'N/A'
            return f'<t:{int(dt.timestamp())}>'

        e = discord.Embed(title='Channel information', color=self.bot.color)
        e.add_field(name='Channel name', value=channel.name, inline=True)
        e.add_field(name='Channel ID', value=channel.id, inline=True)
        e.add_field(name='Mention', value=f'`<#{channel.id}>`', inline=True)
        e.add_field(name='Category name', value=channel.category.name, inline=False)
        e.add_field(name='Channel Created', value=format_date(channel.created_at), inline=False)
        e.add_field(name="NSFW", value=f'{self.bot.yes} Yes' if channel.nsfw else f'{self.bot.no} No', inline=False)
        
        await ctx.send(embed=e)
    
    @commands.command(aliases=['ri'])
    @commands.guild_only()
    async def roleinfo(self, ctx, *, role: discord.Role):
        """Gives some info about the specified role.
        You can mention the role or give the name of it."""
        def format_date(dt:datetime.datetime):
            if dt is None:
                return 'N/A'
            return f'<t:{int(dt.timestamp())}>'

        e = discord.Embed(title='Role Information', color=self.bot.color)
        e.add_field(name='Role name', value=role.name, inline=True)
        e.add_field(name='Role ID', value=role.id, inline=True)
        e.add_field(name='Mention', value=f'`<@&{role.id}>`', inline=True)
        e.add_field(name='Role Created', value=format_date(role.created_at), inline=False)
        e.add_field(name='Role Color', value=role.color, inline=True)
        if role.mentionable:
            e.add_field(name='Mentionable', value=f'{self.bot.yes} Yes', inline=True)
        else:
            e.add_field(name='Mentionable', value=f'{self.bot.no} No', inline=True)
        
        await ctx.send(embed=e)

    def get_bot_uptime(self, *, brief=False):
        now = datetime.datetime.utcnow()
        delta = now - self.bot.uptime
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)

        if not brief:
            if days:
                fmt = '{d} days, {h} hours, {m} minutes, and {s} seconds'
            else:
                fmt = '{h} hours, {m} minutes, and {s} seconds'
        else:
            fmt = '{h}h {m}m {s}s'
            if days:
                fmt = '{d}d ' + fmt

        return fmt.format(d=days, h=hours, m=minutes, s=seconds)

    @commands.command(aliases=['stats'])
    async def botinfo(self, ctx):
        """Shows info about bot."""
        server_count = len(self.bot.guilds)
        total_users = len(set(self.bot.get_all_members()))
        dev = self.bot.get_user(710247495334232164)

        em = discord.Embed(
            title="Bot stats",
            color=self.bot.color
        )
        em.add_field(
            name="<:developer:833297795761831956> Developer",
            value=f"<:join_arrow:946077216297590836> <@710247495334232164> `[{dev}]`",
            inline=False
        )
        em.add_field(
            name="<:partnerbadge:819942435550396448> Servers",
            value=f"<:join_arrow:946077216297590836> `{server_count}`",
            inline=False
        )
        em.add_field(
            name="<:memberlist:811747305543434260> Users",
            value=f"<:join_arrow:946077216297590836> `{total_users}`",
            inline=False
        )
        em.add_field(
            name="<:pycord:929100002440122428> Pycord version",
            value=f"<:join_arrow:946077216297590836> `{discord.__version__}`",
            inline=False
        )
        em.add_field(
            name="⌛ Uptime",
            value=f"<:join_arrow:946077216297590836> `{self.get_bot_uptime(brief=True)}`",
            inline=False
        )

        em.set_thumbnail(url=self.bot.user.avatar.url)
        em.set_footer(text=f'Hosted by {dev}', icon_url=dev.avatar.url)

        await ctx.send(embed=em)

    @commands.command(aliases=['ei'])
    async def emojiinfo(self, ctx, emoji:discord.Emoji):
        """Shows info about emoji."""
        try:
            emoji = await emoji.guild.fetch_emoji(emoji.id)
        except discord.NotFound:
            return await ctx.send("I could not find this emoji in the given guild.")

        is_managed = "Yes" if emoji.managed else "No"
        is_animated = "Yes" if emoji.animated else "No"
        requires_colons = "Yes" if emoji.require_colons else "No"
        creation_time = emoji.created_at.strftime("%I:%M %p %B %d, %Y")
        can_use_emoji = (
            "Everyone"
            if not emoji.roles
            else " ".join(role.name for role in emoji.roles)
        )
        description = f"""
        **__General:__**
        **- Name:** {emoji.name}
        **- ID:** {emoji.id}
        **- URL:** [Link To Emoji]({emoji.url})
        **- Author:** {emoji.user.mention}
        **- Time Created:** {creation_time}
        **- Usable by:** {can_use_emoji}
        **__Others:__**
        **- Animated:** {is_animated}
        **- Managed:** {is_managed}
        **- Requires Colons:** {requires_colons}
        **- Guild Name:** {emoji.guild.name}
        **- Guild ID:** {emoji.guild.id}
        """
        embed = discord.Embed(
            title=f"**Emoji Information for:** `{emoji.name}`",
            description=description,
            colour=0xADD8E6,
        )
        embed.set_thumbnail(url=emoji.url)
        await ctx.send(embed=embed)

    @commands.command(name='invite')
    async def invite_cmd(self, ctx):
        """Gives invite of bot."""
        b1 = Button(label="Invite", emoji="✉️", url="https://dsc.gg/pizza-invite")
        b2 = Button(label="Support", emoji="📨", url="https://discord.gg/WhNVDTF")
        b3 = Button(label="Vote", emoji="🗳", url="https://top.gg/bot/860889936914677770/vote")
        view = View(b1, b2, b3)
        em=discord.Embed(
            title=':link: Links',
            description=(
                'Click on the links below if you cant see the buttons for some reason.\n'
                '[Invite me](https://dsc.gg/pizza-invite) | '
                '[Support](https://discord.gg/WhNVDTF) | '
                '[Vote](https://top.gg/bot/860889936914677770/vote)'
            ),
            color=self.bot.color
        )
        em.set_author(name=self.bot.user.name, icon_url=self.bot.user.avatar.url)
        em.set_footer(text='Thank you for inviting me! <3')
        await ctx.send(embed=em, view=view)

    @commands.command()
    async def support(self, ctx):
        """Gives link to support server"""
        await ctx.send('Do you want help? Join the support server now!\nhttps://discord.gg/WhNVDTF')

    @commands.command()
    async def suggest(self, ctx, *, suggestion):
        """Suggest some commands that should be included in bot."""
        await ctx.send(f'{self.bot.yes} {ctx.author.mention}, your suggestion has been recorded!')
        em = discord.Embed(color=self.bot.color)
        em.add_field(name='__New suggestion!__', value=suggestion, inline=False)
        em.set_footer(text=f'Sent by {ctx.author} from {ctx.guild}', icon_url = ctx.author.avatar.url)

        channel = self.bot.get_channel(818927218884345866)
        e = await channel.send(embed=em)
        await e.add_reaction('⬆️')
        await e.add_reaction('⬇️')

    # show perms
    async def say_permissions(self, ctx, member, channel):
        permissions = channel.permissions_for(member)
        e = discord.Embed()
        allowed, denied = [], []
        for name, value in permissions:
            name = name.replace('_', ' ').title()
            if value:
                allowed.append(name)
            else:
                denied.append(name)

        e.add_field(name='Allowed', value='\n'.join(allowed))
        e.add_field(name='Denied', value='\n'.join(denied))
        await ctx.send(embed=e)

    @commands.command(aliases=['perms'])
    async def permissions(self, ctx, *, member: discord.Member = None):
        """Shows a member's permissions.
        If used in DM's, shows your permissions in a DM channel."""
        channel = ctx.message.channel
        if member is None:
            member = ctx.author
        await self.say_permissions(ctx, member, channel)

    @commands.command(aliases=['botperms'])
    async def botpermissions(self, ctx):
        """Shows the bot's permissions."""
        channel = ctx.channel
        member = ctx.message.guild.me
        await self.say_permissions(ctx, member, channel)

    @commands.command(aliases=['av','profile','pfp'])
    async def avatar(self, ctx, member: discord.Member=None):
        """
        Displays a user's avatar
        If no member is provided, returns your avatar.
        """
        if not member:
            member = ctx.author
        
        em = discord.Embed(title=f"Avatar of {member.name}", color=self.bot.color)
        em.set_image(url=member.avatar.url)
        em.set_footer(text=f"Requested by {ctx.author.name}")
        await ctx.send(embed=em)
    
    @commands.command()
    async def vote(self,ctx):
        """Vote for the bot."""
        em = discord.Embed(
            title='Vote for me',
            description="Click the buttons below to vote!",
            color=self.bot.color
        )
        em.set_thumbnail(url=self.bot.user.avatar.url)
        em.set_footer(text='Make sure to leave a nice review too!')
        b1 = Button(label="Top.gg", url="https://top.gg/bot/860889936914677770/vote")
        b2 = Button(label="DBL", url="https://discordbotlist.com/bots/zion/upvote/")
        view = View(b1, b2)
        await ctx.send(embed=em, view=view)
    
    @commands.command()
    @commands.has_guild_permissions(manage_messages=True)
    async def poll(self, ctx, *, questions_and_choices: str):
        """
        Separate questions and answers by either `|` or `,` 
        supports up to 10 choices
        """
        if "|" in questions_and_choices:
            delimiter = "|"
        elif "," in questions_and_choices:
            delimiter = ","
        else:
            delimiter = None
        if delimiter is not None:
            questions_and_choices = questions_and_choices.split(delimiter)
        else:
            questions_and_choices = shlex.split(questions_and_choices)

        if len(questions_and_choices) < 3:
            return await ctx.send('Need at least 1 question with 2 choices.')
        elif len(questions_and_choices) > 11:
            return await ctx.send('You can only have up to 10 choices.')

        perms = ctx.channel.permissions_for(ctx.guild.me)
        if not (perms.read_message_history or perms.add_reactions):
            return await ctx.send('I need `Read Message History` and `Add Reactions` permissions.')

        question = questions_and_choices[0]
        choices = [(to_keycap(e), v)
                   for e, v in enumerate(questions_and_choices[1:], 1)]

        try:
            await ctx.message.delete()
        except:
            pass

        fmt = '{0} asks: {1}\n\n{2}'
        answer = '\n'.join('%s: %s' % t for t in choices)
        e = discord.Embed(
            description=fmt.format(ctx.message.author, question.replace("@", "@\u200b"), answer.replace("@", "@\u200b")),
            color=discord.Color.green()
            )
        poll = await ctx.send(embed=e)
        for emoji, _ in choices:
            await poll.add_reaction(emoji)

    @commands.command()
    @commands.has_guild_permissions(manage_messages=True)
    async def quickpoll(self, ctx, *, question: str):
        """
        Quick and easy yes/no poll
        For advanced poll, see `poll`
        """
        msg = await ctx.send("**{}** asks: {}".format(ctx.message.author, question.replace("@", "@\u200b")))
        try:
            await ctx.message.delete()
        except:
            pass
        yes_thumb = "👍"
        no_thumb = "👎"
        await msg.add_reaction(yes_thumb)
        await msg.add_reaction(no_thumb)

    @commands.command()
    @commands.has_guild_permissions(manage_messages=True)
    async def strawpoll(self, ctx, *, question_and_choices: str = None):
        """
        Separate questions and answers by `|` or `,`\nAt least two answers required.
        """
        if "|" in question_and_choices:
            delimiter = "|"
        else:
            delimiter = ","
        question_and_choices = question_and_choices.split(delimiter)
        if len(question_and_choices) == 1:
            return await ctx.send("Not enough choices supplied")
        elif len(question_and_choices) >= 31:
            return await ctx.send("Too many choices")
        question, *choices = question_and_choices
        choices = [x.lstrip() for x in choices]
        header = {"Content-Type": "application/json"}
        payload = {
            "title": question,
            "options": choices,
            "multi": False
        }
        async with self.bot.session.post("https://www.strawpoll.me/api/v2/polls", headers=header, json=payload) as r:
            data = await r.json()
        id = data["id"]
        await ctx.send(f"http://www.strawpoll.me/{id}")
        
def setup(bot):
    bot.add_cog(Utility(bot))
