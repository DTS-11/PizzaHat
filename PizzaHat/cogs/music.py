import os
from datetime import timedelta

import discord
import wavelink
from core.cog import Cog
from discord.ext import commands


class Music(Cog, emoji=929100003178348634):
    """Listen to music and chill!"""
    def __init__(self, bot):
        self.bot = bot
        bot.loop.create_task(self.connect_nodes())

    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        await wavelink.NodePool.create_node(
            bot=self.bot,
            host=os.getenv("WAVELINK_HOST"),
            port=443,
            password=os.getenv("WAVELINK_PASS"),
            https=True
        )


    @commands.command(aliases=['leave'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def dc(self, ctx):
        """Leaves a VC."""

        await ctx.voice_client.disconnect()
        await ctx.message.add_reaction("👋")

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def play(self, ctx, *, song: wavelink.YouTubeTrack):
        """Plays a song."""

        if ctx.author.voice is None:
            return await ctx.send("You are not in a voice channel")
        vc: wavelink.Player = ctx.voice_client or await ctx.author.voice.channel.connect(cls=wavelink.Player)

        if vc.queue.is_empty and not vc.is_playing():
            await vc.play(song)

            em = discord.Embed(color=self.bot.color)
            em.add_field(name="▶ Playing", value=f"[{song.title}]({song.uri})", inline=False)
            em.add_field(name="⌛ Song Duration", value=str(timedelta(seconds=song.duration)), inline=False)
            em.add_field(name="👥 Requested by", value=ctx.author.mention, inline=False)
            em.add_field(name="🎵 Song by", value=song.author, inline=False)
            em.set_thumbnail(url=vc.source.thumbnail)

            await ctx.send(embed=em)

        else:
            await vc.queue.put_wait(song)
            await ctx.send(f"{self.bot.yes} Added `{song.title}` to the queue...")

        vc.ctx = ctx
        setattr(vc, "loop", False)

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def skip(self, ctx):
        """Skip to the next song in the queue."""

        try:
            if ctx.author.voice is None:
                return await ctx.send("You are not in a voice channel")

            elif not ctx.voice_client:
                return await ctx.send("You are not playing any music")
            
            else:
                vc: wavelink.Player = ctx.voice_client
                await vc.stop()
                await ctx.send("⏭ Skipped.")

        except wavelink.errors.QueueEmpty:
            return await ctx.send("Queue is empty.")

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def pause(self, ctx):
        """Pause a song which is currently playing."""

        if ctx.author.voice is None:
            return await ctx.send("You are not in a voice channel")

        elif not ctx.voice_client:
            return await ctx.send("You are not playing any music")
        
        else:
            vc: wavelink.Player = ctx.voice_client
            await vc.pause()
            await ctx.message.add_reaction("⏸")

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def resume(self, ctx):
        """Resume a paused song."""

        if ctx.author.voice is None:
            return await ctx.send("You are not in a voice channel")

        elif not ctx.voice_client:
            return await ctx.send("You are not playing any music")

        else:
            vc: wavelink.Player = ctx.voice_client
            await vc.resume()
            await ctx.message.add_reaction("▶")

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def stop(self, ctx):
        """Stops the playing song and removes everything from the queue."""

        if ctx.author.voice is None:
            return await ctx.send("You are not in a voice channel")

        elif not ctx.voice_client:
            return await ctx.send("You are not playing any music")

        else:
            vc: wavelink.Player = ctx.voice_client
            vc.queue.clear()
            await vc.stop()
            await ctx.message.add_reaction("⏹")

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def loop(self, ctx):
        """Loop a song."""

        if ctx.author.voice is None:
            return await ctx.send("You are not in a voice channel")

        elif not ctx.voice_client:
            return await ctx.send("You are not playing any music")

        else:
            vc: wavelink.Player = ctx.voice_client
        
        try:
            vc.loop ^= True

        except Exception:
            setattr(vc, "loop", False)

        if vc.loop:
            return await ctx.send("🔁 Loop is now enabled")
        
        else:
            return await ctx.send("🔁 Loop is now disabled.")

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def queue(self, ctx):
        """Displays the songs which are in the queue."""

        if ctx.author.voice is None:
            return await ctx.send("You are not in a voice channel")

        elif not ctx.voice_client:
            return await ctx.send("You are not playing any music")

        else:
            vc: wavelink.Player = ctx.voice_client
        
        if vc.queue.is_empty:
            return await ctx.send("Queue is empty.")
        
        else:
            queue = vc.queue.copy()
            song_count = 0

            for songs in queue:
                song_count += 1
                songs = [i.title for i in vc.queue]

                em = discord.Embed(title=f"Queued songs [{song_count}]", color=self.bot.color)

                for song in songs:
                    em.add_field(name="\u200b", value=song, inline=False)

            await ctx.send(embed=em)

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def volume(self, ctx, volume: int):
        """Change the volume of the song"""

        if ctx.author.voice is None:
            return await ctx.send("You are not in a voice channel")

        elif not ctx.voice_client:
            return await ctx.send("You are not playing any music")

        else:
            vc: wavelink.Player = ctx.voice_client
        
        if volume > 100:
            return await ctx.send("That is wayy too high...")

        elif volume < 100:
            return await ctx.send("That is wayy too low...")

        await vc.set_volume(volume)
        await ctx.send(f"{self.bot.yes} Set volume to {volume}%")

    @commands.command(aliases=['np'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def nowplaying(self, ctx):
        """Shows which song is playing."""
        
        if ctx.author.voice is None:
            return await ctx.send("You are not in a voice channel")

        elif not ctx.voice_client:
            return await ctx.send("You are not playing any music")

        else:
            vc: wavelink.Player = ctx.voice_client

        if not vc.is_playing():
            return await ctx.send("Nothing is playing right now.")

        else:
            em = discord.Embed(color=self.bot.color)
            em.add_field(name="▶ Now playing", value=f"[{vc.track.title}]({vc.track.uri})", inline=False)
            em.add_field(name="⌛ Song Duration", value=str(timedelta(seconds=vc.track.duration)), inline=False)
            em.add_field(name="🎵 Song by", value=vc.track.author, inline=False)
            em.set_thumbnail(url=vc.source.thumbnail)

            await ctx.send(embed=em)


async def setup(bot):
    await bot.add_cog(Music(bot))
