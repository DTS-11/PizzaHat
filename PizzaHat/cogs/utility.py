import datetime
import time

import discord
import psutil
from core.cog import Cog
from discord.ext import commands
from discord.ui import Button, View

start_time = time.time()

def format_date(dt:datetime.datetime):
    if dt is None:
        return 'N/A'
    return f'<t:{int(dt.timestamp())}>'


class Utility(Cog, emoji="🛠️"):
    """Utility commands which makes your discord experience smooth!"""
    def __init__(self, bot):
        self.bot = bot
        self.process = psutil.Process()

    @commands.command(aliases=['latency'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def ping(self, ctx):
        """Shows latency of bot."""

        time1 = time.perf_counter()
        msg = await ctx.send("Pinging...")
        time2 = time.perf_counter()

        await msg.edit(content=
            "🏓 Pong!"
            f"\nAPI: `{round(self.bot.latency*1000)}ms`"
            f"\nBot: `{round(time2-time1)*1000}ms`"
        )

    @commands.command(aliases=['whois','ui'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.guild_only()
    async def userinfo(self, ctx,  member:discord.Member=None):
        """
        Shows info about a user.
        If no user is given, returns value of yourself.
        """

        if member is None:
            member = ctx.author

        uroles = [role.mention for role in member.roles if not role.is_default()]
        uroles.reverse()

        if len(uroles) > 15:
            uroles = [f"{', '.join(uroles[:10])} (+{len(member.roles) - 11})"]

        user_roles = ('**({} Total)**').format(len(member.roles) - 1) if uroles != [] else ('No roles')

        em = discord.Embed(
            color=member.color,
            timestamp=ctx.message.created_at
        )
        em.set_author(name=member, icon_url=member.display_avatar)

        em.add_field(name="User ID", value=member.id, inline=False)
        em.add_field(name="Display Name", value=member.display_name, inline=False)
        em.add_field(
            name="Account Creation",
            value=format_date(member.created_at),
            inline=False
        )
        em.add_field(
            name="Joined Server",
            value=format_date(member.joined_at),
            inline=False
        )
        em.add_field(
            name="Roles",
            value=', '.join(uroles) + user_roles,
            inline=False
        )
        if member.bot:
            em.add_field(
                name="Member Bot",
                value=f"{self.bot.yes} Yes",
                inline=False
            )
        else:
            em.add_field(
                name="Member bot",
                value=f"{self.bot.no} No",
                inline=False
            )

        em.set_footer(text=f"Requested by {ctx.author}", icon_url = ctx.author.avatar.url)

        if member.avatar:
            em.set_thumbnail(url=member.avatar.url)
        else:
            em.set_thumbnail(url="https://logos-world.net/wp-content/uploads/2020/12/Discord-Logo.png")
        await ctx.send(embed=em)
        
    @commands.command(aliases=['si'])
    @commands.cooldown(1, 3, commands.BucketType.user)
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

        if ctx.guild.icon:
            em.set_thumbnail(url=ctx.guild.icon.url)
        else:
            em.set_thumbnail(url="https://logos-world.net/wp-content/uploads/2020/12/Discord-Logo.png")
        em.set_footer(text=f'Created at: {formatted_date(ctx.guild.created_at)}')
        
        await ctx.send(embed=em)

    @commands.command(aliases=['ci'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.guild_only()
    async def channelinfo(self, ctx, *, channel: discord.TextChannel=None):
        """
        Shows info about a channel.
        If no channel is given, returns value for the current channel.
        """

        if channel is None:
            channel  = ctx.channel

        e = discord.Embed(title='Channel information', color=self.bot.color)
        e.add_field(name='Channel name', value=channel.name, inline=False)
        e.add_field(name='Channel ID', value=channel.id, inline=False)
        e.add_field(name='Mention', value=channel.mention, inline=False)
        e.add_field(name='Category name', value=channel.category.name, inline=False)
        e.add_field(name='Channel Created', value=format_date(channel.created_at), inline=False)
        e.add_field(name="NSFW", value=f'{self.bot.yes} Yes' if channel.nsfw else f'{self.bot.no} No', inline=False)
        
        await ctx.send(embed=e)

    @commands.command(aliases=['vi'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.guild_only()
    async def vcinfo(self, ctx, *, vc: discord.VoiceChannel):
        """Shows info about a voice channel."""

        e = discord.Embed(title='VC Information', color=self.bot.color)
        e.add_field(name='VC name', value=vc.name, inline=False)
        e.add_field(name='VC ID', value=vc.id, inline=False)
        e.add_field(name='VC bitrate', value=vc.bitrate, inline=False)
        e.add_field(name='Mention', value=vc.mention, inline=False)
        e.add_field(name='Category name', value=vc.category.name, inline=False)
        e.add_field(name='VC Created', value=format_date(vc.created_at), inline=False)

        await ctx.send(embed=e)
    
    @commands.command(aliases=['ri'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.guild_only()
    async def roleinfo(self, ctx, *, role: discord.Role):
        """
        Gives some info about the specified role.
        You can mention the role or give the name of it.
        """

        e = discord.Embed(title='Role Information', color=self.bot.color)
        e.add_field(name='Role name', value=role.name, inline=False)
        e.add_field(name='Role ID', value=role.id, inline=False)
        e.add_field(name='Mention', value=role.mention, inline=False)
        e.add_field(name='Role Created', value=format_date(role.created_at), inline=False)
        e.add_field(name='Role Color', value=role.color, inline=False)
        if role.mentionable:
            e.add_field(name='Mentionable', value=f'{self.bot.yes} Yes', inline=False)
        else:
            e.add_field(name='Mentionable', value=f'{self.bot.no} No', inline=False)
        
        await ctx.send(embed=e)

    @commands.command(aliases=['ei'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.guild_only()
    async def emojiinfo(self, ctx, emoji:discord.Emoji):
        """Shows info about emoji."""

        try:
            emoji = await emoji.guild.fetch_emoji(emoji.id)
        except discord.NotFound:
            return await ctx.send("I could not find this emoji in the given guild.")

        is_managed = "Yes" if emoji.managed else "No"
        is_animated = "Yes" if emoji.animated else "No"
        requires_colons = "Yes" if emoji.require_colons else "No"
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
        **- Time Created:** {format_date(emoji.created_at)}
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
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def about(self, ctx):
        """Tells you information about the bot itself."""

        total_members = 0
        total_unique = len(self.bot.users)

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
        cpu_usage = self.process.cpu_percent() / psutil.cpu_count()

        dpy_version = discord.__version__
        dev = self.bot.get_user(710247495334232164)

        em = discord.Embed(color=self.bot.color)
        em.set_author(name=dev, icon_url=dev.avatar.url)

        em.title = "About"
        em.description = self.bot.description

        em.add_field(
            name="Servers",
            value=guilds
        )
        em.add_field(
            name="Users",
            value=f"{total_members} total\n{total_unique} unique"
        )
        em.add_field(
            name="Channels",
            value=f"{text + voice} total\n{text} text\n{voice} voice"
        )
        em.add_field(
            name="Process",
            value=f"{memory_usage:.2f} MiB\n{cpu_usage:.2f}% CPU"
        )
        em.add_field(
            name="Discord.py version",
            value=dpy_version
        )
        em.add_field(
            name="Uptime",
            value=self.get_bot_uptime(brief=True)
        )

        em.set_thumbnail(url=self.bot.user.avatar.url)
        em.set_footer(text="Made with ♥ with discord.py", icon_url="http://i.imgur.com/5BFecvA.png")

        await ctx.send(embed=em)

    @commands.command(name='invite')
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def invite_cmd(self, ctx):
        """Gives invite of bot."""

        b1 = Button(label="Invite", emoji="✉️", url="https://dsc.gg/pizza-invite")
        b2 = Button(label="Support", emoji="📨", url="https://discord.gg/WhNVDTF")
        b3 = Button(label="Vote", emoji="🗳", url="https://top.gg/bot/860889936914677770/vote")
        view = View()
        view.add_item(item=b1)
        view.add_item(item=b2)
        view.add_item(item=b3)

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
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def support(self, ctx):
        """Gives link to support server"""

        await ctx.send('Do you want help? Join the support server now!\nhttps://discord.gg/WhNVDTF')

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
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
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def permissions(self, ctx, *, member: discord.Member = None):
        """Shows a member's permissions.
        If used in DM's, shows your permissions in a DM channel."""

        channel = ctx.message.channel
        if member is None:
            member = ctx.author
        await self.say_permissions(ctx, member, channel)

    @commands.command(aliases=['botperms'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def botpermissions(self, ctx):
        """Shows the bot's permissions."""

        channel = ctx.channel
        member = ctx.message.guild.me
        await self.say_permissions(ctx, member, channel)

    @commands.command(aliases=['av'])
    @commands.cooldown(1, 3, commands.BucketType.user)
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
    @commands.cooldown(1, 3, commands.BucketType.user)
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
        view = View()
        view.add_item(item=b1)
        view.add_item(item=b2)

        await ctx.send(embed=em, view=view)
        
    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 20, commands.BucketType.user)
    @commands.has_permissions(manage_emojis=True)
    async def emotes(self, ctx):
        """
        Sends the servers emotes and their raw form in a list.
        """

        emojis = ctx.guild.emojis
        emoji_string = ''
        for e in emojis:
            if e.animated == True:
                info = f'<a:{e.name}:{e.id}> - `<a:{e.name}:{e.id}>`\n'
            else:
                info = f'<:{e.name}:{e.id}> - `<:{e.name}:{e.id}>`\n'
            emoji_string += info
        chunk = emoji_string.split('\n')

        x = 15    

        final_list= lambda chunk, x: [chunk[i:i+x] for i in range(0, len(chunk), x)]

        output=final_list(chunk, x)

        for b in output:
            try:
                c = '\n'.join(b)
                await ctx.send(c)
            except:
                pass

        
async def setup(bot):
    await bot.add_cog(Utility(bot))
