import discord
from discord.ext import commands
import time
import datetime
import shlex
import requests

start_time = time.time()
def to_keycap(c):
    return '\N{KEYCAP TEN}' if c == 10 else str(c) + '\u20e3'

class Utility(commands.Cog):
    """🛠️ Utility Commands"""
    def __init__(self,bot):
        self.bot = bot

    @commands.command(aliases=['latency'])
    async def ping(self,ctx):
        """Shows latency of bot."""
        await ctx.send(f":ping_pong: Pong!\nBot latency: `{round(self.bot.latency*1000)}ms`")

    @commands.command(aliases=['whois','ui', 'user-info'])
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
            description=f"**User ID:** {member.id}\n**Display Name:** {member.display_name}\n\n**Account Creation:** {format_date(member.created_at)}\n**Joined Server:** {format_date(member.joined_at)}\n",
            color=self.bot.color,
            timestamp=ctx.message.created_at
        )
        em.set_author(name = f"Userinfo of {member}")
        em.add_field(name=f'Roles [{len(rolelist)}]', value=roles or f'{self.bot.no} N/A', inline=False)
        if member.bot:
            em.add_field(name='Member Bot', value=f'{self.bot.yes} Yes', inline=False)
        else:
            em.add_field(name='Member bot', value=f'{self.bot.no} No', inline=False)
        em.set_footer(text=f"Requested by {ctx.author}", icon_url = ctx.author.avatar_url)
        em.set_thumbnail(url = member.avatar_url)
        await ctx.send(embed=em)
        
    @commands.command(aliases=['si', 'server-info'])
    @commands.guild_only()
    async def serverinfo(self, ctx):
        """Shows various info about the server."""
        def formatted_date(date):
            if date is None:
                return 'N/A'
            return f'{date:%m-%d-%Y | %H:%M} UTC'

        info = []
        features = set(ctx.guild.features)
        all_features = {
            'PARTNERED': 'Partnered',
            'VERIFIED': 'Verified',
            'DISCOVERABLE': 'Server Discovery',
            'COMMUNITY': 'Community Server',
            'FEATURABLE': 'Featured',
            'WELCOME_SCREEN_ENABLED': 'Welcome Screen',
            'INVITE_SPLASH': 'Invite Splash',
            'VIP_REGIONS': 'VIP Voice Servers',
            'VANITY_URL': 'Vanity Invite URL',
            'COMMERCE': 'Commerce',
            'LURKABLE': 'Lurkable',
            'NEWS': 'News Channels',
            'THREADS_ENABLED': 'Threads',
            'ANIMATED_ICON': 'Animated Icon',
            'BANNER': 'Banner',
        }

        for feature, label in all_features.items():
            if feature in features:
                info.append(f'{label}')

        em = discord.Embed(
            title=f'{ctx.guild.name}',
            color=self.bot.color
        )
        em.add_field(name='<:owner:811749694744297502> Owner', value=ctx.guild.owner, inline=False)
        em.add_field(name='Description', value=ctx.guild.description, inline=False)
        em.add_field(name='Guild ID', value=ctx.guild.id, inline=False)
        em.add_field(name=f'Roles', value=len(ctx.guild.roles), inline=False)
        em.add_field(name=f'Members ({ctx.guild.member_count})', value=f'<:memberlist:811747305543434260> Humans: {len([m for m in ctx.guild.members if not m.bot])}\n<:botlist:811747723434786859> Bots: {sum(member.bot for member in ctx.guild.members)}', inline=False)
        em.add_field(name='Channels', value=f'<:textchannel:811747767763992586> Text: {len(ctx.guild.text_channels)}\n<:voicechannel:811748732906635295> Voice: {len(ctx.guild.voice_channels)}', inline=False)
        em.add_field(name='📁 Categories', value=len(ctx.guild.categories), inline=False)
        em.add_field(name='Emojis', value=len(ctx.guild.emojis), inline=False)
        em.add_field(name='Boost Info', value=f'<:boosts:811749808133373996> Boosts: {ctx.guild.premium_subscription_count}\n<:boostlevel:811749895143948288> Server level: {ctx.guild.premium_tier}', inline=False)
        if info:
            em.add_field(name='Server Features', value=', '.join(info), inline=False)
        else:
            em.add_field(name='Server Features', value=f'{self.bot.no} None', inline=False)
        em.add_field(name='Verification level', value=str(ctx.guild.verification_level).capitalize(), inline=False)
        em.set_thumbnail(url=f"{ctx.guild.icon_url}")
        em.set_footer(text=f'Created at: {formatted_date(ctx.guild.created_at)}')
        
        await ctx.send(embed=em)

    @commands.command(aliases=['channel-info','ci'])
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
        if channel.nsfw:
            e.add_field(name='NSFW', value=f'{self.bot.yes} Yes', inline=False)
        else:
            e.add_field(name='NSFW', value=f'{self.bot.no} No', inline=False)
        
        await ctx.send(embed=e)
    
    @commands.command(aliases=['role-info','ri'])
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

    @commands.command(aliases=['stats'])
    async def botinfo(self, ctx):
        """Shows info about bot."""
        def format_date(dt:datetime.datetime):
            if dt is None:
                return 'N/A'
            return f'<t:{int(dt.timestamp())}>'
        server_count = len(self.bot.guilds)
        total_members = len(set(self.bot.get_all_members()))
        dev = self.bot.get_user(710247495334232164)

        em = discord.Embed(color=self.bot.color)
        em.set_author(name=self.bot.user.name, icon_url=self.bot.user.avatar_url)
        em.add_field(name='Bot Info', value=f"<:dev_badge:833297795761831956> Developer: <@710247495334232164> `[{dev}]`\n🗓️ Date created: {format_date(self.bot.user.created_at)}\n<:python:819942756314906655> Language: `Python 3`\n<:dpy:824585353221505025> Discord.py version: `{discord.__version__}`\n", inline=False)
        em.add_field(name='Bot Stats', value=f"<:partnerbadge:819942435550396448> Servers: `{server_count} servers`\n<:memberlist:811747305543434260> Members: `{total_members} members`")
        em.set_footer(text=f'Hosted by {dev}', icon_url=dev.avatar_url)
        await ctx.send(embed=em)

    @commands.command(aliases=['ei', 'emoji-info'])
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
        em=discord.Embed(
            title=':link: Links',
            description='Here are some useful links!\n[Invite me](https://dsc.gg/pizza-invite) | [Support](https://discord.gg/WhNVDTF) | [Vote](https://top.gg/bot/860889936914677770/vote)',
            color=self.bot.color
        )
        em.set_author(name=self.bot.user.name, icon_url=self.bot.user.avatar_url)
        em.set_footer(text='Invite me to get good luck!')
        await ctx.send(embed=em)

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
        em.set_footer(text=f'Sent by {ctx.author} from {ctx.guild}', icon_url = ctx.author.avatar_url)

        channel = self.bot.get_channel(818927218884345866)
        e = await channel.send(embed=em)
        await e.add_reaction('⬆️')
        await e.add_reaction('⬇️')

    @commands.command(aliases=['team'])
    async def credits(self,ctx):
        """Shows users who have contributed to this bot."""
        em = discord.Embed(title=f'{self.bot.user.name} Contributors', color=self.bot.color)
        em.description=f"Drapes (<@583745403598405632>): [Github](https://github.com/drapespy)\nGDKID (<@596481615253733408>): [Github](https://github.com/GDKID69)\nCarl (<@106429844627169280>): [Github](https://github.com/CarlGroth)"
        await ctx.send(embed=em)

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

    @commands.command()
    async def uptime(self, ctx):
        """Tells you how long the bot has been up for."""
        em = discord.Embed(title="Local time", description=str(
            datetime.datetime.utcnow())[:-7], color=self.bot.color)
        em.set_author(name=self.bot.user.name,
                      icon_url=self.bot.user.avatar_url)
        em.add_field(name="Current uptime",
                     value=self.get_bot_uptime(brief=True), inline=False)
        em.add_field(name="Start time", value=str(
            self.bot.uptime)[:-7], inline=False)
        await ctx.send(embed=em)

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
        em.set_image(url=member.avatar_url)
        em.set_footer(text=f"Requested by {ctx.author.name}")
        await ctx.send(embed=em)
    
    @commands.command()
    async def vote(self,ctx):
        """Vote for the bot."""
        em = discord.Embed(
            title=f'Vote for {self.bot.user.name}',
            color=self.bot.color
            )
        em.add_field(name='DBL',value='[`VOTE NOW`](https://discordbotlist.com/bots/zion/upvote/)',inline=False)
        em.add_field(name='Top.gg',value='[`VOTE NOW`](https://top.gg/bot/860889936914677770/vote)',inline=False)
        em.set_thumbnail(url=self.bot.user.avatar_url)
        em.set_footer(text='Make sure to leave a nice review too!')
        await ctx.send(embed=em)
    
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
        For advanced poll, see `quickpoll`
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
    async def covid(self, ctx, country):
        """
        Get Covid-19 stats from a country or the world.
        """
        try:
            url = f"https://coronavirus-19-api.herokuapp.com/countries/{country}"
            stats = requests.get(url)
            json_stats = stats.json()
            country = json_stats["country"]
            totalCases = json_stats["cases"]
            todayCases = json_stats["todayCases"]
            totalDeaths = json_stats["deaths"]
            todayDeaths = json_stats["todayDeaths"]
            recovered = json_stats["recovered"]
            active = json_stats["active"]
            critical = json_stats["critical"]
            casesPerOneMil = json_stats["casesPerOneMillion"]
            deathsPerOneMil = json_stats["deathsPerOneMillion"]
            totalTests = json_stats["totalTests"]
            testsPerOneMil = json_stats["testsPerOneMillion"]

            e = discord.Embed(
                title=f"Covid-19 stats of {country}",
                description="This is not live info. Therefore it might not be as accurate, but is approximate info.",
                color=self.bot.color
            )
            e.add_field(name="Total Cases", value=totalCases, inline=True)
            e.add_field(name="Today's Cases", value=todayCases, inline=True)
            e.add_field(name="Total Deaths", value=totalDeaths, inline=True)
            e.add_field(name="Today's Deaths", value=todayDeaths, inline=True)
            e.add_field(name="Recovered", value=recovered, inline=True)
            e.add_field(name="Active", value=active, inline=True)
            e.add_field(name="Critical", value=critical, inline=True)
            e.add_field(name="Cases per one million", value=casesPerOneMil, inline=True)
            e.add_field(name="Deaths per one million", value=deathsPerOneMil, inline=True)
            e.add_field(name="Tests per one million", value=testsPerOneMil, inline=True)
            e.add_field(name="Total tests", value=totalTests, inline=True)
            e.set_thumbnail(url="https://www.osce.org/files/imagecache/10_large_gallery/f/images/hires/8/a/448717.jpg")

            await ctx.send(embed=e)
        except:
            await ctx.send(f"{self.bot.no} Invalid country name or API error! Try again later.")
        
def setup(bot):
    bot.add_cog(Utility(bot))
