import discord
from discord.ext import commands
import DiscordUtils
import humanfriendly

music = DiscordUtils.Music()

class Music(commands.Cog):
    """<:music:929100003178348634> Music commands"""
    def __init__(self, bot):
        self.bot = bot
        
    def now_playing_embed(self, ctx, song) -> discord.Embed:
        return discord.Embed(
            title=song.title,
            url=song.url,
            color=self.bot.color,
            description=f"""
            **Duration:** {humanfriendly.format_timespan(song.duration)}
            **Channel:** [{song.channel}]({song.channel_url})
            """
            ).set_thumbnail(url=song.thumbnail
            ).set_footer(text=f"Loop: {'✅' if song.is_looping else '❌'}", icon_url=ctx.guild.icon.url if ctx.guild.icon is not None else 'https://cdn.discordapp.com/embed/avatars/1.png'
            ).set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
    
    @commands.command()
    async def join(self, ctx):
        """Joins VC where you're in."""
        if not ctx.author.voice:
            return await ctx.send("You are not in a voice channel. Please join one.")
        
        if ctx.guild.me.voice and len(ctx.guild.me.voice.channel.members) > 1:
            return await ctx.send("Someone else is already using the bot.")
        
        try:
            await ctx.author.voice.channel.connect()
            await ctx.message.add_reaction('👍')
        except Exception as e:
            return await ctx.send(f"I wasn't able to connect to your voice channel.\nPlease make sure I have enough permissions.\nError: {e}")
        
    @commands.command(aliases=['dc'])
    async def leave(self, ctx):
        if not ctx.author.voice:
            return await ctx.send("You're not in a voice channel.")
        if not ctx.guild.me.voice:
            return await ctx.send("I am not in a voice channel ._.")
        player = music.get_player(guild_id=ctx.guild.id)
        
        if player:
            try:
                await player.stop()
                await player.delete()
            except Exception:
                pass
            
        await ctx.voice_client.disconnect()
        await ctx.message.add_reaction('👋')
        
    @commands.command()
    async def play(self, ctx, *, song):
        """Play a song using URL/song name."""
        if not ctx.author.voice:
            return await ctx.send("You are not in a voice channel. Please join one.")
        if not ctx.guild.me.voice:
            await ctx.author.voice.channel.connect()
            
        player = music.get_player(guild_id=ctx.guild.id)
        if not player:
            player = music.create_player(ctx, ffmpeg_error_betterfix=True)
            
        if not ctx.voice_client.is_playing():
            s1 = await ctx.send(f"🔍 Searching for: {song}")
            await player.queue(song, search=True)
            song = await player.play()
            await s1.edit(embed=self.now_playing_embed(ctx, song))
            
        else:
            s2 = await ctx.send(f"🔍 Searching for: {song}")
            song = await player.queue(song, search=True)
            await ctx.send(f"{song.name} added to the queue.")
        
    @commands.command()
    async def stop(self, ctx):
        """Stop the song."""
        player = music.get_player(guild_id=ctx.guild.id)
        await player.stop()
        await ctx.send("⏹ Stopped")
        
    @commands.command(aliases=['np'])
    async def nowplaying(self, ctx):
        """See what's playing now."""
        player = music.get_player(guild_id=ctx.guild.id)
        if not player:
            return await ctx.send("Nothing is playing rn.")
        if not ctx.voice_client.is_playing():
            return await ctx.send("No music playing rn ._.")
        song = player.now_playing()
        await ctx.send(embed=self.now_playing_embed(ctx, song))
        
    @commands.command()
    async def pause(self, ctx):
        """Pause the song."""
        player = music.get_player(guild_id=ctx.guild.id)
        try:
            await player.pause()
        except DiscordUtils.NotPlaying:
            return await ctx.send("I am not playing any songs ._.")
        await ctx.message.add_reaction("⏸️")
    
    @commands.command()
    async def resume(self, ctx):
        """Resume the song."""
        player = music.get_player(guild_id=ctx.guild.id)
        if not player:
            return await ctx.send("I am not playing any songs ._.")
        try:
            await player.resume()
        except DiscordUtils.NotPlaying:
            return await ctx.send("I am not playing any songs ._.")
        await ctx.message.add_reaction("▶️")
        
    @commands.command()
    async def skip(self, ctx):
        """Skip the current song."""
        player = music.get_player(guild_id=ctx.guild.id)
        if not player:
            await ctx.send("No music found in the queue.")
            
        data = await player.skip(force=True)
        if len(data) == 2:
            await ctx.send(f"⏩ Skipped from {data[0].name} to {data[1].name}")
        else:
            await ctx.send(f"⏩ Skipped {data[0].name}")
            
    @commands.command()
    async def queue(self, ctx):
        """See the list of queued songs."""
        player = music.get_player(guild_id=ctx.guild.id)
        if player is None or len(player.current_queue()) == 0:
            await ctx.send("Queue is empty.")
        else:
            e = discord.Embed(
                title='Queued songs',
                description=f"{', '.join([song.name for song in player.current_queue()])}",
                color=self.bot.color
            )
            await ctx.send(embed=e)
    
    @commands.command()
    async def remove(self, ctx, song):
        """Remove a song from the queue."""
        player = music.get_player(guild_id=ctx.guild.id)
        song = await player.remove_from_queue(int(song))
        await ctx.send(f"Removed {song.name} from queue.")
            
    @commands.command()
    async def loop(self, ctx):
        """Toggle loop for the current song."""
        player = music.get_player(guild_id=ctx.guild.id)
        if not player:
            await ctx.send("No songs found to loop.")
            
        song = await player.toggle_song_loop()
        if song.is_looping:
            await ctx.send(f"🔄 Enabled loop for {song.name}")
        else:
            await ctx.send(f"🔄 Disabled loop for {song.name}")
            
    @commands.command
    async def volume(self, ctx, vol):
        """Change the volume of the music player."""
        player = music.get_player(guild_id=ctx.guild.id)
        song, volume = await player.change_volume(float(vol) / 100)
        await ctx.send(f"🔊 Changed volume to {volume*100}%")
    
def setup(bot):
    bot.add_cog(Music(bot))
