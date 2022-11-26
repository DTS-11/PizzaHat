import os
from datetime import timedelta

import discord
import wavelink
from core.bot import PizzaHat
from core.cog import Cog
from discord.ext import commands
from discord.ext.commands import Context


class Music(Cog, emoji=929100003178348634):
    """Listen to music and chill!"""
    def __init__(self, bot: PizzaHat):
        self.bot: PizzaHat = bot
        bot.loop.create_task(self.connect_nodes())

    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        await wavelink.NodePool.create_node(
            bot=self.bot,
            host=os.getenv("WAVELINK_HOST"),  # type: ignore
            port=443,
            password=os.getenv("WAVELINK_PASS"),  # type: ignore
            https=True
        )


    @commands.command(aliases=['leave'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def dc(self, ctx: Context):
        """Leaves a VC."""

        if ctx.voice_client is not None:
            await ctx.voice_client.disconnect(force=True)
            await ctx.message.add_reaction("👋")

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def play(self, ctx: Context, *, song: wavelink.YouTubeTrack):
        """Plays a song."""

        if ctx.author.voice is None:  # type: ignore
            return await ctx.send("You are not in a voice channel")
        vc: wavelink.Player = ctx.voice_client or await ctx.author.voice.channel.connect(cls=wavelink.Player)  # type: ignore

        if vc.queue.is_empty and not vc.is_playing():
            await vc.play(song)

            em = discord.Embed(color=self.bot.color)
            em.add_field(name="▶ Playing", value=f"[{song.title}]({song.uri})", inline=False)
            em.add_field(name="⌛ Song Duration", value=str(timedelta(seconds=song.duration)), inline=False)
            em.add_field(name="👥 Requested by", value=ctx.author.mention, inline=False)
            em.add_field(name="🎵 Song by", value=song.author, inline=False)
            em.set_thumbnail(url=vc.source.thumbnail)  # type: ignore

            await ctx.send(embed=em)

        else:
            await vc.queue.put_wait(song)
            await ctx.send(f"{self.bot.yes} Added `{song.title}` to the queue...")

        vc.ctx = ctx  # type: ignore
        setattr(vc, "loop", False)

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def skip(self, ctx: Context):
        """Skip to the next song in the queue."""

        try:
            if ctx.author.voice is None:  # type: ignore
                return await ctx.send("You are not in a voice channel")

            elif not ctx.voice_client:
                return await ctx.send("You are not playing any music")
            
            else:
                vc: wavelink.Player = ctx.voice_client  # type: ignore
                await vc.stop()
                await ctx.send("⏭ Skipped.")

        except wavelink.errors.QueueEmpty:
            return await ctx.send("Queue is empty.")

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def pause(self, ctx: Context):
        """Pause a song which is currently playing."""

        if ctx.author.voice is None:  # type: ignore
            return await ctx.send("You are not in a voice channel")

        elif not ctx.voice_client:
            return await ctx.send("You are not playing any music")
        
        else:
            vc: wavelink.Player = ctx.voice_client  # type: ignore
            await vc.pause()
            await ctx.message.add_reaction("⏸")

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def resume(self, ctx: Context):
        """Resume a paused song."""

        if ctx.author.voice is None:  # type: ignore
            return await ctx.send("You are not in a voice channel")

        elif not ctx.voice_client:
            return await ctx.send("You are not playing any music")

        else:
            vc: wavelink.Player = ctx.voice_client  # type: ignore
            await vc.resume()
            await ctx.message.add_reaction("▶")

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def stop(self, ctx: Context):
        """Stops the playing song and removes everything from the queue."""

        if ctx.author.voice is None:  # type: ignore
            return await ctx.send("You are not in a voice channel")

        elif not ctx.voice_client:
            return await ctx.send("You are not playing any music")

        else:
            vc: wavelink.Player = ctx.voice_client  # type: ignore
            vc.queue.clear()
            await vc.stop()
            await ctx.message.add_reaction("⏹")

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def loop(self, ctx: Context):
        """Loop a song."""

        if ctx.author.voice is None:  # type: ignore
            return await ctx.send("You are not in a voice channel")

        elif not ctx.voice_client:
            return await ctx.send("You are not playing any music")

        else:
            vc: wavelink.Player = ctx.voice_client  # type: ignore
        
        try:
            vc.loop ^= True  # type: ignore

        except Exception:
            setattr(vc, "loop", False)

        if vc.loop:  # type: ignore
            return await ctx.send("🔁 Loop is now enabled")
        
        else:
            return await ctx.send("🔁 Loop is now disabled.")

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def queue(self, ctx: Context):
        """Displays the songs which are in the queue."""

        if ctx.author.voice is None:  # type: ignore
            return await ctx.send("You are not in a voice channel")

        elif not ctx.voice_client:
            return await ctx.send("You are not playing any music")

        else:
            vc: wavelink.Player = ctx.voice_client  # type: ignore
        
        if vc.queue.is_empty:
            return await ctx.send("Queue is empty.")
        
        else:
            queue = vc.queue.copy()
            song_count = 0
            
            em=discord.Embed(
                color=self.bot.color,
                timestamp=ctx.message.created_at
            )

            for songs in queue:
                song_count += 1
                songs = [i.title for i in vc.queue]  # type: ignore

                em.title=f"Queued songs [{song_count}]"

                for song in songs:
                    em.add_field(name="\u200b", value=song, inline=False)

            await ctx.send(embed=em)

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def volume(self, ctx: Context, volume: int):
        """Change the volume of the song"""

        if ctx.author.voice is None:  # type: ignore
            return await ctx.send("You are not in a voice channel")

        elif not ctx.voice_client:
            return await ctx.send("You are not playing any music")

        else:
            vc: wavelink.Player = ctx.voice_client  # type: ignore
        
        if volume > 100:
            return await ctx.send("That is wayy too high...")

        elif volume < 100:
            return await ctx.send("That is wayy too low...")

        await vc.set_volume(volume)
        await ctx.send(f"{self.bot.yes} Set volume to {volume}%")

    @commands.command(aliases=['np'])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def nowplaying(self, ctx: Context):
        """Shows which song is playing."""
        
        if ctx.author.voice is None:  # type: ignore
            return await ctx.send("You are not in a voice channel")

        elif not ctx.voice_client:
            return await ctx.send("You are not playing any music")

        else:
            vc: wavelink.Player = ctx.voice_client  # type: ignore

        if not vc.is_playing():
            return await ctx.send("Nothing is playing right now.")

        else:
            if vc.track is not None:
                em = discord.Embed(color=self.bot.color)
                em.add_field(name="▶ Now playing", value=f"[{vc.track.title}]({vc.track.uri})", inline=False)  # type: ignore
                em.add_field(name="⌛ Song Duration", value=str(timedelta(seconds=vc.track.duration)), inline=False)
                em.add_field(name="🎵 Song by", value=vc.track.author, inline=False)  # type: ignore
                em.set_thumbnail(url=vc.source.thumbnail)  # type: ignore

                await ctx.send(embed=em)


async def setup(bot):
    await bot.add_cog(Music(bot))
